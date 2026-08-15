from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any
from n0te_state import atomic_write_json


ALLOWED_KINDS = {
    "rename_track",
    "set_track_mute",
    "set_track_solo",
    "set_track_arm",
    "set_track_pan",
    "set_track_volume",
    "set_send_level",
    "set_tempo",
    "set_device_parameter",
    "set_device_active",
    "set_clip_name",
    "set_clip_muted",
    "set_arrangement_loop",
    "update_midi_clip_notes",
}


def live_object_index(snapshot: dict[str, Any]) -> dict[str, dict[int, dict[str, Any]]]:
    """Canonical recursive index for exposed tracks, Rack devices and clips."""
    index: dict[str, dict[int, dict[str, Any]]] = {"tracks": {}, "devices": {}, "clips": {}}

    def devices(rows: list[Any]) -> None:
        for device in rows:
            if not isinstance(device, dict):
                continue
            if isinstance(device.get("id"), int):
                index["devices"][device["id"]] = device
            devices(device.get("devices") or device.get("nested_devices") or [])
            for chain in device.get("chains") or []:
                if isinstance(chain, dict):
                    devices(chain.get("devices") or [])

    tracks = []
    for group in ("tracks", "return_tracks"):
        tracks.extend(snapshot.get("set", {}).get(group) or [])
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        tracks.append(master)
    for track in tracks:
        if not isinstance(track, dict):
            continue
        if isinstance(track.get("id"), int):
            index["tracks"][track["id"]] = track
        devices(track.get("devices") or [])
        for clip in (track.get("clips") or []) + (track.get("arrangement_clips") or []):
            if isinstance(clip, dict) and isinstance(clip.get("id"), int):
                index["clips"][clip["id"]] = clip
    appointed = snapshot.get("song", {}).get("properties", {}).get("appointed_device")
    if isinstance(appointed, dict) and isinstance(appointed.get("id"), int):
        index["devices"][appointed["id"]] = appointed
    return index


def action_schema() -> dict[str, Any]:
    item = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": sorted(ALLOWED_KINDS)},
            "track_index": {"type": "integer"},
            "send_index": {"type": "integer"},
            "target_id": {"type": "integer"},
            "parameter": {"type": "string"},
            "string_value": {"type": "string"},
            "number_value": {"type": "number"},
            "number_value_2": {"type": "number"},
            "bool_value": {"type": "boolean"},
            "reason": {"type": "string"},
            "risk": {"type": "string", "enum": ["low", "medium"]},
        },
        "required": [
            "kind", "track_index", "send_index", "target_id", "parameter", "string_value",
            "number_value", "number_value_2", "bool_value", "reason", "risk"
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "decision_summary": {"type": "string"},
            "confidence": {"type": "number"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "evidence_labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "enum": ["live_state", "audio_measurement", "inference", "ear_decision"]},
                        "text": {"type": "string"}
                    },
                    "required": ["label", "text"],
                    "additionalProperties": False
                }
            },
            "actions": {"type": "array", "items": item},
            "needs_audio": {"type": "boolean"},
            "audio_reason": {"type": "string"},
            "tool_answer": {"type": "string"},
            "stage_warning": {"type": "string"},
        },
        "required": [
            "message", "decision_summary", "confidence", "evidence", "evidence_labels", "actions",
            "needs_audio", "audio_reason", "tool_answer", "stage_warning"
        ],
        "additionalProperties": False,
    }


