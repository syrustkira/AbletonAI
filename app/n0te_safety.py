from __future__ import annotations

from pathlib import Path
import json
import threading
import time

from n0te_state import atomic_write_json


class SafetyController:
    """Persistent authority freeze. It never rolls back creative work."""
    def __init__(self, state: Path):
        self.path = Path(state) / "safety_state.json"
        self._lock = threading.RLock()

    def status(self) -> dict[str, object]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict): return value
        except (OSError, ValueError): pass
        return {"safe": False, "mutation_authority": True, "remote_authority": False, "recovery_required": False}

    def enter(self, reason: str = "user") -> dict[str, object]:
        with self._lock:
            value = {"safe": True, "mutation_authority": False, "remote_authority": False,
                     "ai_paused": True, "network_paused": True, "community_paused": True,
                     "background_paused": True, "recovery_required": False, "reason": reason, "updated_at": time.time()}
            atomic_write_json(self.path, value); return value

    def leave(self, *, explicit_user_confirmation: bool = False) -> dict[str, object]:
        if not explicit_user_confirmation: raise PermissionError("Leaving N0TE SAFE requires explicit user confirmation")
        with self._lock:
            value = {"safe": False, "mutation_authority": True, "remote_authority": False,
                     "recovery_required": False, "updated_at": time.time()}
            atomic_write_json(self.path, value); return value

    def require_mutation_authority(self) -> None:
        if not self.status().get("mutation_authority", False):
            raise PermissionError("N0TE SAFE has revoked mutation authority")
