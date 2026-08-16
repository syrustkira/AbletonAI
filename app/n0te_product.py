"""Song-centred product workflows built from durable evidence, not AI claims."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import threading
import time
import uuid
from typing import Any

from n0te_audio import AudioBuffer, analyze, masking
from n0te_audio_workflow import RenderSpecification, render_external
from n0te_dsp import Gain
from n0te_events import EventEngine
from n0te_state import atomic_write_json


class EvidenceKind(str, Enum):
    DAW_FACT = "DAW_FACT"
    AUDIO_MEASUREMENT = "AUDIO_MEASUREMENT"
    USER_DECLARED_INTENT = "USER_DECLARED_INTENT"
    USER_DECISION = "USER_DECISION"
    SYSTEM_FACT = "SYSTEM_FACT"
    INFERENCE = "INFERENCE"
    EXTERNAL_FACT = "EXTERNAL_FACT"
    MODELED_VALUE = "MODELED_VALUE"
    MEASURED_VALUE = "MEASURED_VALUE"
    EAR_DECISION_REQUIRED = "EAR_DECISION_REQUIRED"


class Privacy(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    VAULT = "VAULT"
    AVAILABLE_TO_AI = "AVAILABLE_TO_AI"
    SYNC_ELIGIBLE = "SYNC_ELIGIBLE"
    PUBLICATION_ELIGIBLE = "PUBLICATION_ELIGIBLE"
    COMMUNITY_VISIBLE = "COMMUNITY_VISIBLE"


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    claim: str
    source: str
    song_id: str
    workspace_id: str = ""
    section: str = ""
    privacy: tuple[Privacy, ...] = (Privacy.LOCAL_ONLY,)
    measurement_confidence: str = "UNKNOWN"
    recommendation_confidence: str = "UNKNOWN"

    def __post_init__(self):
        if not self.claim or not self.source or not self.song_id:
            raise ValueError("Evidence requires claim, provenance source, and Song identity")
        outward = {
            Privacy.AVAILABLE_TO_AI,
            Privacy.SYNC_ELIGIBLE,
            Privacy.PUBLICATION_ELIGIBLE,
            Privacy.COMMUNITY_VISIBLE,
        }
        if Privacy.VAULT in self.privacy and any(flag in outward for flag in self.privacy):
            raise ValueError("Vault evidence cannot implicitly become AI, sync, publication, or community content")


@dataclass
class SongTwins:
    song_id: str
    technical: list[Evidence] = field(default_factory=list)
    creative: list[Evidence] = field(default_factory=list)

    @staticmethod
    def _terms(value: str) -> set[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or ""))
        stop = {
            "the", "and", "for", "with", "that", "this", "from", "into", "keep", "preserve",
            "intentional", "measured", "automatic", "change", "should", "want", "make",
        }
        return {word for word in cleaned.split() if len(word) > 2 and word not in stop}

    def recommend(self, technical_claim: str, subject: str = "", section: str = "", source: str = "") -> dict[str, Any]:
        target_terms = self._terms(" ".join((technical_claim, subject, section, source)))
        conflicts = []
        for evidence in self.creative:
            if evidence.kind is not EvidenceKind.USER_DECLARED_INTENT:
                continue
            claim = evidence.claim.lower()
            if not any(marker in claim for marker in ("intentional", "preserve", "do not")):
                continue
            if section and evidence.section and evidence.section != section:
                continue
            claim_terms = self._terms(evidence.claim)
            if target_terms and claim_terms and not (target_terms & claim_terms):
                continue
            conflicts.append(evidence)
        return {
            "technical_claim": technical_claim,
            "creative_conflicts": [asdict(e) for e in conflicts],
            "automatic_correction": not conflicts,
            "decision": "EAR_DECISION_REQUIRED" if conflicts else "TECHNICAL_CANDIDATE",
        }


class ProductStore:
    """One atomic Song-product ledger; events remain in the existing EventEngine."""

    SCHEMA = 1

    def __init__(self, state: Path):
        self.path = Path(state) / "product.json"
        self.recovery_dir = Path(state) / "Recovery"
        self.events = EventEngine(Path(state))
        self._lock = threading.RLock()

    def _empty(self):
        return {
            "schema": self.SCHEMA,
            "sessions": [],
            "ear_decisions": [],
            "auditions": [],
            "versions": [],
            "preferences": [],
            "recovery_required": False,
            "recovery_copy": "",
        }

    def _preserve_corrupt_copy(self) -> str:
        try:
            if not self.path.is_file():
                return ""
            self.recovery_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time() * 1000)
            recovery = self.recovery_dir / f"product-corrupt-{stamp}.json"
            recovery.write_bytes(self.path.read_bytes())
            return str(recovery)
        except OSError:
            return ""

    def load(self):
        if not self.path.is_file():
            return self._empty()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema") != self.SCHEMA:
                raise ValueError("Unsupported product state schema")
            baseline = self._empty()
            baseline.update(value)
            baseline["recovery_required"] = False
            baseline["recovery_copy"] = ""
            return baseline
        except (OSError, ValueError, json.JSONDecodeError):
            baseline = self._empty()
            baseline["recovery_required"] = True
            baseline["recovery_copy"] = self._preserve_corrupt_copy()
            return baseline

    def _mutate(self, function):
        with self._lock:
            state = self.load()
            if state.get("recovery_required"):
                raise RuntimeError("Product state requires recovery before mutation")
            result = function(state)
            atomic_write_json(self.path, state)
            return result

    def start_session(self, song_id, workspace_id, mode, goal, exit_condition, guardrails=(),
                      bottleneck="", deliverable=""):
        if mode not in {"WRITE", "ARRANGE", "RECORD", "MIX", "FINISH", "EXPLORE", "FIX_SOMETHING", "PERFORM", "CONTENT"}:
            raise ValueError("Unknown session mode")
        if not song_id or not goal or not exit_condition:
            raise ValueError("Song, goal, and exit condition required")
        row = {
            "id": uuid.uuid4().hex,
            "song_id": song_id,
            "workspace_id": workspace_id,
            "mode": mode,
            "goal": goal,
            "exit_condition": exit_condition,
            "not_now": list(guardrails),
            "bottleneck": bottleneck,
            "deliverable": deliverable,
            "started_at": time.time(),
            "status": "ACTIVE",
        }
        self._mutate(lambda state: state["sessions"].append(row) or row)
        self.events.append("SESSION_STARTED", song_id, workspace_id, data=row)
        return row

    def complete_session(self, session_id, evidence: list[Evidence], next_action="", exit_condition_status="UNVERIFIED"):
        allowed_exit = {"UNVERIFIED", "USER_CONFIRMED", "EVIDENCE_SUPPORTED", "NOT_MET"}
        if exit_condition_status not in allowed_exit:
            raise ValueError("Unknown exit-condition status")

        def apply(state):
            row = next((item for item in state["sessions"] if item["id"] == session_id), None)
            if not row or row["status"] != "ACTIVE":
                raise ValueError("Active session not found")
            scoped = [
                item for item in evidence
                if item.song_id == row["song_id"] and item.workspace_id == row["workspace_id"]
            ]
            decisions = [item.claim for item in scoped if item.kind is EvidenceKind.USER_DECISION]
            changes = [item.claim for item in scoped if item.kind in {EvidenceKind.DAW_FACT, EvidenceKind.SYSTEM_FACT}]
            remaining = [item.claim for item in scoped if item.kind is EvidenceKind.EAR_DECISION_REQUIRED]
            row.update(
                status="COMPLETED",
                completed_at=time.time(),
                debrief={
                    "goal": row["goal"],
                    "exit_condition": row["exit_condition"],
                    "exit_condition_status": exit_condition_status,
                    "what_changed": changes,
                    "decisions": decisions,
                    "ear_decisions_remaining": remaining,
                    "completed": exit_condition_status in {"USER_CONFIRMED", "EVIDENCE_SUPPORTED"},
                    "next_obvious_action": next_action,
                },
            )
            return row

        row = self._mutate(apply)
        self.events.append("SESSION_COMPLETED", row["song_id"], row["workspace_id"], data=row["debrief"])
        return row

    def context(self, song_id, workspace_id, evidence):
        scoped = [item for item in evidence if item.song_id == song_id and item.workspace_id == workspace_id]
        known_kinds = {
            EvidenceKind.DAW_FACT,
            EvidenceKind.AUDIO_MEASUREMENT,
            EvidenceKind.USER_DECLARED_INTENT,
            EvidenceKind.USER_DECISION,
            EvidenceKind.SYSTEM_FACT,
            EvidenceKind.MEASURED_VALUE,
        }
        return {
            "song_id": song_id,
            "workspace_id": workspace_id,
            "known": [asdict(item) for item in scoped if item.kind in known_kinds],
            "thought": [asdict(item) for item in scoped if item.kind is EvidenceKind.INFERENCE],
            "unknown": [asdict(item) for item in scoped if item.kind is EvidenceKind.EAR_DECISION_REQUIRED],
        }

    def create_ear_decision(self, song_id, workspace_id, question, candidates=(), section="", evidence=()):
        row = {
            "id": uuid.uuid4().hex,
            "song_id": song_id,
            "workspace_id": workspace_id,
            "question": question,
            "section": section,
            "candidates": list(candidates),
            "evidence": list(evidence),
            "status": "OPEN",
            "created_at": time.time(),
        }
        self._mutate(lambda state: state["ear_decisions"].append(row) or row)
        self.events.append("EAR_DECISION_CREATED", song_id, workspace_id, data=row)
        return row

    def resolve_ear_decision(self, decision_id, choice):
        allowed = {"A", "B", "C", "CANT_TELL", "KEEP_ORIGINAL", "DECIDE_LATER"}
        if choice not in allowed:
            raise ValueError("Unsupported ear decision")

        def apply(state):
            row = next((item for item in state["ear_decisions"] if item["id"] == decision_id), None)
            if not row:
                raise ValueError("Ear decision not found")
            row.update(
                choice=choice,
                status="DEFERRED" if choice in {"CANT_TELL", "DECIDE_LATER"} else "RESOLVED",
                resolved_at=time.time(),
            )
            return row

        row = self._mutate(apply)
        self.events.append("EAR_DECISION_RESOLVED", row["song_id"], row["workspace_id"], data={"choice": choice})
        return row

    def add_version(self, song_id, workspace_id, label, parent_id="", status="ACTIVE", changes=()):
        def apply(state):
            if parent_id and not any(item["id"] == parent_id and item["song_id"] == song_id for item in state["versions"]):
                raise ValueError("Parent version is not in this Song")
            row = {
                "id": uuid.uuid4().hex,
                "song_id": song_id,
                "workspace_id": workspace_id,
                "label": label,
                "parent_id": parent_id,
                "status": status,
                "changes": list(changes),
                "created_at": time.time(),
            }
            state["versions"].append(row)
            return row

        return self._mutate(apply)

    def version_tree(self, song_id):
        rows = [item for item in self.load()["versions"] if item["song_id"] == song_id]
        return {"song_id": song_id, "versions": rows, "mutation_supported": False}

    def record_preference(self, song_id, subject, choice, explicit=False):
        def apply(state):
            prior = [item for item in state["preferences"] if item["subject"] == subject and item["choice"] == choice]
            level = "STRONG_PREFERENCE" if explicit else (
                "PATTERN" if len({item["song_id"] for item in prior}) >= 2 else "OBSERVATION"
            )
            row = {"song_id": song_id, "subject": subject, "choice": choice, "level": level, "explicit": explicit}
            state["preferences"].append(row)
            return row

        return self._mutate(apply)


def plan_job(intent, evidence, implementation, reason, authority, alternatives=()):
    steps = [
        {"action": "analyze evidence", "authority": "AUTOMATIC"},
        {"action": "create candidate preview", "authority": "PREVIEW"},
        {"action": "apply project change", "authority": authority},
    ]
    return {
        "job": intent,
        "intent": intent,
        "evidence": [asdict(item) for item in evidence],
        "plan": steps,
        "implementation_selected": implementation,
        "why": reason,
        "alternatives": list(alternatives),
        "authority": authority,
        "ear_decision": "REQUIRED",
        "applied": False,
    }


def what_if(question, result, evidence_kind=EvidenceKind.MODELED_VALUE):
    if evidence_kind not in {EvidenceKind.MEASURED_VALUE, EvidenceKind.MODELED_VALUE, EvidenceKind.INFERENCE}:
        raise ValueError("Simulation result must identify measured, modeled, or inferred evidence")
    return {"question": question, "result": result, "evidence_kind": evidence_kind.value, "applied": False}


def _evaluation_value(report: dict[str, Any], metric: str) -> float:
    if metric in {"true_dbtp", "lufs_i", "rms_dbfs", "sample_peak_dbfs"}:
        return float(report["levels"][metric])
    raise ValueError(f"Unsupported audition evaluation metric: {metric}")


def audition_candidates(original: AudioBuffer, candidates: dict[str, AudioBuffer], loudness_match=True,
                        evaluation_profile: dict[str, Any] | None = None):
    original_report = analyze(original)
    rows = {"ORIGINAL": {"buffer": original, "report": original_report, "gain_db": 0.0}}
    target_loudness = original_report["levels"]["lufs_i"]
    for name, candidate in candidates.items():
        report = analyze(candidate)
        gain_db = 0.0
        if loudness_match and target_loudness != float("-inf") and report["levels"]["lufs_i"] != float("-inf"):
            gain_db = target_loudness - report["levels"]["lufs_i"]
            candidate = Gain(gain_db).process(candidate)
            report = analyze(candidate)
        rows[name] = {"buffer": candidate, "report": report, "gain_db": gain_db}

    measurement_winner = None
    objective = None
    if evaluation_profile:
        metric = str(evaluation_profile.get("metric") or "")
        if "target" not in evaluation_profile:
            raise ValueError("Audition evaluation profile requires a target")
        target = float(evaluation_profile["target"])
        measurement_winner = min(
            rows,
            key=lambda name: abs(_evaluation_value(rows[name]["report"], metric) - target),
        )
        objective = {"metric": metric, "target": target}

    return {
        "candidates": rows,
        "measurement_winner": measurement_winner,
        "measurement_objective": objective,
        "user_winner": None,
        "approval_required": True,
        "source_overwritten": False,
    }


def mix_relationship(left_name, left: AudioBuffer, right_name, right: AudioBuffer):
    report = masking(left, right)
    overlaps = report.get("band_overlap", {})
    primary = max(overlaps, key=overlaps.get) if overlaps else ""
    return {
        "relationship": f"{left_name} ↔ {right_name}",
        "measurements": report,
        "primary_band": primary,
        "interpretation": "INFERENCE",
        "problem": None,
        "action_status": "EAR_DECISION_REQUIRED",
    }


def signal_view(nodes, routes, latency):
    diagnostics = []
    for node in nodes:
        if node.get("semantic_job") in (None, "UNKNOWN"):
            diagnostics.append({"node": node.get("id"), "issue": "UNVERIFIED_SEMANTICS"})
    return {
        "nodes": nodes,
        "routes": routes,
        "latency": {
            **latency,
            "evidence_kind": "MEASURED_VALUE" if latency.get("measured") else "MODELED_VALUE",
        },
        "diagnostics": diagnostics,
    }


def assess_portability(graph, target_host, installed_plugins=()):
    installed = set(installed_plugins)
    items = []
    for node in graph.nodes:
        plugin_id = node.data.get("plugin_id") if node.kind == "Device" else None
        if node.kind in {"AudioAsset", "MIDI", "Tempo", "Marker"}:
            status = "PORTABLE"
            reason = "universal Song representation"
        elif node.kind == "Device" and plugin_id:
            status = "PARTIALLY_PORTABLE" if plugin_id in installed else "UNKNOWN"
            reason = "target plugin installation is verified" if status == "PARTIALLY_PORTABLE" else "target plugin installation not verified"
        elif node.kind == "Device" and node.host_type and node.host_type != target_host:
            status = "HOST_SPECIFIC"
            reason = "source-host native device"
        elif node.kind in {"Routing", "Automation"}:
            status = "REQUIRES_GUIDED_MANUAL"
            reason = "host semantics require review"
        else:
            status = "UNKNOWN"
            reason = "no translation evidence"
        items.append({"node_id": node.id, "status": status, "reason": reason})
    actions = []
    if any(item["status"] in {"HOST_SPECIFIC", "UNKNOWN"} for item in items):
        actions.extend(["create reference render", "export stems", "capture plugin state receipts"])
    return {
        "song_id": graph.song_id,
        "workspace_id": graph.workspace_id,
        "target_host": target_host,
        "items": items,
        "migration_plan": actions,
        "translation_performed": False,
    }


@dataclass(frozen=True)
class MonitoringContext:
    output_device: str = "UNKNOWN"
    sample_rate: int | None = None
    buffer_frames: int | None = None
    medium: str = "UNKNOWN"
    mono: bool = False
    room_correction_state: str = "UNKNOWN"
    evidence_kind: EvidenceKind = EvidenceKind.USER_DECLARED_INTENT


def capability_health(capabilities):
    states = {str(value.get("status", "UNKNOWN")).upper() for value in capabilities.values()}
    if states & {"FAILED", "UNAVAILABLE"}:
        overall = "DEGRADED"
    elif states & {"DEGRADED", "RECOVERING", "PAUSED", "BUSY", "UNKNOWN"}:
        overall = "DEGRADED"
    else:
        overall = "HEALTHY"
    return {"overall": overall, "capabilities": capabilities, "capability_scoped": True}


def authority_view():
    return {
        "view_type": "POLICY_SUMMARY_NOT_RUNTIME_AUTHORITY",
        "analyze_local_audio": "AUTHORIZED",
        "external_audio_render": "OUTPUT_AUTHORITY",
        "daw_project_mutation": "GATE_1",
        "publication": "EXPLICIT_PUBLICATION_AUTHORITY",
        "community_mutation": "BLOCKED",
        "guided_manual": "MANUAL",
    }


def deliver(source_path, output_path, candidate, song_id, workspace_id, parent_version,
            processor_receipt, specification: RenderSpecification, output_authority=False,
            analysis_before: dict[str, Any] | None = None):
    before = analysis_before or {
        "status": "UNAVAILABLE",
        "reason": "source analysis was not supplied to the delivery operation",
    }
    return render_external(
        source_path,
        output_path,
        candidate,
        song_id,
        parent_version,
        processor_receipt,
        output_authority,
        specification,
        workspace_id=workspace_id,
        analysis_before=before,
        analysis_after=analyze(candidate),
    )


def archive_manifest(song_id, workspaces, versions, render_receipts, plugin_inventory, decisions, missing=()):
    return {
        "schema": 1,
        "song_id": song_id,
        "workspaces": list(workspaces),
        "versions": list(versions),
        "render_receipts": list(render_receipts),
        "plugin_inventory": list(plugin_inventory),
        "decisions": list(decisions),
        "missing_dependencies": list(missing),
        "bundles_third_party_software": False,
    }