def validate_action(action: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, str]:
    kind = action.get("kind")
    if kind not in ALLOWED_KINDS:
        return False, f"Action kind {kind!r} is not allowed"
    tracks = [
        t for t in (snapshot.get("set", {}).get("tracks") or [])
        if isinstance(t, dict) and isinstance(t.get("index"), int)
    ]
    valid_track_indices = {t["index"] for t in tracks}
    objects = live_object_index(snapshot)
    device_ids = set(objects["devices"])
    clip_ids = set(objects["clips"])
    all_tracks = tracks + [
        t for t in (snapshot.get("set", {}).get("return_tracks") or []) if isinstance(t, dict)
    ]
    master = snapshot.get("set", {}).get("master_track")
    if isinstance(master, dict):
        all_tracks.append(master)
    if kind.startswith("set_track_") or kind == "rename_track" or kind == "set_send_level":
        idx = action.get("track_index")
        if not isinstance(idx, int) or idx not in valid_track_indices:
            return False, f"Invalid track index {idx}"
    if kind == "set_tempo":
        bpm = float(action.get("number_value", 0))
        if not 20 <= bpm <= 300:
            return False, "Tempo must be between 20 and 300 BPM"
    if kind == "set_track_pan":
        val = float(action.get("number_value", 0))
        if not -1.0 <= val <= 1.0:
            return False, "Pan must be between -1 and 1"
    if kind in ("set_track_volume", "set_send_level"):
        val = float(action.get("number_value", 0))
        if not 0.0 <= val <= 1.0:
            return False, "Mixer parameter values must be between 0 and 1"
        if kind == "set_send_level" and int(action.get("send_index", -1)) < 0:
            return False, "send_index must be >= 0"
    if kind in ("set_device_parameter", "set_device_active"):
        tid = int(action.get("target_id") or 0)
        if tid not in device_ids:
            return False, f"Device id {tid} is not present in the current snapshot"
        if kind == "set_device_parameter" and not str(action.get("parameter") or "").strip():
            return False, "parameter is required"
    if kind in ("set_clip_name", "set_clip_muted"):
        tid = int(action.get("target_id") or 0)
        if tid not in clip_ids:
            return False, f"Clip id {tid} is not present in the current snapshot"
    if kind == "set_arrangement_loop":
        start = float(action.get("number_value", 0))
        length = float(action.get("number_value_2", 0))
        if start < 0 or length <= 0:
            return False, "Arrangement loop requires start >= 0 and length > 0"
    if kind == "update_midi_clip_notes":
        tid = int(action.get("target_id") or 0)
        detail = snapshot.get("view", {}).get("properties", {}).get("detail_clip")
        if not isinstance(detail, dict) or int(detail.get("id") or 0) != tid:
            return False, "MIDI note edits are limited to the currently selected/detail clip"
        try:
            updates = json.loads(str(action.get("string_value") or "[]"))
        except Exception:
            return False, "string_value must contain a JSON list of MIDI note updates"
        if not isinstance(updates, list) or not updates or len(updates) > 128:
            return False, "MIDI update list must contain 1..128 note updates"
        known = {int(n.get("note_id")) for n in (snapshot.get("selected_clip_notes", {}).get("notes") or []) if isinstance(n, dict) and n.get("note_id") is not None}
        allowed = {"note_id", "pitch", "start_time", "duration", "velocity", "mute", "probability", "velocity_deviation", "release_velocity"}
        for row in updates:
            if not isinstance(row, dict) or set(row) - allowed:
                return False, "MIDI updates contain unsupported fields"
            note_id = row.get("note_id")
            if not isinstance(note_id, int) or note_id not in known:
                return False, f"Unknown MIDI note_id {note_id}"
            if "pitch" in row and not 0 <= int(row["pitch"]) <= 127:
                return False, "MIDI pitch must be 0..127"
            if "velocity" in row and not 0 <= float(row["velocity"]) <= 127:
                return False, "MIDI velocity must be 0..127"
            if "probability" in row and not 0.0 <= float(row["probability"]) <= 1.0:
                return False, "MIDI probability must be 0..1"
            if "duration" in row and float(row["duration"]) <= 0:
                return False, "MIDI note duration must be > 0"
    return True, ""


def ref_id(object_id: int) -> dict[str, int]:
    return {"id": int(object_id)}


def ref_path(path: str) -> dict[str, str]:
    return {"path": path}


