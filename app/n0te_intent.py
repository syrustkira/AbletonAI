from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any


class ExecutionTier(str, Enum):
    INFORMATION_ONLY = "INFORMATION_ONLY"
    GUIDED_MANUAL = "GUIDED_MANUAL"
    SEMI_AUTOMATIC = "SEMI_AUTOMATIC"
    APPROVAL_GATED = "APPROVAL_GATED"
    DETERMINISTIC_NATIVE = "DETERMINISTIC_NATIVE"


@dataclass(frozen=True)
class JobRequirement:
    capability: str
    required: bool = True
    evidence: str = "OBSERVED"


@dataclass(frozen=True)
class Job:
    intent: str
    goal: str
    requirements: tuple[JobRequirement, ...] = ()


@dataclass(frozen=True)
class GuidedManualPlan:
    goal: str
    technical_job: str
    target: str
    reason: str
    steps: tuple[str, ...]
    evidence: str = "UNKNOWN"
    observe_afterward: str = "Refresh N0TE and verify the resulting Live state."
    state: str = "CONTINUE"


@dataclass
class ExecutionPlan:
    job: Job
    tier: ExecutionTier
    message: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    manual: GuidedManualPlan | None = None

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["tier"] = self.tier.value
        return value


def _action(kind: str, **values: Any) -> dict[str, Any]:
    action = {"kind": kind, "track_index": 0, "send_index": 0, "target_id": 0, "parameter": "",
              "string_value": "", "number_value": 0.0, "number_value_2": 0.0, "bool_value": False,
              "reason": "Explicit deterministic user command", "risk": "low"}
    action.update(values)
    return action


class IntentRouter:
    """Conservative producer-language routing for AI-OFF operation."""

    def route(self, text: str, snapshot: dict[str, Any], song_state: dict[str, Any] | None = None) -> ExecutionPlan:
        raw = " ".join(str(text or "").strip().split())
        lower = raw.lower()
        selected = snapshot.get("selected_track_summary") or {}
        track_index = selected.get("index")
        if lower in {"status", "what is the status", "show status"} or "health" in lower:
            return ExecutionPlan(Job("status", "Inspect N0TE and Ableton availability"), ExecutionTier.INFORMATION_ONLY,
                                 "Status is available in N0TE Health/Diagnostics. No mutation was requested.")
        if (any(term in lower for term in ("inspect", "show", "what", "which")) and
                any(term in lower for term in ("selected track", "selection", "what track"))):
            name = selected.get("name") or "No resolvable selected track"
            device = snapshot.get("selected_device") or snapshot.get("song", {}).get("properties", {}).get("appointed_device") or {}
            return ExecutionPlan(Job("selection", "Inspect current selection"), ExecutionTier.INFORMATION_ONLY,
                                 f"Selected track: {name}. Selected device: {device.get('name') or 'none exposed'}.")
        if "midi" in lower and any(term in lower for term in ("inspect", "selected", "notes", "show")):
            notes = (snapshot.get("selected_clip_notes") or {}).get("notes") or []
            return ExecutionPlan(Job("selected_midi", "Inspect selected MIDI", (JobRequirement("daw.selected_midi"),)),
                                 ExecutionTier.INFORMATION_ONLY, f"Selected MIDI contains {len(notes)} exposed note(s).")
        if any(term in lower for term in ("song goal", "song context", "session goal")):
            state = song_state or {}
            return ExecutionPlan(Job("song_context", "Inspect Song context"), ExecutionTier.INFORMATION_ONLY,
                                 f"Song intent: {state.get('song_intent') or 'not set'}. Session goal: {state.get('session_goal') or 'not set'}.")
        if "undo n0te" in lower or lower == "undo":
            return ExecutionPlan(Job("undo_n0te", "Undo the latest safe N0TE transaction"), ExecutionTier.GUIDED_MANUAL,
                                 "Undo remains a separate explicit authority action. Use Undo N0TE; it will revalidate ownership and recovery safety.",
                                 manual=GuidedManualPlan("Undo the latest N0TE change", "Revalidated targeted recovery", "N0TE Undo",
                                    "Chat text is not treated as approval for recovery execution.", ("Review the latest transaction.", "Press Undo N0TE.", "Review the restored state."), "OBSERVED"))
        tempo = re.fullmatch(r"(?:set|change) (?:the )?tempo (?:to )?(\d+(?:\.\d+)?)\s*(?:bpm)?", lower)
        if tempo:
            return ExecutionPlan(Job("set_tempo", raw, (JobRequirement("daw.set_tempo"),)), ExecutionTier.APPROVAL_GATED,
                                 f"Propose setting tempo to {tempo.group(1)} BPM.", [_action("set_tempo", number_value=float(tempo.group(1)))])
        rename = re.fullmatch(r"rename (?:the )?(?:selected )?track (?:to )?(.+)", raw, re.I)
        if rename and isinstance(track_index, int):
            return ExecutionPlan(Job("rename_track", raw, (JobRequirement("daw.rename_track"),)), ExecutionTier.APPROVAL_GATED,
                                 f"Propose renaming the selected track to {rename.group(1)}.", [_action("rename_track", track_index=track_index, string_value=rename.group(1))])
        toggle = re.fullmatch(r"(mute|unmute|solo|unsolo|arm|disarm) (?:the )?(?:selected )?track", lower)
        if toggle and isinstance(track_index, int):
            word = toggle.group(1); base = word.removeprefix("un").removeprefix("dis")
            kind = {"mute": "set_track_mute", "solo": "set_track_solo", "arm": "set_track_arm"}[base]
            enabled = word in {"mute", "solo", "arm"}
            return ExecutionPlan(Job(kind, raw, (JobRequirement("daw." + kind),)), ExecutionTier.APPROVAL_GATED,
                                 f"Propose {word} on the selected track.", [_action(kind, track_index=track_index, bool_value=enabled)])
        if any(term in lower for term in ("route", "sidechain", "audio input", "audio output")):
            manual = GuidedManualPlan(raw, "Configure unsupported Live routing", "Ableton Live",
                                      "The current validated action schema does not expose this routing mutation safely.",
                                      ("Open the selected track's Input/Output section.", "Choose the intended source and destination.",
                                       "Refresh N0TE and verify the exposed routing/state before continuing."), "UNKNOWN")
            return ExecutionPlan(Job("guided_routing", raw), ExecutionTier.GUIDED_MANUAL,
                                 "This job is a successful Guided Manual outcome rather than an unsafe automated mutation.", manual=manual)
        return ExecutionPlan(Job("clarify", raw or "empty command"), ExecutionTier.GUIDED_MANUAL,
                             "I cannot safely infer one deterministic operation from that command.",
                             choices=["Inspect status", "Inspect selection", "Open the relevant N0TE view", "Describe one exact target and value"])
