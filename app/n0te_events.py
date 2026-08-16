from __future__ import annotations

from pathlib import Path
import json
import threading
import time
import uuid
from typing import Any

from n0te_state import atomic_write_json


class EventEngine:
    def __init__(self, state: Path, max_events_per_song: int = 2000):
        self.root = Path(state) / "events"
        self.max_events_per_song = max(10, int(max_events_per_song))
        self._lock = threading.RLock()

    def append(self, event_type: str, song_id: str, workspace_id: str = "", *, source: str = "user",
               data: dict[str, Any] | None = None, linked_event: str = "") -> dict[str, Any]:
        if not event_type or not song_id:
            raise ValueError("event_type and song_id are required")
        now = time.time(); event_id = uuid.uuid4().hex
        row = {"id": event_id, "type": event_type, "song_id": song_id, "workspace_id": workspace_id,
               "timestamp": now, "source": source, "data": data or {}, "linked_event": linked_event}
        with self._lock:
            folder = self.root / song_id; folder.mkdir(parents=True, exist_ok=True)
            atomic_write_json(folder / f"{int(now * 1_000_000)}_{event_id}.json", row)
            paths = sorted(folder.glob("*.json"))
            for stale in paths[:-self.max_events_per_song]:
                stale.unlink(missing_ok=True)
        return row

    def mark(self, song_id: str, workspace_id: str, label: str, *, transport: dict[str, Any] | None = None,
             source: str = "user", linked_event: str = "") -> dict[str, Any]:
        return self.append("content_mark", song_id, workspace_id, source=source,
                           data={"label": str(label or "MARK"), "transport": transport or {}}, linked_event=linked_event)

    def recent(self, song_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            paths = sorted((self.root / song_id).glob("*.json"), reverse=True)[:max(0, limit)]
            rows = []
            for path in reversed(paths):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(value, dict): rows.append(value)
                except (OSError, ValueError):
                    continue
            return rows