def resolve_parameter(bridge, device_id: int, query: str) -> dict[str, Any]:
    params = bridge.request("device_parameters", {
        "ref": ref_id(device_id),
        "query": query,
        "limit": 48,
        "timeout": 5,
    })
    rows = [x for x in (params or []) if isinstance(x, dict) and x.get("id")]
    if not rows:
        raise RuntimeError(f"No parameter matching {query!r} found on device {device_id}")
    exact = [p for p in rows if str(p.get("name", "")).lower() == query.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(rows) == 1:
        return rows[0]
    names = ", ".join(str(x.get("name")) for x in rows[:8])
    raise RuntimeError(f"Parameter {query!r} is ambiguous. Matches: {names}")


def capture_inverse(bridge, action: dict[str, Any]) -> dict[str, Any]:
    kind = action["kind"]
    inv = dict(action)
    inv["reason"] = "N0TE rollback"
    inv["risk"] = "low"

    if kind == "rename_track":
        idx = action["track_index"]
        cur = bridge.request("get", {"ref": ref_path(f"live_set tracks {idx}"), "properties": ["name"], "timeout": 5})
        inv["string_value"] = cur["properties"]["name"]
    elif kind in ("set_track_mute", "set_track_solo", "set_track_arm"):
        idx = action["track_index"]
        prop = {"set_track_mute": "mute", "set_track_solo": "solo", "set_track_arm": "arm"}[kind]
        cur = bridge.request("get", {"ref": ref_path(f"live_set tracks {idx}"), "properties": [prop], "timeout": 5})
        inv["bool_value"] = bool(cur["properties"][prop])
    elif kind == "set_tempo":
        cur = bridge.request("get", {"ref": ref_path("live_set"), "properties": ["tempo"], "timeout": 5})
        inv["number_value"] = float(cur["properties"]["tempo"])
    elif kind == "set_track_pan":
        idx = action["track_index"]
        cur = bridge.request("get", {
            "ref": ref_path(f"live_set tracks {idx} mixer_device panning"),
            "properties": ["value"], "timeout": 5
        })
        inv["number_value"] = float(cur["properties"]["value"])
    elif kind == "set_track_volume":
        idx = action["track_index"]
        cur = bridge.request("get", {
            "ref": ref_path(f"live_set tracks {idx} mixer_device volume"),
            "properties": ["value"], "timeout": 5
        })
        inv["number_value"] = float(cur["properties"]["value"])
    elif kind == "set_send_level":
        idx = action["track_index"]
        send_idx = action["send_index"]
        cur = bridge.request("get", {
            "ref": ref_path(f"live_set tracks {idx} mixer_device sends {send_idx}"),
            "properties": ["value"], "timeout": 5
        })
        inv["number_value"] = float(cur["properties"]["value"])
    elif kind == "set_device_parameter":
        p = resolve_parameter(bridge, action["target_id"], action["parameter"])
        inv["target_id"] = int(action["target_id"])
        inv["parameter"] = str(p["name"])
        inv["number_value"] = float(p["value"])
    elif kind == "set_device_active":
        cur = bridge.request("get", {
            "ref": ref_id(action["target_id"]), "properties": ["is_active"], "timeout": 5
        })
        inv["bool_value"] = bool(cur["properties"]["is_active"])
    elif kind in ("set_clip_name", "set_clip_muted"):
        prop = "name" if kind == "set_clip_name" else "muted"
        cur = bridge.request("get", {"ref": ref_id(action["target_id"]), "properties": [prop], "timeout": 5})
        if kind == "set_clip_name":
            inv["string_value"] = cur["properties"][prop]
        else:
            inv["bool_value"] = bool(cur["properties"][prop])
    elif kind == "set_arrangement_loop":
        cur = bridge.request("get", {
            "ref": ref_path("live_set"), "properties": ["loop", "loop_start", "loop_length"], "timeout": 5
        })
        inv["bool_value"] = bool(cur["properties"]["loop"])
        inv["number_value"] = float(cur["properties"]["loop_start"])
        inv["number_value_2"] = float(cur["properties"]["loop_length"])
    elif kind == "update_midi_clip_notes":
        requested = json.loads(str(action.get("string_value") or "[]"))
        current = bridge.request("clip_notes", {"ref": ref_id(action["target_id"]), "limit": 2048, "timeout": 7})
        by_id = {int(n.get("note_id")): n for n in (current.get("notes") or []) if isinstance(n, dict) and n.get("note_id") is not None}
        inverse_updates = []
        attrs = ("pitch", "start_time", "duration", "velocity", "mute", "probability", "velocity_deviation", "release_velocity")
        for row in requested:
            old = by_id.get(int(row["note_id"]))
            if not old:
                raise RuntimeError(f"Cannot capture inverse for MIDI note {row['note_id']}")
            inv_row = {"note_id": int(row["note_id"])}
            for attr in attrs:
                if attr in row and attr in old:
                    inv_row[attr] = old[attr]
            inverse_updates.append(inv_row)
        inv["string_value"] = json.dumps(inverse_updates, separators=(",", ":"))
    return inv


def execute_action(bridge, action: dict[str, Any], expected_signature: str | None = None) -> Any:
    kind = action["kind"]
    guard = {"expected_set_signature": expected_signature} if expected_signature else {}

    if kind == "rename_track":
        return bridge.request("set", {
            "ref": ref_path(f"live_set tracks {action['track_index']}"),
            "property": "name", "value": action["string_value"], **guard
        })
    if kind in ("set_track_mute", "set_track_solo", "set_track_arm"):
        prop = {"set_track_mute": "mute", "set_track_solo": "solo", "set_track_arm": "arm"}[kind]
        return bridge.request("set", {
            "ref": ref_path(f"live_set tracks {action['track_index']}"),
            "property": prop, "value": bool(action["bool_value"]), **guard
        })
    if kind == "set_tempo":
        return bridge.request("set", {
            "ref": ref_path("live_set"), "property": "tempo",
            "value": float(action["number_value"]), **guard
        })
    if kind == "set_track_pan":
        return bridge.request("parameter_set", {
            "ref": ref_path(f"live_set tracks {action['track_index']} mixer_device panning"),
            "value": float(action["number_value"]), "coerce": True, **guard
        })
    if kind == "set_track_volume":
        return bridge.request("parameter_set", {
            "ref": ref_path(f"live_set tracks {action['track_index']} mixer_device volume"),
            "value": float(action["number_value"]), "coerce": True, **guard
        })
    if kind == "set_send_level":
        return bridge.request("parameter_set", {
            "ref": ref_path(f"live_set tracks {action['track_index']} mixer_device sends {action['send_index']}"),
            "value": float(action["number_value"]), "coerce": True, **guard
        })
    if kind == "set_device_parameter":
        p = resolve_parameter(bridge, action["target_id"], action["parameter"])
        return bridge.request("parameter_set", {
            "ref": ref_id(int(p["id"])), "value": float(action["number_value"]),
            "coerce": True, **guard
        })
    if kind == "set_device_active":
        return bridge.request("set", {
            "ref": ref_id(action["target_id"]), "property": "is_active",
            "value": bool(action["bool_value"]), **guard
        })
    if kind == "set_clip_name":
        return bridge.request("set", {
            "ref": ref_id(action["target_id"]), "property": "name",
            "value": action["string_value"], **guard
        })
    if kind == "set_clip_muted":
        return bridge.request("set", {
            "ref": ref_id(action["target_id"]), "property": "muted",
            "value": bool(action["bool_value"]), **guard
        })
    if kind == "set_arrangement_loop":
        ops = [
            {"method": "set", "params": {"ref": ref_path("live_set"), "property": "loop_start", "value": float(action["number_value"]) }},
            {"method": "set", "params": {"ref": ref_path("live_set"), "property": "loop_length", "value": float(action["number_value_2"]) }},
            {"method": "set", "params": {"ref": ref_path("live_set"), "property": "loop", "value": bool(action["bool_value"]) }},
        ]
        return bridge.request("batch", {"operations": ops, **guard, "timeout": 8})
    if kind == "update_midi_clip_notes":
        updates = json.loads(str(action.get("string_value") or "[]"))
        return bridge.request("clip_update_notes", {"ref": ref_id(action["target_id"]), "updates": updates, **guard, "timeout": 10})
    raise RuntimeError(f"Unsupported action: {kind}")


def make_transaction(actions: list[dict[str, Any]], inverses: list[dict[str, Any]], signature: str,
                     results: list[Any], label: str = "N0TE edit", *, song_key: str = "",
                     set_path: str = "", set_identity: str = "", signature_after: str = "",
                     targets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": time.time(),
        "label": label,
        "set_signature_before": signature,
        "set_signature_after": signature_after,
        "song_key": song_key,
        "set_path": set_path,
        "set_identity": set_identity,
        "affected_targets": targets or [],
        "actions": actions,
        "inverse_actions": inverses,
        "results": results,
        "undone": False,
    }


def save_transaction(state_dir: Path, tx: dict[str, Any]) -> Path:
    d = state_dir / "transactions"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{int(tx['created_at'])}_{tx['id']}.json"
    atomic_write_json(p, tx)
    return p


def latest_transaction(state_dir: Path, song_key: str | None = None) -> tuple[Path | None, dict[str, Any] | None]:
    d = state_dir / "transactions"
    if not d.exists():
        return None, None
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            tx = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Unscoped legacy records remain history, but are never operationally
        # assigned to the Set that merely happens to be open.
        if not tx.get("undone") and (song_key is None or tx.get("song_key") == song_key):
            return p, tx
    return None, None


def list_transactions(state_dir: Path, limit: int = 50) -> list[dict[str, Any]]:
    d = state_dir / "transactions"
    result = []
    if not d.exists():
        return result
    for p in sorted(d.glob("*.json"), reverse=True)[:limit]:
        try:
            tx = json.loads(p.read_text(encoding="utf-8"))
            result.append({
                "path": str(p),
                "id": tx.get("id"),
                "created_at": tx.get("created_at"),
                "label": tx.get("label"),
                "undone": tx.get("undone", False),
                "song_key": tx.get("song_key"),
                "ownership_scoped": bool(tx.get("song_key")),
                "actions": tx.get("actions") or [],
            })
        except Exception:
            pass
    return result
