from __future__ import annotations

import json
import base64
import logging
import math
from logging.handlers import RotatingFileHandler
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get("N0TE_STATE_DIR") or (Path.home() / ".n0te-ableton-ai"))
STATE.mkdir(parents=True, exist_ok=True)
STATIC = HERE / "static"
sys.path.insert(0, str(HERE))

from n0te_bridge import AbletonBridge
from n0te_context import ContextStore, context_for_prompt
from n0te_core import (
    action_schema,
    capture_inverse,
    execute_action,
    latest_transaction,
    list_transactions,
    make_transaction,
    save_transaction,
    validate_action,
    is_track_targeted_action,
)
from n0te_library import LibraryIndex, current_set_devices, resolve_tools
from n0te_discovery import discover, extract_discovery_intent
from n0te_project import ProjectStore, finish_checklist
from n0te_state import atomic_write_json
from n0te_doctor import remote_script_doctor
from n0te_provider import provider_status
from n0te_network import NetworkPolicy
from n0te_intent import IntentRouter
from n0te_safety import SafetyController
from n0te_services import CreatorService, DawManagementService
from n0te_daw_discovery import AdapterInstallation, DawDiscoveryService
from n0te_capabilities import ComponentState
from n0te_macos import MacOSApplicationDiscovery
from n0te_media import MockStreamBackend
from n0te_audio import read_wav, analyze, diagnose
from n0te_plugins import PluginScanProcess
import tempfile

APP_VERSION = "1.2.4"
HOST = "127.0.0.1"
PORT = 8766
KEYCHAIN_SERVICE = "N0TE_Ableton_AI_OpenAI"
CONFIG_PATH = STATE / "config.json"
SECRET_PATH = STATE / "secrets.json"

_diagnostic_log = logging.getLogger("n0te.diagnostics")
if not _diagnostic_log.handlers:
    log_dir = Path(os.environ.get("N0TE_LOG_DIR") or STATE);log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "diagnostics.log", maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _diagnostic_log.addHandler(handler)
    _diagnostic_log.setLevel(logging.INFO)

bridge = AbletonBridge()
context_store = ContextStore(HERE / "context" / "N0TE_CONTEXT_PACK.json", STATE)
library = LibraryIndex(STATE)
projects = ProjectStore(STATE)
intent_router = IntentRouter()
safety = SafetyController(STATE)
creator_service = CreatorService(STATE, safety, MockStreamBackend())
_mac_metadata = MacOSApplicationDiscovery() if sys.platform == "darwin" else None
daw_service = DawManagementService(DawDiscoveryService(adapters={"ABLETON_ADAPTER": AdapterInstallation("ABLETON_ADAPTER", True, APP_VERSION, ComponentState.READY, ComponentState.READY, True, False)}, metadata_backend=_mac_metadata), STATE / "first_run.json")
proposals: dict[str, dict[str, Any]] = {}
simplify_proposals: dict[str, dict[str, Any]] = {}
_snapshot_lock = threading.Lock()

def audio_summary(report):
    def safe(item):
        if isinstance(item,float) and not math.isfinite(item):return None
        if isinstance(item,dict):return {key:safe(value) for key,value in item.items()}
        if isinstance(item,list):return [safe(value) for value in item]
        return item
    value=safe(report)
    value["levels"].pop("momentary_series",None);value["levels"].pop("short_term_series",None)
    value["spectrum"].pop("bins",None)
    return value

def plugin_roots():
    if sys.platform=="darwin":return [Path.home()/"Library/Audio/Plug-Ins","/Library/Audio/Plug-Ins"]
    if os.name=="nt":return [Path(os.environ.get("COMMONPROGRAMFILES",r"C:\Program Files\Common Files"))/"VST3",Path(os.environ.get("LOCALAPPDATA",Path.home()))/"Programs/Common/VST3"]
    return [Path.home()/".vst3",Path.home()/".clap","/usr/lib/vst3","/usr/local/lib/vst3","/usr/lib/clap"]
_mutation_lock = threading.RLock()
_proposal_lock = threading.RLock()
PROPOSAL_TTL_SECONDS = 15 * 60
MAX_REQUEST_BODY = 1024 * 1024
_snapshot_cache: dict[str, Any] = {"at": 0.0, "value": None}


def load_config() -> dict[str, Any]:
    config = {
        "model": "gpt-5.6",
        "mode": "produce",
        "context_sync_path": "",
        "auto_refresh_seconds": 5,
        "ai_provider": "openai",
        "network_mode": "full",
        "community_enabled": False,
        "automatic_update_checking": True,
        "automatic_safe_install": True,
        "update_channel": "STABLE",
    }
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config.update(loaded)
        except Exception:
            pass
    return config


def save_config(config: dict[str, Any]) -> None:
    atomic_write_json(CONFIG_PATH, config)


