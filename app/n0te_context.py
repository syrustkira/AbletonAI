from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import threading
from pathlib import Path
from typing import Any
from n0te_state import atomic_write_json


def _install_provider_router_for_server() -> None:
    """Install the provider switchboard only for the real N0TE server process.

    Importing n0te_context from tests or helper scripts stays side-effect free.
    """
    if Path(sys.argv[0]).name != "n0te_server.py":
        return
    try:
        import n0te_provider as provider

        placeholder = "n0te-provider-router"

        def sync_legacy_guard(active_provider: str) -> None:
            current = str(os.environ.get("OPENAI_API_KEY") or "")
            if active_provider == "openai":
                if current == placeholder:
                    os.environ.pop("OPENAI_API_KEY", None)
                return
            if not current:
                os.environ["OPENAI_API_KEY"] = placeholder

        original_update = provider._update_provider_settings

        def update_with_guard(payload: dict[str, Any]) -> dict[str, Any]:
            status = original_update(payload)
            sync_legacy_guard(str(status.get("provider") or "openai"))
            return status

        provider._update_provider_settings = update_with_guard
        sync_legacy_guard(str(provider.provider_config().get("provider") or "openai"))
        provider.install_provider_router(start_switchboard=True)
    except Exception as exc:
        print(f"N0TE AI provider router did not start: {exc}", file=sys.stderr)


_install_provider_router_for_server()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except Exception:
        return None



def _payload_sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


class ContextStore:
    """Versioned canonical context with a separately persisted override layer.

    The bundled/local base is managed by N0TE and can safely advance on upgrades.
    User or external customizations live separately so an old bundled pack can no
    longer shadow a newer build forever.
    """

    def __init__(self, bundled_path: Path, state_dir: Path):
        self.bundled_path = bundled_path
        self.state_dir = state_dir
        self.context_dir = state_dir / "context"
        self.local_path = self.context_dir / "N0TE_CONTEXT_PACK.json"
        self.override_path = self.context_dir / "N0TE_CONTEXT_OVERRIDES.json"
        self.meta_path = self.context_dir / "context_meta.json"
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _bundled(self) -> dict[str, Any]:
        return _read_json(self.bundled_path) or {"schema_version": 1, "context_version": "unknown"}

    def ensure_local(self) -> Path:
        with self._lock:
            return self._ensure_local_locked()

    def _ensure_local_locked(self) -> Path:
        bundled = self._bundled()
        bundled_sha = _payload_sha(bundled)
        current = _read_json(self.local_path) if self.local_path.exists() else None
        meta = _read_json(self.meta_path) or {}

        needs_refresh = not current or _payload_sha(current) != bundled_sha
        if needs_refresh:
            # v1.2 and earlier allowed /api/context/replace to overwrite the managed
            # base. Archive any differing local pack before refreshing so upgrades
            # cannot silently destroy user context. Obvious custom packs are also
            # promoted to the separate override layer.
            if current and self.local_path.exists():
                backup = self.context_dir / f"legacy_context_backup_{int(time.time())}.json"
                try:
                    shutil.copy2(self.local_path, backup)
                    if (not str(current.get("generated_for") or "").startswith("N0TE Ableton AI")) and not self.override_path.exists():
                        atomic_write_json(self.override_path, current)
                except Exception:
                    pass
            atomic_write_json(self.local_path, bundled)

        meta.update({
            "managed_base_sha256": bundled_sha,
            "schema_version": bundled.get("schema_version"),
            "context_version": bundled.get("context_version") or bundled.get("generated_for") or "unknown",
            "updated_at": time.time(),
        })
        atomic_write_json(self.meta_path, meta)
        return self.local_path

    def load(self, sync_path: str | None = None) -> dict[str, Any]:
        self.ensure_local()
        source_path = self.local_path
        base = _read_json(self.local_path) or self._bundled()
        sync_error = ""
        if sync_path:
            candidate = Path(sync_path).expanduser()
            external = _read_json(candidate) if candidate.is_file() else None
            if external:
                base = external
                source_path = candidate
            else:
                sync_error = "Configured context sync path is missing or invalid; managed local base is in use."

        overrides = _read_json(self.override_path) or {}
        merged = _deep_merge(base, overrides) if overrides else dict(base)
        merged["_source_path"] = str(source_path)
        merged["_sha256"] = hashlib.sha256(json.dumps(merged, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        merged["_base_sha256"] = _sha(source_path)
        merged["_override_path"] = str(self.override_path) if self.override_path.exists() else ""
        merged["_sync_error"] = sync_error
        return merged

    def replace(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Replace the user override layer, never the managed shipped base."""
        if not isinstance(payload, dict):
            raise ValueError("Context pack must be a JSON object")
        self.context_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            atomic_write_json(self.override_path, payload)
            return self.load()

    def clear_overrides(self) -> dict[str, Any]:
        try:
            self.override_path.unlink()
        except FileNotFoundError:
            pass
        return self.load()

    def status(self, sync_path: str | None = None) -> dict[str, Any]:
        current = self.load(sync_path)
        bundled = self._bundled()
        return {
            "source_path": current.get("_source_path", ""),
            "sha256": current.get("_sha256", ""),
            "base_sha256": current.get("_base_sha256", ""),
            "schema_version": current.get("schema_version"),
            "context_version": current.get("context_version") or current.get("generated_for"),
            "bundled_context_version": bundled.get("context_version") or bundled.get("generated_for"),
            "override_path": current.get("_override_path", ""),
            "overrides_active": bool(current.get("_override_path")),
            "sync_path_configured": bool(sync_path),
            "sync_path_exists": bool(sync_path and Path(sync_path).expanduser().is_file()),
            "sync_error": current.get("_sync_error", ""),
        }


def context_for_prompt(pack: dict[str, Any]) -> str:
    clean = {k: v for k, v in pack.items() if not str(k).startswith("_")}
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
