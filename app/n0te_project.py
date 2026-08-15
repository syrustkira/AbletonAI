from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
import threading
from pathlib import Path
from typing import Any
from n0te_state import atomic_write_json


STAGES = ["CREATE", "ARRANGE", "PRODUCE", "MIX", "MASTER", "FINISH"]


class ProjectStore:
    """Persistent per-song semantic state with stable unsaved-set identity.

    Unsaved Sets no longer key themselves from set_signature, because that changes
    on normal edits. A stable token is retained while the Set is unsaved, then its
    song/checkpoint/decision/discovery/conversation state is migrated when a file
    path appears.
    """

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.song_dir = state_dir / "songs"
        self.checkpoint_dir = state_dir / "checkpoints"
        self.decision_dir = state_dir / "decisions"
        self.discovery_dir = state_dir / "discovery"
        self.conversation_dir = state_dir / "conversations"
        self.identity_path = state_dir / "project_identity.json"
        self.runtime_token = uuid.uuid4().hex
        self._identity_lock = threading.RLock()
        self._song_state_lock = threading.RLock()
        for p in (self.song_dir, self.checkpoint_dir, self.decision_dir, self.discovery_dir, self.conversation_dir):
            p.mkdir(parents=True, exist_ok=True)

    def _saved_key(self, file_path: str) -> str:
        basis = os.path.abspath(os.path.expanduser(file_path))
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    def _load_identity(self) -> dict[str, Any]:
        try:
            value = json.loads(self.identity_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except Exception:
            pass
        return {"version": 2, "active_unsaved": None}

    def _save_identity(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.identity_path, value)

    def _song_anchor(self, snapshot: dict[str, Any]) -> str:
        song = snapshot.get("song") or {}
        for candidate in (song.get("id"), song.get("object_id"), song.get("ref")):
            if candidate not in (None, ""):
                return str(candidate)
        return ""

    def _new_unsaved_key(self) -> tuple[str, str]:
        token = uuid.uuid4().hex
        return hashlib.sha1(("unsaved:" + token).encode("utf-8")).hexdigest()[:16], token

    def _migrate_key(self, source_key: str, target_key: str) -> None:
        if not source_key or source_key == target_key:
            return

        source_song = self.song_dir / f"{source_key}.json"
        target_song = self.song_dir / f"{target_key}.json"
        if source_song.exists():
            try:
                source = json.loads(source_song.read_text(encoding="utf-8"))
            except Exception:
                source = {}
            try:
                target = json.loads(target_song.read_text(encoding="utf-8")) if target_song.exists() else {}
            except Exception:
                target = {}
            merged = dict(source)
            merged.update(target)  # Explicit saved-key state wins if it already exists.
            atomic_write_json(target_song, merged)
            try:
                source_song.unlink()
            except FileNotFoundError:
                pass

        for root in (self.checkpoint_dir, self.discovery_dir, self.conversation_dir):
            src = root / source_key
            dst = root / target_key
            if not src.exists():
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for path in src.glob("*.json"):
                target = dst / path.name
                if target.exists():
                    target = dst / (path.stem + "_migrated" + path.suffix)
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        data["song_key"] = target_key
                        atomic_write_json(target, data)
                    else:
                        shutil.copy2(path, target)
                except Exception:
                    shutil.copy2(path, target)
            shutil.rmtree(src, ignore_errors=True)

        for path in self.decision_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("song_key") == source_key:
                    data["song_key"] = target_key
                    atomic_write_json(path, data)
            except Exception:
                continue

        # Transactions remain in the global journal for chronological history,
        # but ownership follows a proven unsaved -> Save As identity migration.
        transaction_dir = self.state_dir / "transactions"
        for path in transaction_dir.glob("*.json") if transaction_dir.exists() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("song_key") == source_key:
                    data["song_key"] = target_key
                    data["ownership_migrated_from"] = source_key
                    atomic_write_json(path, data)
            except Exception:
                continue

    def song_key(self, snapshot: dict[str, Any]) -> str:
        with self._identity_lock:
            props = snapshot.get("song", {}).get("properties", {})
            file_path = str(props.get("file_path") or "").strip()
            signature = str(snapshot.get("set", {}).get("set_signature") or "")
            anchor = self._song_anchor(snapshot)
            identity = self._load_identity()
            active = identity.get("active_unsaved") if isinstance(identity.get("active_unsaved"), dict) else None

            if file_path:
                target = self._saved_key(file_path)
                # Process/runtime identity is not Set identity. Automatic Save As
                # migration requires a stable Song/Set anchor observed on both
                # sides; signatures may change on save and are not identity proof.
                continuity = bool(active and anchor and active.get("anchor") and str(active.get("anchor")) == anchor)
                if continuity and active and active.get("key") and active.get("key") != target:
                    # Saving an unsaved Set can change the set signature. Migrate only
                    # when we have continuity evidence, never from a stale unrelated Set.
                    self._migrate_key(str(active["key"]), target)
                # Preserve an unrelated/unproven unsaved Set's ownership. It may
                # become observable again; never assign its state to this path.
                if continuity:
                    identity["active_unsaved"] = None
                identity["last_saved_key"] = target
                identity["last_saved_path"] = os.path.abspath(os.path.expanduser(file_path))
                identity["updated_at"] = time.time()
                self._save_identity(identity)
                return target

            reuse = False
            if active:
                if anchor and active.get("anchor") and str(active.get("anchor")) == anchor:
                    reuse = True
                elif signature and str(active.get("last_signature") or "") == signature:
                    # Supports companion restart while the unsaved Set itself has not changed.
                    reuse = True
                elif not anchor and time.time() - float(active.get("updated_at") or 0) < 12 * 3600:
                    # Fallback for bridges that do not expose a stable Song object id.
                    # This intentionally favors continuity over fragmenting state on edits.
                    reuse = True

            if not reuse:
                key, token = self._new_unsaved_key()
                active = {"key": key, "token": token, "anchor": anchor, "created_at": time.time()}

            active["runtime_token"] = self.runtime_token
            active["anchor"] = anchor or active.get("anchor") or ""
            active["last_signature"] = signature
            active["updated_at"] = time.time()
            identity["active_unsaved"] = active
            identity["updated_at"] = time.time()
            self._save_identity(identity)
            return str(active["key"])
    def song_state_path(self, snapshot: dict[str, Any]) -> Path:
        return self.song_dir / f"{self.song_key(snapshot)}.json"

    def load_song(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        path = self.song_state_path(snapshot)
        default = {
            "version": 2,
            "stage": "CREATE",
            "song_intent": "",
            "session_goal": "",
            "next_action": "",
            "do_not_work_on": [],
            "do_not_lose": [],
            "references": {"emotion": "", "groove_motif": "", "payoff": "", "self_reference": ""},
            "key_center": "",
            "scale": "",
            "chord_map": "",
            "notes": "",
            "updated_at": None,
        }
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                default.update(loaded)
        except Exception:
            pass
        return default

    def save_song(self, snapshot: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
        with self._song_state_lock:
            state = self.load_song(snapshot)
            allowed = {"stage", "song_intent", "session_goal", "next_action", "do_not_work_on", "do_not_lose", "references", "key_center", "scale", "chord_map", "notes"}
            for key, value in update.items():
                if key in allowed:
                    state[key] = value
            if state.get("stage") not in STAGES:
                state["stage"] = "CREATE"
            state["updated_at"] = time.time()
            atomic_write_json(self.song_state_path(snapshot), state)
            return state

    def checkpoint(self, snapshot: dict[str, Any], song_state: dict[str, Any], context_status: dict[str, Any], library_summary: dict[str, Any], label: str = "") -> dict[str, Any]:
        key = self.song_key(snapshot)
        now = time.time()
        data = {"version": 2, "created_at": now, "label": label or "Checkpoint", "song_key": key, "set_signature": snapshot.get("set", {}).get("set_signature"), "snapshot": snapshot, "song_state": song_state, "context": context_status, "library": library_summary}
        d = self.checkpoint_dir / key
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{int(now)}_{_slug(label or 'checkpoint')}.json"
        atomic_write_json(path, data)
        return {"path": str(path), **data}

    def list_checkpoints(self, snapshot: dict[str, Any], limit: int = 30) -> list[dict[str, Any]]:
        d = self.checkpoint_dir / self.song_key(snapshot)
        result = []
        if not d.exists():
            return result
        for path in sorted(d.glob("*.json"), reverse=True)[:limit]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result.append({"path": str(path), "created_at": data.get("created_at"), "label": data.get("label"), "set_signature": data.get("set_signature")})
            except Exception:
                pass
        return result

    def latest_checkpoint(self, snapshot: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
        d = self.checkpoint_dir / self.song_key(snapshot)
        if not d.exists():
            return None, None
        for path in sorted(d.glob("*.json"), reverse=True):
            try:
                return path, json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
        return None, None

    def compare_latest(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        path, previous = self.latest_checkpoint(snapshot)
        if not previous:
            return {"has_checkpoint": False, "changes": []}
        changes = compare_snapshots(previous.get("snapshot") or {}, snapshot)
        return {"has_checkpoint": True, "checkpoint": {"path": str(path), "label": previous.get("label"), "created_at": previous.get("created_at")}, "changes": changes}

    def record_decision(self, snapshot: dict[str, Any], title: str, why: str, status: str = "accepted", source: str = "user+n0te", details: dict[str, Any] | None = None) -> dict[str, Any]:
        item = {"created_at": time.time(), "song_key": self.song_key(snapshot), "title": title, "why": why, "status": status, "source": source, "details": details or {}}
        path = self.decision_dir / f"{int(item['created_at']*1000)}_{_slug(title)}.json"
        atomic_write_json(path, item)
        item["path"] = str(path)
        return item

    def record_discovery(self, snapshot: dict[str, Any], item: dict[str, Any], status: str = "tried", note: str = "") -> dict[str, Any]:
        row = {"created_at": time.time(), "song_key": self.song_key(snapshot), "status": status if status in ("tried", "used", "rejected", "saved") else "tried", "note": str(note or ""), "item": item if isinstance(item, dict) else {}}
        d = self.discovery_dir / row["song_key"]
        d.mkdir(parents=True, exist_ok=True)
        title = str((row["item"] or {}).get("title") or (row["item"] or {}).get("name") or "sound")
        path = d / f"{int(row['created_at']*1000)}_{_slug(title)}.json"
        atomic_write_json(path, row)
        row["path"] = str(path)
        return row

    def list_discovery(self, snapshot: dict[str, Any], limit: int = 80) -> list[dict[str, Any]]:
        d = self.discovery_dir / self.song_key(snapshot)
        if not d.exists():
            return []
        rows = []
        for path in sorted(d.glob("*.json"), reverse=True)[:limit]:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                row["path"] = str(path)
                rows.append(row)
            except Exception:
                pass
        return rows

    def append_conversation(self, snapshot: dict[str, Any], role: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        role = role if role in ("user", "assistant", "system") else "user"
        row = {"created_at": time.time(), "song_key": self.song_key(snapshot), "role": role, "text": str(text or ""), "metadata": metadata or {}}
        d = self.conversation_dir / row["song_key"]
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{int(row['created_at']*1000000)}_{role}.json"
        atomic_write_json(path, row)
        row["path"] = str(path)
        return row

    def list_conversation(self, snapshot: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
        d = self.conversation_dir / self.song_key(snapshot)
        if not d.exists():
            return []
        rows = []
        for path in sorted(d.glob("*.json"), reverse=True)[:limit]:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict):
                    rows.append(row)
            except Exception:
                pass
        rows.reverse()
        return rows

    def list_decisions(self, snapshot: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        key = self.song_key(snapshot)
        rows = []
        for path in sorted(self.decision_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("song_key") != key:
                    continue
                data["path"] = str(path)
                rows.append(data)
                if len(rows) >= limit:
                    break
            except Exception:
                pass
        return rows

def _slug(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "_" for c in str(text)).strip("_")
    return out[:60] or "item"


def flatten_tracks(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result = {}
    for track in snapshot.get("set", {}).get("tracks") or []:
        if isinstance(track, dict) and isinstance(track.get("id"), int):
            result[track["id"]] = track
    return result


def compare_snapshots(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    old_set, new_set = old.get("set", {}), new.get("set", {})
    if old_set.get("tempo") != new_set.get("tempo"):
        changes.append({"type": "tempo", "before": old_set.get("tempo"), "after": new_set.get("tempo")})

    old_tracks, new_tracks = flatten_tracks(old), flatten_tracks(new)
    for tid in sorted(set(old_tracks) - set(new_tracks)):
        changes.append({"type": "track_removed", "track": old_tracks[tid].get("name"), "id": tid})
    for tid in sorted(set(new_tracks) - set(old_tracks)):
        changes.append({"type": "track_added", "track": new_tracks[tid].get("name"), "id": tid})
    for tid in sorted(set(old_tracks) & set(new_tracks)):
        a, b = old_tracks[tid], new_tracks[tid]
        for prop in ("name", "mute", "solo", "arm"):
            if a.get(prop) != b.get(prop):
                changes.append({"type": f"track_{prop}", "track": b.get("name") or a.get("name"), "before": a.get(prop), "after": b.get(prop)})
        a_devices = [(d.get("name"), d.get("class_name")) for d in a.get("devices") or [] if isinstance(d, dict)]
        b_devices = [(d.get("name"), d.get("class_name")) for d in b.get("devices") or [] if isinstance(d, dict)]
        if a_devices != b_devices:
            changes.append({"type": "device_chain", "track": b.get("name"), "before": a_devices, "after": b_devices})
        a_clips = [(c.get("name"), c.get("length"), c.get("muted")) for c in a.get("arrangement_clips") or [] if isinstance(c, dict)]
        b_clips = [(c.get("name"), c.get("length"), c.get("muted")) for c in b.get("arrangement_clips") or [] if isinstance(c, dict)]
        if a_clips != b_clips:
            changes.append({"type": "arrangement_clips", "track": b.get("name"), "before_count": len(a_clips), "after_count": len(b_clips)})
    return changes[:200]


def finish_checklist(snapshot: dict[str, Any], song_state: dict[str, Any], preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    """Scope/finish gate. It deliberately refuses to claim export readiness without audio preflight evidence."""
    stage = song_state.get("stage") or "CREATE"
    set_data = snapshot.get("set", {})
    tracks = [t for t in set_data.get("tracks") or [] if isinstance(t, dict) and not t.get("truncated")]
    must: list[str] = []
    probably: list[str] = []
    leave: list[str] = []
    limitations: list[str] = []

    if not song_state.get("song_intent"):
        probably.append("Write one sentence for what the song is trying to communicate.")
    if not song_state.get("session_goal"):
        probably.append("Choose one session goal so the next work block has a finish line.")
    if not tracks:
        must.append("The Live Set contains no visible production tracks.")
    soloed = [str(t.get("name") or "Track") for t in tracks if t.get("solo")]
    if soloed:
        probably.append("Review soloed tracks before export: " + ", ".join(soloed[:8]))
    if stage in ("CREATE", "ARRANGE"):
        leave.extend(["final loudness", "mastering polish", "micro-EQ that does not solve an audible problem"])
    if stage == "FINISH":
        leave.extend(["new sound-design directions", "new plugin experiments", "rewriting sections that already communicate unless a concrete problem is named"])
    if not song_state.get("next_action"):
        probably.append("Define one smallest next action before starting another plugin/research branch.")

    preflight = preflight or {}
    missing = preflight.get("missing_assets") or []
    if missing:
        must.append(f"Resolve {len(missing)} missing exposed audio asset(s) before relying on a final export.")
    structural_preflight = bool(preflight.get("structural_preflight_complete"))
    audio_preflight = bool(preflight.get("audio_preflight_complete"))
    if not audio_preflight:
        limitations.append("Audio dry-run analysis is not implemented yet; clipping, true peak, loudness, silent tails and sonic anomalies have not been verified by N0TE.")

    scope_ready = not must and stage in ("MIX", "MASTER", "FINISH")
    ready_for_bounce = bool(scope_ready and structural_preflight and audio_preflight)
    return {
        "stage": stage,
        "must_fix": must,
        "probably_fix": probably,
        "leave_alone": leave,
        "scope_ready": scope_ready,
        "preflight_complete": bool(structural_preflight and audio_preflight),
        "audio_preflight_complete": audio_preflight,
        "limitations": limitations,
        "ready_for_bounce": ready_for_bounce,
    }