def load_secrets() -> dict[str, str]:
    try:
        value = json.loads(SECRET_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
    except Exception:
        pass
    return {}


def store_secret(name: str, value: str) -> None:
    value = str(value or "").strip()
    if not value:
        return
    secrets = load_secrets()
    secrets[name] = value
    atomic_write_json(SECRET_PATH, secrets, mode=0o600)
    try:
        SECRET_PATH.chmod(0o600)
    except Exception:
        pass


def get_secret(name: str) -> str:
    env_name = {
        "freesound_api_key": "FREESOUND_API_KEY",
        "openverse_token": "OPENVERSE_API_TOKEN",
    }.get(name, "")
    if env_name and os.environ.get(env_name):
        return str(os.environ.get(env_name) or "").strip()
    return load_secrets().get(name, "").strip()


def get_api_key() -> str:
    env = os.environ.get("OPENAI_API_KEY")
    if env:
        return env.strip()
    if sys.platform == "darwin":
        try:
            cp = subprocess.run(
                ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=3,
            )
            if cp.returncode == 0:
                return cp.stdout.strip()
        except Exception:
            pass
    key_file = STATE / "api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return ""


def store_api_key(key: str) -> None:
    key = key.strip()
    if not key:
        return
    if sys.platform == "darwin":
        cp = subprocess.run(
            ["security", "add-generic-password", "-U", "-a", os.environ.get("USER", ""), "-s", KEYCHAIN_SERVICE, "-w", key],
            capture_output=True, text=True,
        )
        if cp.returncode == 0:
            return
    key_file = STATE / "api_key"
    key_file.write_text(key, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except Exception:
        pass


def selected_context(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    selected = snapshot.get("view", {}).get("properties", {}).get("selected_track")
    if not (isinstance(selected, dict) and selected.get("id")):
        return None
    sid = selected["id"]
    groups = [
        ("track", snapshot.get("set", {}).get("tracks") or []),
        ("return", snapshot.get("set", {}).get("return_tracks") or []),
    ]
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        groups.append(("master", [master]))
    for group, tracks in groups:
        for t in tracks:
            if isinstance(t, dict) and t.get("id") == sid:
                row = dict(t)
                row["_track_group"] = group
                return row
    return None


def selected_track_ref(snapshot: dict[str, Any]) -> tuple[str, int | None, str] | None:
    selected = selected_context(snapshot)
    if not selected:
        return None
    group = str(selected.get("_track_group") or "track")
    index = selected.get("index") if isinstance(selected.get("index"), int) else None
    if group == "track" and index is not None:
        return f"live_set tracks {index}", index, group
    if group == "return" and index is not None:
        return f"live_set return_tracks {index}", index, group
    if group == "master":
        return "live_set master_track", None, group
    return None


def selected_track_index(snapshot: dict[str, Any]) -> int | None:
    ref = selected_track_ref(snapshot)
    return ref[1] if ref and ref[2] == "track" else None


def get_snapshot(force: bool = False) -> dict[str, Any]:
    with _snapshot_lock:
        if not force and _snapshot_cache["value"] is not None and time.time() - _snapshot_cache["at"] < 2.0:
            return _snapshot_cache["value"]
        ping = bridge.request("ping", {"timeout": 3})
        summary = bridge.request("set_summary", {
            "track_limit": 96,
            "clip_slot_limit": 16,
            "device_limit": 32,
            "arrangement_clip_limit": 80,
            "include_return_tracks": True,
            "include_master_track": True,
            "max_depth": 6,
            "max_items": 500,
            "timeout": 10,
        })
        song = bridge.request("get", {
            "ref": {"path": "live_set"},
            "properties": [
                "file_path", "tempo", "current_song_time", "is_playing", "can_undo", "can_redo",
                "appointed_device", "loop", "loop_start", "loop_length"
            ],
            "max_depth": 4, "timeout": 5,
        })
        view = bridge.request("get", {
            "ref": {"path": "live_set view"},
            "properties": ["selected_track", "selected_parameter", "detail_clip"],
            "max_depth": 4, "timeout": 5,
        })
        snap = {"ping": ping, "set": summary, "song": song, "view": view}
        detail_clip = view.get("properties", {}).get("detail_clip")
        if isinstance(detail_clip, dict) and detail_clip.get("id"):
            try:
                snap["selected_clip_notes"] = bridge.request("clip_notes", {
                    "ref": {"id": detail_clip["id"]}, "limit": 256, "timeout": 6,
                })
            except Exception as exc:
                # Audio clips/non-MIDI clips legitimately fail clip_notes. Preserve that as context rather than a health error.
                snap["selected_clip_notes_error"] = str(exc)
        appointed = song.get("properties", {}).get("appointed_device")
        if isinstance(appointed, dict) and appointed.get("id"):
            try:
                snap["appointed_device_parameters"] = bridge.request("device_parameters", {
                    "ref": {"id": appointed["id"]}, "limit": 96, "timeout": 5,
                })
            except Exception as exc:
                snap["appointed_device_parameters_error"] = str(exc)
        st = selected_context(snap)
        if st:
            snap["selected_track_summary"] = st
            track_ref = selected_track_ref(snap)
            if track_ref:
                try:
                    track_view = bridge.request("get", {
                        "ref": {"path": track_ref[0] + " view"},
                        "properties": ["selected_device"], "max_depth": 4, "timeout": 5,
                    })
                    selected_device = track_view.get("properties", {}).get("selected_device")
                    if isinstance(selected_device, dict) and selected_device.get("id"):
                        snap["selected_device"] = selected_device
                        try:
                            snap["selected_device_parameters"] = bridge.request("device_parameters", {
                                "ref": {"id": selected_device["id"]}, "limit": 128, "timeout": 6,
                            })
                        except Exception as exc:
                            snap["selected_device_parameters_error"] = str(exc)
                        try:
                            meta = bridge.request("get", {
                                "ref": {"id": selected_device["id"]},
                                "properties": ["is_active", "latency_in_ms", "latency_in_samples", "class_name", "class_display_name", "type", "can_have_chains"],
                                "timeout": 5,
                            })
                            snap["selected_device_meta"] = meta.get("properties") or {}
                        except Exception:
                            pass
                except Exception as exc:
                    snap["selected_device_error"] = str(exc)
        _snapshot_cache["at"] = time.time()
        _snapshot_cache["value"] = snap
        return snap


def invalidate_snapshot() -> None:
    with _snapshot_lock:
        _snapshot_cache["at"] = 0.0
        _snapshot_cache["value"] = None


def compact_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    result = {
        "ableton": snap.get("ping"),
        "song": snap.get("song"),
        "view": snap.get("view"),
        "set": snap.get("set"),
    }
    if "appointed_device_parameters" in snap:
        result["appointed_device_parameters"] = snap["appointed_device_parameters"]
    if "selected_clip_notes" in snap:
        result["selected_clip_notes"] = snap["selected_clip_notes"]
    if "selected_clip_notes_error" in snap:
        result["selected_clip_notes_error"] = snap["selected_clip_notes_error"]
    for key in ("selected_device", "selected_device_parameters", "selected_device_meta", "selected_device_parameters_error", "selected_device_error"):
        if key in snap:
            result[key] = snap[key]
    return result


class ConflictError(RuntimeError):
    """Current Live evidence no longer matches an approved operation."""


class DependencyUnavailableError(RuntimeError):
    """A required local or network dependency is unavailable."""


def cleanup_proposals(now: float | None = None) -> None:
    cutoff = (now or time.time()) - PROPOSAL_TTL_SECONDS
    with _proposal_lock:
        for registry in (proposals, simplify_proposals):
            for key in [key for key, value in registry.items() if value.get("created_at") is not None and float(value.get("created_at")) < cutoff]:
                registry.pop(key, None)


def _proposal_get(registry: dict[str, dict[str, Any]], proposal_id: str) -> dict[str, Any] | None:
    with _proposal_lock:
        return registry.get(proposal_id)


def _all_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        result.append(device)
        children = device.get("devices") or device.get("nested_devices") or []
        result.extend(_all_devices(children if isinstance(children, list) else []))
        for chain in device.get("chains") or []:
            if isinstance(chain, dict):
                result.extend(_all_devices(chain.get("devices") or []))
    return result


def affected_target_evidence(actions: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = [t for group in ("tracks", "return_tracks") for t in snapshot.get("set", {}).get(group) or [] if isinstance(t, dict)]
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        tracks.append(master)
    evidence = []
    for action in actions:
        row: dict[str, Any] = {"kind": action.get("kind"), "target_id": action.get("target_id")}
        idx = action.get("track_index")
        track = next((t for t in tracks if t.get("index") == idx), None)
        if track and is_track_targeted_action(action):
            row.update({"object_type": "track", "object_id": track.get("id"), "track_index": idx, "name_before": track.get("name")})
        target_id = action.get("target_id")
        if target_id:
            devices = [d for t in tracks for d in _all_devices(t.get("devices") or [])]
            device = next((d for d in devices if d.get("id") == target_id), None)
            clips = [c for t in tracks for c in ((t.get("clips") or []) + (t.get("arrangement_clips") or [])) if isinstance(c, dict)]
            target = device or next((c for c in clips if c.get("id") == target_id), None)
            if target:
                row.update({"object_type": "device" if device else "clip", "object_id": target_id, "name_before": target.get("name"), "class_name": target.get("class_name", "")})
        evidence.append(row)
    return evidence


def _same_action_value(current: dict[str, Any], intended: dict[str, Any]) -> bool:
    kind = intended.get("kind")
    keys = {
        "rename_track": ("string_value",), "set_clip_name": ("string_value",),
        "set_track_mute": ("bool_value",), "set_track_solo": ("bool_value",),
        "set_track_arm": ("bool_value",), "set_device_active": ("bool_value",),
        "set_clip_muted": ("bool_value",), "set_track_pan": ("number_value",),
        "set_track_volume": ("number_value",), "set_send_level": ("number_value",),
        "set_tempo": ("number_value",), "set_device_parameter": ("number_value",),
        "set_arrangement_loop": ("bool_value", "number_value", "number_value_2"),
        "update_midi_clip_notes": ("string_value",),
    }.get(kind, ())
    if kind == "update_midi_clip_notes":
        try:
            wanted = {r["note_id"]: r for r in json.loads(intended["string_value"])}
            actual = {r["note_id"]: r for r in json.loads(current["string_value"])}
            return all(all(actual.get(nid, {}).get(k) == value for k, value in row.items() if k != "note_id") for nid, row in wanted.items())
        except Exception:
            return False
    def same(left: Any, right: Any) -> bool:
        if isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
            return math.isclose(float(left), float(right), rel_tol=1e-6, abs_tol=1e-5)
        return left == right
    return bool(keys) and all(same(current.get(key), intended.get(key)) for key in keys)


def recovery_conflicts(live_bridge, tx: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    evidence = tx.get("affected_targets") or []
    tracks = snapshot.get("set", {}).get("tracks") or []
    errors = []
    for row in evidence:
        if row.get("object_type") == "track":
            match = next((t for t in tracks if t.get("id") == row.get("object_id")), None)
            if not match:
                errors.append(f"track target {row.get('object_id')} no longer matches")
    for position, action in enumerate(tx.get("actions") or []):
        if is_track_targeted_action(action):
            row = evidence[position] if position < len(evidence) else {}
            if row.get("object_type") != "track" or row.get("object_id") is None:
                errors.append(f"track ownership evidence missing for {action.get('kind')}")
                continue
        try:
            current = capture_inverse(live_bridge, action)
            if not _same_action_value(current, action):
                errors.append(f"affected target for {action.get('kind')} changed incompatibly")
        except Exception as exc:
            errors.append(f"cannot revalidate {action.get('kind')}: {exc}")
    return errors


def reresolve_transaction_tracks(tx: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    """Rewrite volatile track indexes from journaled stable Track IDs."""
    tracks = snapshot.get("set", {}).get("tracks") or []
    errors = []
    evidence = tx.get("affected_targets") or []
    for position, row in enumerate(evidence):
        if row.get("object_type") != "track" or row.get("object_id") is None:
            continue
        match = next((track for track in tracks if track.get("id") == row["object_id"]), None)
        if not match or not isinstance(match.get("index"), int):
            errors.append(f"track target {row['object_id']} is no longer resolvable")
            continue
        for key in ("actions", "inverse_actions", "post_actions"):
            actions = tx.get(key) or []
            if position < len(actions) and is_track_targeted_action(actions[position]):
                actions[position]["track_index"] = match["index"]
        row["track_index"] = match["index"]
    return errors


def extract_output_text(response: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text" and part.get("text"):
                texts.append(part["text"])
    return "\n".join(texts).strip()


def openai_structured(instructions: str, user_text: str, schema_name: str, schema: dict[str, Any], max_output_tokens: int = 2600) -> dict[str, Any]:
    NetworkPolicy.from_value(load_config().get("network_mode", "full")).require("https://api.openai.com/v1/responses")
    key = get_api_key()
    if not key:
        raise DependencyUnavailableError("OpenAI API key is not configured. Open Settings and save a project API key.")
    model = load_config().get("model") or "gpt-5.6"
    payload = {
        "model": model,
        "store": False,
        "reasoning": {"effort": "low" if load_config().get("mode") == "produce" else "medium"},
        "instructions": instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
        "text": {
            "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True},
            "verbosity": "medium",
        },
        "max_output_tokens": max_output_tokens,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenAI API error {exc.code}: {detail[:900]}")
    text = extract_output_text(raw)
    if not text:
        raise RuntimeError("OpenAI returned no structured output.")
    return json.loads(text)


def looks_like_sound_discovery(text: str) -> bool:
    value = str(text or "").lower()
    intent = any(token in value for token in ("find ", "search ", "look for", "looking for", "need a ", "need an ", "more like this", "similar sound", "similar sample", "complement this"))
    sound_terms = (
        "sample", "sound", "loop", "one shot", "one-shot", "kick", "snare", "clap", "hat", "percussion",
        "impact", "riser", "sweep", "texture", "fx", "foley", "vocal chop", "guitar", "drum", "bass shot",
        "ambience", "atmosphere", "noise", "hit"
    )
    return bool(intent and any(term in value for term in sound_terms))


def looks_like_tool_question(text: str) -> bool:
    value = str(text or "").lower()
    terms = ("plugin", "device", "rack", "chain", "tool", "ableton do", "native", "what is this", "what does this", "do i have", "do i own", "simplify", "replace", "latency", "overhead")
    return any(term in value for term in terms)


def ask_openai(user_text: str, snap: dict[str, Any]) -> dict[str, Any]:
    if str(load_config().get("ai_provider") or "openai").lower() in {"off", "none"}:
        raise DependencyUnavailableError("AI is intentionally OFF. Status, project, history, diagnostics, Apply, and Undo remain available.")
    config = load_config()
    context_pack = context_store.load(config.get("context_sync_path") or "")
    song_state = projects.load_song(snap)
    tool_context = resolve_tools(user_text, library, snap, bridge=bridge, deep=looks_like_tool_question(user_text))
    discovery_context = None
    if looks_like_sound_discovery(user_text):
        try:
            discovery_context = discover(
                user_text, bridge, library, snap, include_web=True,
                openverse_token=get_secret("openverse_token"),
                freesound_key=get_secret("freesound_api_key"),
                web_threshold=6, network_policy=NetworkPolicy.from_value(config.get("network_mode")),
            )
        except Exception as exc:
            discovery_context = {"error": str(exc), "query": user_text}
    _, recent_tx = latest_transaction(STATE, projects.song_key(snap))
    recent_change = None
    if recent_tx:
        recent_change = {
            "label": recent_tx.get("label"),
            "created_at": recent_tx.get("created_at"),
            "actions": recent_tx.get("actions") or [],
            "inverse_actions": recent_tx.get("inverse_actions") or [],
        }
    discovery_history = projects.list_discovery(snap, 20)
    recent = projects.list_conversation(snap, 12)
    history_text = "\n".join(f"{str(x.get('role') or 'user').upper()}: {str(x.get('text') or '')}" for x in recent)

    mode = str(config.get("mode") or "produce").lower()
    mode_rule = (
        "PRODUCE MODE: lead with the smallest useful action and keep explanation concise unless asked."
        if mode == "produce" else
        "TEACH MODE: explain the reasoning, Ableton mechanism, alternatives, and tradeoffs while still giving a concrete next action."
    )
    instructions = f"""You are N0TE, an Ableton Live production copilot and production-memory system.
You are looking at a machine-readable snapshot of the user's CURRENT Live Set.

CANONICAL TELLMEN0TE CONTEXT:
{context_for_prompt(context_pack)}

CURRENT SONG STATE:
{json.dumps(song_state, ensure_ascii=False, separators=(',', ':'))}

{mode_rule}

PRIMARY COPRODUCER LOOP:
- Natural language is the main interface: ANALYZE -> CONSULT -> PROPOSE -> IMPLEMENT after approval -> REVIEW with the user -> KEEP / ADJUST / UNDO.
- Infer whether the user is asking to ASK/read, ADVISE, TRY/experiment, or DO. Do not require manual mode switching.
- When the user comments on a recent edit (for example “better but thinner”), use RECENT N0TE CHANGE to understand exactly what was changed.
- Challenge a requested technical solution when the evidence points to a different musical bottleneck, while still leaving the user in control.

KNOWLEDGE PLANE VS ACTION PLANE:
- Your knowledge surface should be broad: Ableton capabilities, commands/workflows, currently used devices, scanned plugin/rack library, and production reasoning.
- Your execution surface is intentionally narrow and approval-gated.
- If the user asks whether Live can do something or whether they already own a tool for it, answer from TOOL CONTEXT and explicitly distinguish: already in set, Ableton-native, already owned, or not established.
- If DISCOVERY CONTEXT is present, use those actual search results. Prefer local/current-Set results first. Do not invent a web result or claim a license beyond the returned metadata.
- Prefer solutions in this order: ALREADY IN SET -> ABLETON NATIVE -> ALREADY OWNED PLUGIN/RACK -> N0TE EXTENSION only for a missing capability -> WEB/EXTERNAL/NEW only when genuinely justified.
- 'Simple' means least unnecessary complexity that preserves musical intent. Do not automatically replace a sophisticated plugin if its sophisticated capability is actually being used.
- Never pretend two processors are equivalent merely because they share a category.

STAGE AWARENESS:
- CREATE: emotion, hook, composition, performance; discourage mastering rabbit holes.
- ARRANGE: section roles, contrast, development, ending.
- PRODUCE: sound selection and intentional texture after the song works.
- MIX: balance, masking, dynamics, space, translation.
- MASTER: delivery and loudness after mix decisions are stable.
- FINISH: identify the minimum remaining work required to produce a complete bounce; resist unnecessary new experiments.

SAFETY / ACTION CONTRACT:
- Advice is free; edits must only use the allowed action schema.
- Actions are proposals. The local app will not execute until the user presses Apply.
- Never propose deletion, destructive replacement, file deletion, plugin purchase, recording, or arbitrary code.
- Prefer 0-3 high-leverage actions.
- Tie every edit to a stated musical reason.
- Do not claim you heard audio. Use needs_audio when tone/balance/dynamics/performance requires actual audio evidence.
- Object ids and track indices must come from the supplied snapshot.
- Raw mixer volume/send values are 0..1; do not claim those numbers are dB.
- For set_arrangement_loop: number_value=start beats, number_value_2=length beats, bool_value=enabled.
- For update_midi_clip_notes: only edit the currently selected/detail MIDI clip; target_id is that clip id; string_value is a JSON list of note updates using existing note_id values. Preserve requested constraints (rhythm, harmony, motif, etc.) and change only what is needed. Maximum 128 note updates per proposal.
- Native Ableton features should be orchestrated rather than redundantly rebuilt.
- If the user asks a knowledge question, actions may be empty.

EVIDENCE DISCIPLINE:
Use evidence_labels to distinguish Live-state fact, audio measurement, inference, and an ear decision. Do not dress inference up as fact.
"""

    user_payload = (
        "CURRENT LIVE SET SNAPSHOT:\n" + json.dumps(compact_snapshot(snap), separators=(",", ":")) +
        "\n\nTOOL / CAPABILITY CONTEXT FOR THIS QUESTION:\n" + json.dumps(tool_context, ensure_ascii=False, separators=(",", ":")) +
        "\n\nDISCOVERY CONTEXT (only populated for sound-search intent):\n" + json.dumps(discovery_context, ensure_ascii=False, separators=(",", ":")) +
        "\n\nRECENT N0TE CHANGE (if any):\n" + json.dumps(recent_change, ensure_ascii=False, separators=(",", ":")) +
        "\n\nRECENT DISCOVERY / TRIED-HERE MEMORY:\n" + json.dumps(discovery_history, ensure_ascii=False, separators=(",", ":")) +
        ("\n\nRECENT LOCAL CHAT:\n" + history_text if history_text else "") +
        "\n\nUSER:\n" + user_text
    )
    result = openai_structured(instructions, user_payload, "n0te_ableton_reply", action_schema(), 2800)
    valid, rejected = [], []
    for action in result.get("actions") or []:
        ok, reason = validate_action(action, snap)
        if ok:
            valid.append(action)
        else:
            rejected.append({"action": action, "reason": reason})
    result["actions"] = valid
    if rejected:
        result["rejected_actions"] = rejected
    if discovery_context:
        result["_discovery"] = discovery_context
    return result


def deterministic_reply(user_text: str, snap: dict[str, Any]) -> dict[str, Any]:
    plan = intent_router.route(user_text, snap, projects.load_song(snap))
    return {
        "message": plan.message,
        "decision_summary": plan.job.goal,
        "actions": plan.actions,
        "execution_plan": plan.payload(),
        "evidence": ["Deterministic AI-OFF intent routing; no model provider was invoked."],
        "needs_audio": False,
    }


def apply_proposal(proposal_id: str) -> dict[str, Any]:
    with _mutation_lock:
        safety.require_mutation_authority()
        cleanup_proposals()
        prop = _proposal_get(proposals, proposal_id)
        if not prop:
            raise LookupError("Unknown or expired proposal.")
        current = get_snapshot(force=True)
        expected = prop["signature"]
        actual = current["set"].get("set_signature")
        current_key = projects.song_key(current)
        if prop.get("song_key") and prop["song_key"] != current_key:
            raise ConflictError("The proposal belongs to another Live Set.")
        if expected != actual:
            raise ConflictError("The Live Set changed since this proposal was created. Refresh/re-analyze before applying.")
        actions = prop["reply"].get("actions") or []
        if not actions:
            return {"ok": True, "message": "No actions to apply.", "results": []}
        # Track indexes are volatile. When proposal-time evidence retained a
        # stable exposed Track id, resolve its current index immediately before
        # validation/execution rather than trusting the old raw index.
        proposed_targets = prop.get("affected_targets") or []
        current_tracks = current.get("set", {}).get("tracks") or []
        for position, action in enumerate(actions):
            evidence = proposed_targets[position] if position < len(proposed_targets) else {}
            if is_track_targeted_action(action) and evidence.get("object_type") == "track" and evidence.get("object_id") is not None:
                match = next((t for t in current_tracks if t.get("id") == evidence["object_id"]), None)
                if not match or not isinstance(match.get("index"), int):
                    raise ConflictError(f"Approved track target {evidence['object_id']} is no longer resolvable.")
                action["track_index"] = match["index"]
        for action in actions:
            ok, reason = validate_action(action, current)
            if not ok:
                raise ConflictError(f"Fresh Apply validation failed: {reason}")
        targets = affected_target_evidence(actions, current)
        inverses = [capture_inverse(bridge, action) for action in actions]
        results = []
        try:
            for action in actions:
                result = execute_action(bridge, action, expected if not results else None)
                results.append(result)
        except Exception as exc:
            rollback_errors = []
            for inverse in reversed(inverses[:len(results)]):
                try:
                    execute_action(bridge, inverse, None)
                except Exception as rb_exc:
                    rollback_errors.append(str(rb_exc))
            invalidate_snapshot()
            detail = f"Proposal failed after {len(results)} action(s): {exc}"
            if rollback_errors:
                detail += " | rollback errors: " + "; ".join(rollback_errors)
            raise RuntimeError(detail)
        props = current.get("song", {}).get("properties", {})
        tx = make_transaction(
            actions, inverses, expected, results,
            label=prop["reply"].get("decision_summary") or "N0TE edit",
            song_key=current_key, set_path=str(props.get("file_path") or ""),
            set_identity=str((current.get("song") or {}).get("id") or (current.get("song") or {}).get("object_id") or ""),
            signature_after="", targets=targets,
        )
        tx["post_actions"] = [dict(action) for action in actions]
        tx["post_state_verified"] = False
        # JOURNAL immediately after successful execution. Everything below is
        # fallible best-effort enrichment and must not reopen an unjournaled
        # success window if Live disconnects.
        path = save_transaction(STATE, tx)
        verified_actions = []
        for position, action in enumerate(actions):
            try:
                tx["post_actions"][position] = capture_inverse(bridge, action)
                verified_actions.append(position)
            except Exception as exc:
                tx.setdefault("post_state_errors", []).append({"action_index": position, "error": type(exc).__name__})
        tx["post_state_verified_actions"] = verified_actions
        tx["post_state_verified"] = len(verified_actions) == len(actions)
        if verified_actions:
            tx["post_state_captured_at"] = time.time()
        invalidate_snapshot()
        try:
            after = get_snapshot(force=True)
            tx["set_signature_after"] = str(after.get("set", {}).get("set_signature") or "")
        except Exception as exc:
            tx["post_snapshot_error"] = type(exc).__name__
        atomic_write_json(path, tx)
    projects.record_decision(
        current,
        title=prop["reply"].get("decision_summary") or "Applied N0TE change",
        why=prop["reply"].get("message") or "Approved N0TE proposal.",
        status="accepted",
        details={"transaction": tx["id"], "actions": actions},
    )
    with _proposal_lock:
        if proposals.get(proposal_id) is prop:
            prop["applied_tx"] = tx["id"]
    return {
        "ok": True, "transaction": tx["id"], "journal": str(path), "results": results,
        "review_prompt": "Applied and journaled. Listen/look at the result, then tell me what improved, what got worse, or what should stay. I have the exact recent change in context for the next message.",
    }


def undo_last_n0te() -> dict[str, Any]:
    with _mutation_lock:
        return _undo_last_n0te_locked()


def _undo_last_n0te_locked() -> dict[str, Any]:
    snap = get_snapshot(force=True)
    song_key = projects.song_key(snap)
    path, tx = latest_transaction(STATE, song_key)
    if not tx:
        any_path, any_tx = latest_transaction(STATE)
        if any_tx:
            return {"ok": False, "message": "The latest N0TE transaction belongs to another or unverified Set. Cross-Set Undo is refused."}
        return {"ok": False, "message": "No unapplied N0TE transaction to undo for this Set."}
    current_set_identity = str((snap.get("song") or {}).get("id") or (snap.get("song") or {}).get("object_id") or "")
    if not tx.get("set_identity") or not current_set_identity or str(tx.get("set_identity")) != current_set_identity:
        return {"ok": False, "message": "N0TE cannot prove this transaction belongs to the current Live Set session. Undo refused.", "recovery_required": True}
    if tx.get("transaction_type") == "experiment":
        created_id = tx.get("created_track_id")
        tracks = [t for t in snap.get("set", {}).get("tracks") or [] if isinstance(t, dict)]
        match = next((t for t in tracks if t.get("id") == created_id), None)
        if not match:
            tx["undone"] = True
            tx["undone_at"] = time.time()
            atomic_write_json(path, tx)
            return {"ok": True, "message": "Experiment track is already absent."}
        idx = match.get("index")
        expected_name = tx.get("created_track_name")
        if expected_name and match.get("name") != expected_name:
            return {"ok": False, "message": "The N0TE experiment track was renamed after creation. Refusing automatic deletion; delete it manually if you still want to discard it."}
        bridge.request("call", {"ref": {"path": "live_set"}, "method": "delete_track", "args": [idx], "kwargs": {}, "timeout": 8})
        tx["undone"] = True
        tx["undone_at"] = time.time()
        atomic_write_json(path, tx)
        invalidate_snapshot()
        return {"ok": True, "transaction": tx["id"], "message": "N0TE experiment track removed; original was never altered."}

    unsafe = reresolve_transaction_tracks(tx, snap)
    unsafe.extend(recovery_conflicts(bridge, {**tx, "actions": tx.get("post_actions") or tx.get("actions") or []}, snap))
    if unsafe:
        return {"ok": False, "message": "Unsafe N0TE recovery refused: " + "; ".join(unsafe), "recovery_required": True}
    results, errors = [], []
    for action in reversed(tx.get("inverse_actions") or []):
        try:
            results.append(execute_action(bridge, action, None))
        except Exception as exc:
            errors.append(str(exc))
            break
    if errors:
        # Never issue a blind Live native Undo after a partially successful inverse
        # rollback. At this point Live's undo stack may describe the rollback itself,
        # so another mutation can make recovery worse. Persist the partial state and
        # stop for explicit user recovery.
        tx["rollback_partial"] = True
        tx["rollback_attempted_at"] = time.time()
        tx["rollback_results"] = results
        tx["rollback_errors"] = errors
        atomic_write_json(path, tx)
        invalidate_snapshot()
        return {
            "ok": False,
            "errors": errors,
            "results": results,
            "message": "N0TE stopped after a rollback error. No automatic Ableton Undo was invoked. Review the current Set and use Ableton Undo manually only if you decide it is appropriate.",
            "recovery_required": True,
        }
    tx["undone"] = True
    tx["undone_at"] = time.time()
    atomic_write_json(path, tx)
    invalidate_snapshot()
    return {"ok": True, "transaction": tx["id"], "results": results}


def native_undo() -> dict[str, Any]:
    can = bridge.request("get", {"ref": {"path": "live_set"}, "properties": ["can_undo"], "timeout": 3})
    if not can.get("properties", {}).get("can_undo"):
        return {"ok": False, "message": "Ableton reports nothing to undo."}
    bridge.request("call", {"ref": {"path": "live_set"}, "method": "undo", "args": [], "kwargs": {}, "timeout": 5})
    invalidate_snapshot()
    return {"ok": True}


def selected_chain(snapshot: dict[str, Any], include_parameters: bool = True) -> dict[str, Any]:
    track = selected_context(snapshot)
    if not track:
        return {"track": None, "devices": [], "nested_devices": []}
    devices = []
    for index, device in enumerate(track.get("devices") or []):
        if not isinstance(device, dict) or not device.get("id"):
            continue
        row = {
            "index": index,
            "id": device.get("id"),
            "name": device.get("name"),
            "class_name": device.get("class_name", ""),
            "device_path": device.get("name") or f"Device {index + 1}",
        }
        if include_parameters:
            try:
                params = bridge.request("device_parameters", {"ref": {"id": device["id"]}, "limit": 64, "timeout": 7})
                row["parameters"] = [p for p in (params or []) if isinstance(p, dict)][:64]
            except Exception as exc:
                row["parameters_error"] = str(exc)
            try:
                meta = bridge.request("get", {
                    "ref": {"id": device["id"]},
                    "properties": ["is_active", "latency_in_ms", "latency_in_samples", "can_have_chains"],
                    "timeout": 5,
                })
                row.update(meta.get("properties") or {})
            except Exception:
                pass
        devices.append(row)

    all_devices = current_set_devices(snapshot, bridge=bridge)
    nested = [d for d in all_devices if d.get("track_id") == track.get("id") and int(d.get("depth") or 0) > 0]
    selected_device = snapshot.get("selected_device") if isinstance(snapshot.get("selected_device"), dict) else None
    selected_detail = None
    if selected_device and selected_device.get("id"):
        selected_detail = {
            "id": selected_device.get("id"),
            "name": selected_device.get("name"),
            "parameters": snapshot.get("selected_device_parameters") or [],
            "meta": snapshot.get("selected_device_meta") or {},
        }
    return {
        "track": {"id": track.get("id"), "index": track.get("index"), "name": track.get("name"), "group": track.get("_track_group", "track")},
        "devices": devices,
        "nested_devices": nested,
        "selected_device": selected_detail,
    }

def simplify_schema() -> dict[str, Any]:
    replacement = {
        "type": "object",
        "properties": {
            "device_index": {"type": "integer"},
            "device_id": {"type": "integer"},
            "current_name": {"type": "string"},
            "job": {"type": "string"},
            "recommendation": {"type": "string", "enum": ["keep", "replace", "bypass", "needs_listening"]},
            "replacement_name": {"type": "string"},
            "replacement_source": {"type": "string", "enum": ["ableton_native", "owned", "none"]},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
            "expected_tradeoff": {"type": "string"},
            "can_build_experiment": {"type": "boolean"},
        },
        "required": [
            "device_index", "device_id", "current_name", "job", "recommendation", "replacement_name",
            "replacement_source", "reason", "confidence", "expected_tradeoff", "can_build_experiment"
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "functional_jobs": {"type": "array", "items": {"type": "string"}},
            "replacements": {"type": "array", "items": replacement},
            "notes": {"type": "array", "items": {"type": "string"}},
            "requires_audio_ab": {"type": "boolean"},
            "buildable_count": {"type": "integer"},
        },
        "required": ["summary", "functional_jobs", "replacements", "notes", "requires_audio_ab", "buildable_count"],
        "additionalProperties": False,
    }


def analyze_simplification(snap: dict[str, Any]) -> dict[str, Any]:
    chain = selected_chain(snap, include_parameters=True)
    if not chain.get("track"):
        raise RuntimeError("Select a track in Ableton first.")
    config = load_config()
    pack = context_store.load(config.get("context_sync_path") or "")
    lib = library.load()
    native_names = sorted({
        str(item.get("name") or "") for item in lib.get("items") or []
        if str(item.get("kind") or "").startswith("native_")
    })
    owned_names = sorted({str(item.get("name") or "") for item in lib.get("items") or []})
    instructions = f"""You are N0TE's chain simplification engine.
The goal is NOT to remove fancy plugins for ideological reasons. The goal is to preserve the musical/technical JOB with the least unnecessary complexity.

TELLMEN0TE CONTEXT:
{context_for_prompt(pack)}

RULES:
- Describe the functional jobs actually inferable from device name/parameters. If a plugin's behavior cannot be established, mark needs_listening or keep rather than inventing equivalence.
- A sophisticated plugin should stay when its sophisticated feature is actually being used.
- Prefer replacements in order: an already-present simpler solution, Ableton native, already-owned simpler tool.
- can_build_experiment=true ONLY for Ableton-native replacements whose exact replacement_name appears in AVAILABLE NATIVE DEVICE NAMES.
- Never claim a replacement will sound identical. A/B is required for sonic equivalence.
- Replacement experiments leave the original untouched and build on a duplicate track.
- Do not recommend buying anything.
"""
    payload = (
        "SELECTED CHAIN:\n" + json.dumps(chain, ensure_ascii=False, separators=(",", ":")) +
        "\n\nAVAILABLE NATIVE DEVICE NAMES:\n" + json.dumps(native_names, ensure_ascii=False) +
        "\n\nOWNED/SCANNED DEVICE NAMES (bounded):\n" + json.dumps(owned_names[:1800], ensure_ascii=False)
    )
    result = openai_structured(instructions, payload, "n0te_simplify_plan", simplify_schema(), 3200)
    native_lower = {n.lower() for n in native_names}
    actual_ids = {d.get("id") for d in chain.get("devices") or []}
    buildable_track = (chain.get("track") or {}).get("group") == "track"
    buildable = 0
    for item in result.get("replacements") or []:
        if item.get("device_id") not in actual_ids:
            item["can_build_experiment"] = False
            item["reason"] += " Target id did not match the current chain; execution disabled."
        if item.get("replacement_source") == "ableton_native" and str(item.get("replacement_name") or "").lower() not in native_lower:
            item["can_build_experiment"] = False
        if not buildable_track:
            item["can_build_experiment"] = False
            item["reason"] += " Automatic duplicate-track construction currently supports normal tracks only; return/master analysis remains read-only."
        # v1.2.4 can construct a safe duplicate with the candidate device, but it
        # does not yet translate arbitrary third-party plugin state into native
        # parameter settings. Never imply equivalence from device insertion alone.
        item["implementation_status"] = "structural_candidate_only" if item.get("can_build_experiment") else "analysis_only"
        item["parameter_mapping_available"] = False
        if item.get("can_build_experiment") and item.get("recommendation") == "replace":
            buildable += 1
    result["buildable_count"] = buildable
    result["parameter_mapping_available"] = False
    result.setdefault("notes", []).append("Automatic simplification currently builds a structural A/B candidate with default replacement settings; arbitrary plugin-to-native parameter translation is not yet implemented.")
    return {"plan": result, "chain": chain}


def build_simplify_experiment(proposal_id: str) -> dict[str, Any]:
    cleanup_proposals()
    prop = _proposal_get(simplify_proposals, proposal_id)
    if not prop:
        raise LookupError("Unknown or expired simplification proposal.")
    before = get_snapshot(force=True)
    song_key = projects.song_key(before)
    if prop.get("song_key") and prop.get("song_key") != song_key:
        raise ConflictError("This simplification proposal belongs to another Live Set.")
    if before.get("set", {}).get("set_signature") != prop.get("signature"):
        raise ConflictError("The set changed after the simplification analysis. Re-analyze before building an experiment.")
    track_idx = selected_track_index(before)
    if track_idx is None or track_idx != prop.get("track_index"):
        raise ConflictError("The selected track changed. Re-analyze the intended track first.")
    replacements = [
        r for r in prop["result"]["plan"].get("replacements") or []
        if r.get("recommendation") == "replace" and r.get("can_build_experiment") and r.get("replacement_source") == "ableton_native"
    ]
    if not replacements:
        raise ConflictError("This plan has no native replacement candidates safe enough to build automatically.")

    before_ids = {t.get("id") for t in before.get("set", {}).get("tracks") or [] if isinstance(t, dict)}
    original = selected_context(before) or {}
    bridge.request("call", {
        "ref": {"path": "live_set"}, "method": "duplicate_track", "args": [track_idx], "kwargs": {},
        "expected_set_signature": prop["signature"], "timeout": 12,
    })
    invalidate_snapshot()
    after_dup = get_snapshot(force=True)
    new_tracks = [t for t in after_dup.get("set", {}).get("tracks") or [] if isinstance(t, dict) and t.get("id") not in before_ids]
    if len(new_tracks) != 1:
        recovery = {
            "created_at": time.time(), "operation": "simplification_experiment",
            "proposal_id": proposal_id, "song_key": song_key,
            "reason": "duplicated track could not be uniquely identified",
            "candidate_track_ids": [track.get("id") for track in new_tracks],
            "recovery_required": True,
        }
        recovery_path = STATE / "recovery" / f"simplify_{time.time_ns()}.json"
        atomic_write_json(recovery_path, recovery)
        raise ConflictError(
            f"Could not uniquely identify the duplicated track. No automatic Ableton Undo was invoked; "
            f"review the Set manually. Recovery record: {recovery_path}"
        )
    new_track = new_tracks[0]
    new_idx = new_track.get("index")
    new_id = new_track.get("id")
    new_name = f"{original.get('name') or 'Track'} [N0TE SIMPLE]"
    try:
        bridge.request("set", {"ref": {"id": new_id}, "property": "name", "value": new_name, "timeout": 5})
        bridge.request("set", {"ref": {"id": new_id}, "property": "mute", "value": True, "timeout": 5})
        # Work from highest original device index downward to reduce index-shift confusion.
        for repl in sorted(replacements, key=lambda x: int(x.get("device_index", 0)), reverse=True):
            invalidate_snapshot()
            current = get_snapshot(force=True)
            dup = next((t for t in current.get("set", {}).get("tracks") or [] if isinstance(t, dict) and t.get("id") == new_id), None)
            if not dup:
                raise RuntimeError("Simplification experiment track disappeared during construction.")
            d_idx = int(repl["device_index"])
            devices = [d for d in dup.get("devices") or [] if isinstance(d, dict)]
            if d_idx < 0 or d_idx >= len(devices):
                raise RuntimeError(f"Device index {d_idx} is no longer valid on the duplicate.")
            old_dup_device = devices[d_idx]
            # Preserve original processor on the experiment but bypass it; never delete it.
            bridge.request("set", {"ref": {"id": old_dup_device["id"]}, "property": "is_active", "value": False, "timeout": 5})
            bridge.request("track_insert_device", {
                "ref": {"id": new_id},
                "device_name": repl["replacement_name"],
                "device_index": d_idx + 1,
                "timeout": 10,
            })
        invalidate_snapshot()
    except Exception as exc:
        # Delete only the track N0TE just created; original remains untouched.
        try:
            snap = get_snapshot(force=True)
            match = next((t for t in snap.get("set", {}).get("tracks") or [] if isinstance(t, dict) and t.get("id") == new_id), None)
            if match and isinstance(match.get("index"), int):
                bridge.request("call", {"ref": {"path": "live_set"}, "method": "delete_track", "args": [match["index"]], "kwargs": {}, "timeout": 8})
                invalidate_snapshot()
        except Exception:
            pass
        raise RuntimeError(f"Experiment construction failed and the N0TE duplicate was removed if possible: {exc}")

    completed = get_snapshot(force=True)
    tx = {
        "id": f"exp-{int(time.time()*1000)}",
        "created_at": time.time(),
        "label": f"Simplify {original.get('name') or 'track'}",
        "transaction_type": "experiment",
        "set_signature_before": prop["signature"],
        "set_signature_after": str(completed.get("set", {}).get("set_signature") or ""),
        "song_key": song_key,
        "set_path": str(before.get("song", {}).get("properties", {}).get("file_path") or ""),
        "set_identity": str((before.get("song") or {}).get("id") or (before.get("song") or {}).get("object_id") or ""),
        "affected_targets": [{"object_type": "track", "object_id": new_id, "name_after": new_name}],
        "created_track_id": new_id,
        "created_track_name": new_name,
        "original_track_id": original.get("id"),
        "actions": replacements,
        "inverse_actions": [],
        "results": [{"created_track_id": new_id, "created_track_index": new_idx}],
        "undone": False,
    }
    path = save_transaction(STATE, tx)
    projects.record_decision(
        before,
        title=f"Built simplification experiment for {original.get('name') or 'track'}",
        why=prop["result"]["plan"].get("summary") or "Compare a simpler native implementation against the untouched original.",
        status="experiment",
        details={"transaction": tx["id"], "created_track": new_name, "replacements": replacements},
    )
    return {
        "ok": True,
        "transaction": tx["id"],
        "journal": str(path),
        "created_track": {"id": new_id, "index": new_idx, "name": new_name, "muted": True},
        "message": "Built a muted structural A/B candidate with native replacements at their default settings. Original track was not changed. Parameter translation is not implemented yet, so configure/listen before comparing equivalence.",
        "parameter_mapping_available": False,
    }


def song_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    tracks_out = []
    min_time, max_time = None, 0.0
    total_clip_queries = 0
    for track in snapshot.get("set", {}).get("tracks") or []:
        if not isinstance(track, dict):
            continue
        clips_out = []
        for clip in track.get("arrangement_clips") or []:
            if not isinstance(clip, dict) or not clip.get("id") or total_clip_queries >= 180:
                continue
            total_clip_queries += 1
            try:
                row = bridge.request("get", {
                    "ref": {"id": clip["id"]},
                    "properties": ["start_time", "end_time", "name", "muted"],
                    "timeout": 4,
                }).get("properties") or {}
                start = float(row.get("start_time") or 0.0)
                end = float(row.get("end_time") or start + float(clip.get("length") or 0.0))
                clips_out.append({"id": clip["id"], "name": row.get("name") or clip.get("name"), "start": start, "end": end, "muted": bool(row.get("muted", False))})
                min_time = start if min_time is None else min(min_time, start)
                max_time = max(max_time, end)
            except Exception:
                pass
        tracks_out.append({"index": track.get("index"), "name": track.get("name"), "clips": clips_out})
    numerator = int(snapshot.get("set", {}).get("signature_numerator") or 4)
    segment_beats = max(1, numerator) * 8
    segments = []
    start0 = max(0.0, min_time or 0.0)
    cursor = (start0 // segment_beats) * segment_beats
    while cursor < max_time and len(segments) < 64:
        end = cursor + segment_beats
        active = []
        for t in tracks_out:
            if any(c["start"] < end and c["end"] > cursor and not c.get("muted") for c in t["clips"]):
                active.append(t["name"])
        segments.append({
            "start": cursor,
            "end": end,
            "bar_start": int(cursor / max(1, numerator)) + 1,
            "bar_end": int(end / max(1, numerator)),
            "active_count": len(active),
            "active_tracks": active,
        })
        cursor = end
    return {"tracks": tracks_out, "segments": segments, "segment_bars": 8, "truncated_clip_queries": total_clip_queries >= 180}


def asset_health(snapshot: dict[str, Any]) -> dict[str, Any]:
    assets = []
    seen = set()
    queries = 0
    for track in snapshot.get("set", {}).get("tracks") or []:
        if not isinstance(track, dict):
            continue
        clips = (track.get("clips") or []) + (track.get("arrangement_clips") or [])
        for clip in clips:
            if not isinstance(clip, dict) or not clip.get("id") or not clip.get("is_audio_clip") or clip["id"] in seen or queries >= 180:
                continue
            seen.add(clip["id"])
            queries += 1
            try:
                props = bridge.request("get", {
                    "ref": {"id": clip["id"]}, "properties": ["file_path", "name"], "timeout": 4,
                }).get("properties") or {}
                path = str(props.get("file_path") or "")
                assets.append({
                    "clip_id": clip["id"],
                    "clip_name": props.get("name") or clip.get("name"),
                    "track": track.get("name"),
                    "path": path,
                    "exists": bool(path and Path(path).expanduser().exists()),
                    "external": bool(path and snapshot.get("song", {}).get("properties", {}).get("file_path") and not path.startswith(str(Path(snapshot["song"]["properties"]["file_path"]).expanduser().parent))),
                })
            except Exception as exc:
                assets.append({"clip_id": clip["id"], "clip_name": clip.get("name"), "track": track.get("name"), "error": str(exc)})
    missing = [a for a in assets if a.get("path") and not a.get("exists")]
    external = [a for a in assets if a.get("external")]
    return {"assets": assets, "missing": missing, "external": external, "queries": queries, "truncated": queries >= 180}



def enrich_library() -> dict[str, Any]:
    targets = library.enrichment_targets(limit=240)
    if not targets:
        return {"updated": 0, "message": "No unenriched plugin/rack targets remain in the current bounded pass.", "library": library.summary()}
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "category": {"type": "string"},
                        "capability_tags": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                        "note": {"type": "string"},
                    },
                    "required": ["key", "category", "capability_tags", "confidence", "note"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    all_rows = []
    for start in range(0, len(targets), 48):
        batch = targets[start:start+48]
        instructions = """Classify music-production plugins/racks for local search. Use your product knowledge cautiously.
Return the provided key exactly. category should be a short functional class such as eq, compressor, reverb, delay, saturation, transient, stereo, modulation, synth, sampler, meter, utility, pitch, restoration, multiband, rack, or unknown.
capability_tags should contain natural-language production jobs someone might search for.
If you are not confident what a product is from its name/path, use category=unknown, low confidence, and do not invent capabilities.
This is knowledge enrichment only; do not recommend purchases."""
        result = openai_structured(
            instructions,
            json.dumps(batch, ensure_ascii=False),
            "n0te_library_enrichment",
            schema,
            max_output_tokens=5000,
        )
        valid_keys = {x["key"] for x in batch}
        for row in result.get("items") or []:
            if row.get("key") in valid_keys:
                all_rows.append(row)
    applied = library.apply_enrichment(all_rows)
    return {**applied, "library": library.summary()}

def engineer_status(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = snapshot or get_snapshot()
    config = load_config()
    try:
        bridge_status = bridge.request("bridge_status", {"timeout": 2})
    except Exception as exc:
        bridge_status = {"ok": False, "error": str(exc)}
    return {
        "app_version": APP_VERSION,
        "bridge_status": bridge_status,
        "set_signature": snap.get("set", {}).get("set_signature"),
        "context": context_store.status(config.get("context_sync_path") or ""),
        "library": library.summary(),
        "transactions": list_transactions(STATE, 20),
        "state_dir": str(STATE),
        "config_path": str(CONFIG_PATH),
        "secret_path": str(SECRET_PATH),
        "providers": {
            "openverse_token": bool(get_secret("openverse_token")),
            "freesound_api_key": bool(get_secret("freesound_api_key")),
        },
    }


def status_payload() -> dict[str, Any]:
    """Return useful app status even when Ableton is offline."""
    config = load_config()
    base = {
        "version": APP_VERSION,
        "api_key": bool(get_api_key()),
        "config": config,
        "library": library.summary(),
        "context": context_store.status(config.get("context_sync_path") or ""),
        "providers": {
            "openverse_token": bool(get_secret("openverse_token")),
            "freesound_api_key": bool(get_secret("freesound_api_key")),
        },
        "services": {
            "ai": provider_status(),
            "network": NetworkPolicy.from_value(config.get("network_mode")).status(),
            "community": {"state": "READY" if config.get("community_enabled") else "OFF"},
        },
    }
    try:
        snap = get_snapshot()
    except Exception as exc:
        return {**base, "ok": False, "error": f"Ableton bridge offline: {exc}", "snapshot": None, "selected_track": None, "song_state": {}, "conversation": []}
    return {
        **base,
        "ok": True,
        "snapshot": compact_snapshot(snap),
        "selected_track": snap.get("selected_track_summary"),
        "song_state": projects.load_song(snap),
        "conversation": projects.list_conversation(snap, 20),
    }


def local_request_allowed(host: str, origin: str = "") -> bool:
    host = str(host or "").lower().strip()
    allowed_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    if host not in allowed_hosts:
        return False
    origin = str(origin or "").lower().rstrip("/")
    if origin and origin not in {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}:
        return False
    return True


def error_status(exc: Exception) -> int:
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, OverflowError):
        return 413
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return 400
    if isinstance(exc, LookupError):
        return 404
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, (DependencyUnavailableError, ConnectionError, TimeoutError, urllib.error.URLError, OSError)):
        return 503
    return 500


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        # Standard request metadata only; bodies, model/audio payloads and headers
        # (including credentials) are deliberately excluded.
        _diagnostic_log.info("http %s", (fmt % args)[:1000])

    def send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body_json(self) -> dict[str, Any]:
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if n < 0 or n > MAX_REQUEST_BODY:
            raise OverflowError(f"Request body exceeds {MAX_REQUEST_BODY} bytes")
        try:
            value = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Malformed JSON request body") from exc
        return value if isinstance(value, dict) else {}

    def do_GET(self):
        if not local_request_allowed(self.headers.get("Host", ""), self.headers.get("Origin", "")):
            return self.send_json({"ok": False, "error": "Rejected non-local request origin."}, 403)
        try:
            if self.path == "/api/status":
                self.send_json(status_payload())
                return
            if self.path == "/api/history":
                snap = get_snapshot()
                self.send_json({
                    "ok": True,
                    "transactions": list_transactions(STATE, 60),
                    "checkpoints": projects.list_checkpoints(snap, 40),
                    "decisions": projects.list_decisions(snap, 60),
                    "discovery": projects.list_discovery(snap, 80),
                    "conversation": projects.list_conversation(snap, 40),
                })
                return
            if self.path == "/api/engineer":
                self.send_json({"ok": True, "data": engineer_status()})
                return
            if self.path == "/api/artist-world":
                return self.send_json({"ok": True, "artist_world": creator_service.artist_read()})
            if self.path == "/api/creator/projects":
                return self.send_json({"ok": True, "projects": creator_service.projects()})
            if self.path == "/api/stream":
                return self.send_json({"ok": True, "stream": creator_service.stream_state()})
            if self.path == "/api/daws":
                return self.send_json({"ok": True, "label": "Detect DAWs", "integrations": daw_service.integrations()})
            if self.path == "/api/setup":
                return self.send_json({"ok": True, "setup": daw_service.first_run_status(), "integrations": daw_service.integrations()})
            if self.path == "/api/updates":
                config=load_config(); offline=NetworkPolicy.from_value(config.get("network_mode")).status()["intentional_offline"]
                return self.send_json({"ok":True,"updates":{"state":"PAUSED_BY_NETWORK_POLICY" if offline else "IDLE","intentional_offline":offline,"channel":config.get("update_channel","STABLE"),"automatic_checking":bool(config.get("automatic_update_checking",True)),"automatic_safe_install":bool(config.get("automatic_safe_install",True)),"release_signature_status":"NOT_CHECKED","pending_components":[],"pending_host_closes":[],"pending_restart":False,"rollback_available":False}})
            return super().do_GET()
        except Exception as exc:
            _diagnostic_log.error("GET %s: %s", self.path[:300], type(exc).__name__)
            self.send_json({"ok": False, "error": str(exc)}, error_status(exc))

    def do_POST(self):
        if not local_request_allowed(self.headers.get("Host", ""), self.headers.get("Origin", "")):
            self.send_json({"ok": False, "error": "Rejected non-local request origin."}, 403)
            return
        try:
            if self.path == "/api/audio/analyze":
                data=self.body_json();encoded=str(data.get("wav_base64") or "")
                if not encoded:raise ValueError("WAV payload required")
                raw=base64.b64decode(encoded,validate=True)
                if len(raw)>700_000:raise ValueError("Audio analysis upload exceeds 700 KB")
                with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
                    handle.write(raw);handle.flush();buffer=read_wav(handle.name);full=analyze(buffer);report=audio_summary(full)
                return self.send_json({"ok":True,"mode":"OFFLINE_ANALYSIS","report":report,"diagnoses":diagnose(full)})
            if self.path == "/api/plugins/scan":
                return self.send_json({"ok":True,"scan":PluginScanProcess().scan(plugin_roots(),timeout=15)})
            if self.path == "/api/config":
                data = self.body_json()
                if data.get("api_key"):
                    store_api_key(str(data["api_key"]))
                if data.get("freesound_api_key"):
                    store_secret("freesound_api_key", str(data["freesound_api_key"]))
                if data.get("openverse_token"):
                    store_secret("openverse_token", str(data["openverse_token"]))
                config = load_config()
                for key in ("model", "mode", "context_sync_path", "auto_refresh_seconds", "ai_provider", "network_mode", "community_enabled", "automatic_update_checking", "automatic_safe_install", "update_channel"):
                    if key in data:
                        config[key] = data[key]
                save_config(config)
                return self.send_json({"ok": True, "api_key": bool(get_api_key()), "config": config, "providers": {"openverse_token": bool(get_secret("openverse_token")), "freesound_api_key": bool(get_secret("freesound_api_key"))}})

            if self.path == "/api/artist-world":
                return self.send_json({"ok": True, "artist_world": creator_service.artist_update(self.body_json())})
            if self.path == "/api/setup":
                return self.send_json({"ok": True, "setup": daw_service.first_run_advance(self.body_json()), "integrations": daw_service.integrations()})
            if self.path == "/api/daws/ableton":
                data=self.body_json();operation=str(data.get("operation") or "verify")
                evidence=remote_script_doctor(STATE)
                if operation in {"verify","diagnostics"}:return self.send_json({"ok":True,"operation":operation,"doctor":evidence,"deep_acceptance":False})
                return self.send_json({"ok":False,"error":"Ableton integration install/repair requires a verified bundled adapter payload in this development build.","doctor":evidence},503)
            if self.path == "/api/creator/projects":
                data=self.body_json(); return self.send_json({"ok":True,"project":creator_service.project_create(str(data.get("song_id") or ""),str(data.get("title") or "Untitled"))})
            if self.path == "/api/creator/recipe":
                data=self.body_json(); return self.send_json({"ok":True,"recipe":creator_service.recipe(str(data.get("project_id") or ""),str(data.get("recipe") or ""),data.get("sections") or [],data.get("marks") or [],str(data.get("aspect") or "9:16"),str(data.get("artist_mode") or "USE_ARTIST_WORLD"))})
            if self.path == "/api/creator/edit":
                data=self.body_json(); return self.send_json({"ok":True,"project":creator_service.edit(str(data.get("project_id") or ""),int(data.get("index",-1)),str(data.get("operation") or ""),data.get("params") or {})})
            if self.path == "/api/creator/visibility":
                data=self.body_json(); return self.send_json({"ok":True,"project":creator_service.visibility(str(data.get("project_id") or ""),str(data.get("visibility") or ""),str(data.get("authority") or ""),bool(data.get("explicit")))})
            if self.path == "/api/stream":
                data=self.body_json();op=str(data.get("operation") or "state")
                if op=="test": value=creator_service.stream_test(str(data.get("scene") or "PRODUCING"))
                elif op=="go_live": value=creator_service.stream_live(str(data.get("scene") or "PRODUCING"),str(data.get("authority") or ""),bool(data.get("explicit")),bool(data.get("reconnect")))
                elif op=="stop": value=creator_service.stream_stop()
                else: value=creator_service.stream_state()
                return self.send_json({"ok":True,"stream":value})

            if self.path == "/api/chat":
                data = self.body_json()
                text = str(data.get("message") or "").strip()
                if not text:
                    raise RuntimeError("Message is empty.")
                snap = get_snapshot(force=True)
                ai_off = str(load_config().get("ai_provider") or "openai").lower() in {"off", "none"}
                reply = deterministic_reply(text, snap) if ai_off else ask_openai(text, snap)
                pid = str(int(time.time() * 1000))
                cleanup_proposals()
                with _proposal_lock:
                    proposals[pid] = {
                        "created_at": time.time(), "signature": snap["set"].get("set_signature"),
                        "song_key": projects.song_key(snap), "reply": reply,
                        "affected_targets": affected_target_evidence(reply.get("actions") or [], snap),
                    }
                projects.append_conversation(snap, "user", text, {"proposal_id": pid})
                projects.append_conversation(snap, "assistant", reply.get("message", ""), {"proposal_id": pid})
                discovery_payload = reply.pop("_discovery", None)
                return self.send_json({"ok": True, "proposal_id": pid, "reply": reply, "discovery": discovery_payload})

            if self.path == "/api/apply":
                data = self.body_json()
                return self.send_json(apply_proposal(str(data.get("proposal_id") or "")))

            if self.path == "/api/undo_n0te":
                return self.send_json(undo_last_n0te())

            if self.path == "/api/undo_live":
                with _mutation_lock:
                    return self.send_json(native_undo())

            if self.path == "/api/safe":
                data = self.body_json()
                enabled = bool(data.get("enabled", True))
                if enabled:
                    state = safety.enter(str(data.get("reason") or "user"))
                    with _proposal_lock:
                        proposals.clear(); simplify_proposals.clear()
                else:
                    state = safety.leave(explicit_user_confirmation=bool(data.get("confirm")))
                return self.send_json({"ok": True, "safety": state})

            if self.path == "/api/refresh":
                snap = get_snapshot(force=True)
                return self.send_json({"ok": True, "snapshot": compact_snapshot(snap), "selected_track": snap.get("selected_track_summary"), "song_state": projects.load_song(snap)})

            if self.path == "/api/song_state":
                data = self.body_json()
                snap = get_snapshot(force=True)
                state = projects.save_song(snap, data)
                return self.send_json({"ok": True, "song_state": state})

            if self.path == "/api/tools/search":
                data = self.body_json()
                query = str(data.get("query") or "").strip()
                snap = get_snapshot()
                return self.send_json({"ok": True, "result": resolve_tools(query, library, snap, bridge=bridge, deep=True), "current_set_devices": current_set_devices(snap, bridge=bridge)})

            if self.path == "/api/library/scan":
                result = library.scan(bridge)
                return self.send_json({"ok": True, "library": library.summary(), "errors": result.get("errors") or []})


            if self.path == "/api/library/enrich":
                result = enrich_library()
                return self.send_json({"ok": True, **result})

            if self.path == "/api/discover/search":
                data = self.body_json()
                snap = get_snapshot(force=True)
                query = str(data.get("query") or "").strip()
                include_web = bool(data.get("include_web", True))
                result = discover(
                    query, bridge, library, snap,
                    include_web=include_web,
                    openverse_token=get_secret("openverse_token"),
                    freesound_key=get_secret("freesound_api_key"),
                    web_threshold=int(data.get("web_threshold") or 6),
                    license_filter=str(data.get("license_filter") or ""),
                    network_policy=NetworkPolicy.from_value(load_config().get("network_mode")),
                )
                return self.send_json({"ok": True, "result": result})

            if self.path == "/api/discover/remember":
                data = self.body_json()
                snap = get_snapshot(force=True)
                item = data.get("item") if isinstance(data.get("item"), dict) else {}
                row = projects.record_discovery(
                    snap, item, status=str(data.get("status") or "tried"), note=str(data.get("note") or "")
                )
                return self.send_json({"ok": True, "memory": row})

            if self.path == "/api/create/midi":
                snap = get_snapshot(force=True)
                detail = snap.get("view", {}).get("properties", {}).get("detail_clip")
                return self.send_json({
                    "ok": True,
                    "clip": detail,
                    "notes": snap.get("selected_clip_notes"),
                    "error": snap.get("selected_clip_notes_error", ""),
                })

            if self.path == "/api/chain":
                snap = get_snapshot(force=True)
                return self.send_json({"ok": True, "chain": selected_chain(snap, include_parameters=True)})

            if self.path == "/api/simplify/analyze":
                snap = get_snapshot(force=True)
                result = analyze_simplification(snap)
                pid = f"simp-{int(time.time()*1000)}"
                with _proposal_lock:
                    simplify_proposals[pid] = {
                        "created_at": time.time(),
                        "signature": snap.get("set", {}).get("set_signature"),
                        "song_key": projects.song_key(snap),
                        "track_index": selected_track_index(snap),
                        "result": result,
                    }
                return self.send_json({"ok": True, "proposal_id": pid, **result})

            if self.path == "/api/simplify/build":
                data = self.body_json()
                with _mutation_lock:
                    return self.send_json(build_simplify_experiment(str(data.get("proposal_id") or "")))

            if self.path == "/api/checkpoint":
                data = self.body_json()
                snap = get_snapshot(force=True)
                config = load_config()
                cp = projects.checkpoint(
                    snap,
                    projects.load_song(snap),
                    context_store.status(config.get("context_sync_path") or ""),
                    library.summary(),
                    label=str(data.get("label") or "Checkpoint"),
                )
                projects.record_decision(snap, f"Checkpoint: {cp['label']}", "Saved a reconstruction/state checkpoint.", status="checkpoint", details={"path": cp["path"]})
                return self.send_json({"ok": True, "checkpoint": {k: v for k, v in cp.items() if k != "snapshot"}})

            if self.path == "/api/compare":
                snap = get_snapshot(force=True)
                return self.send_json({"ok": True, "compare": projects.compare_latest(snap)})

            if self.path == "/api/song_map":
                snap = get_snapshot(force=True)
                return self.send_json({"ok": True, "map": song_map(snap)})

            if self.path == "/api/finish":
                snap = get_snapshot(force=True)
                assets = asset_health(snap)
                preflight = {
                    "structural_preflight_complete": True,
                    "audio_preflight_complete": False,
                    "missing_assets": assets.get("missing") or [],
                }
                return self.send_json({"ok": True, "finish": finish_checklist(snap, projects.load_song(snap), preflight=preflight), "assets": assets})

            if self.path == "/api/health":
                config = load_config()
                payload = {
                    "ok": True, "ableton_online": False,
                    "assets": {"assets": [], "missing": [], "external": [], "unavailable": True},
                    "context": context_store.status(config.get("context_sync_path") or ""),
                    "library": library.summary(),
                    "remote_script_doctor": remote_script_doctor(STATE),
                }
                try:
                    snap = get_snapshot(force=True)
                    payload.update({"ableton_online": True, "assets": asset_health(snap), "engineer": engineer_status(snap)})
                except Exception as exc:
                    payload["ableton_error"] = f"{type(exc).__name__}: {exc}"
                return self.send_json(payload)

            if self.path == "/api/context/replace":
                data = self.body_json()
                pack = data.get("context_pack")
                if not isinstance(pack, dict):
                    raise RuntimeError("context_pack must be a JSON object")
                result = context_store.replace(pack)
                return self.send_json({"ok": True, "context": {k: v for k, v in result.items() if str(k).startswith("_") or k == "schema_version"}})

            if self.path == "/api/decision":
                data = self.body_json()
                snap = get_snapshot()
                item = projects.record_decision(
                    snap,
                    title=str(data.get("title") or "Decision"),
                    why=str(data.get("why") or ""),
                    status=str(data.get("status") or "accepted"),
                    source=str(data.get("source") or "user"),
                )
                return self.send_json({"ok": True, "decision": item})

            self.send_json({"ok": False, "error": "Unknown endpoint"}, 404)
        except Exception as exc:
            _diagnostic_log.error("POST %s: %s", self.path[:300], type(exc).__name__)
            self.send_json({"ok": False, "error": str(exc)}, error_status(exc))


def main() -> None:
    print(f"N0TE Ableton AI {APP_VERSION}")
    print(f"UI: http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    first_run = not (STATE / "first_run.json").is_file()
    threading.Timer(0.7, lambda: webbrowser.open(f"http://{HOST}:{PORT}/?first_run=1" if first_run else f"http://{HOST}:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
