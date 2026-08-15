"""Deterministic Remote Script and local-service diagnostics."""
from __future__ import annotations

import json
import os
import re
import socket
from pathlib import Path
from typing import Any


def _probe(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), 0.6):
            return True
    except OSError:
        return False


def remote_script_doctor(state: Path, home: Path | None = None) -> dict[str, Any]:
    home = home or Path.home()
    manifest_path = state / "install_manifest.json"
    manifest: dict[str, Any] = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    configured = str(manifest.get("ableton_user_library") or os.environ.get("ABLETON_USER_LIBRARY") or "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    candidates += [home / "Music/Ableton/User Library", home / "Documents/Ableton/User Library"]
    user_library = next((p for p in candidates if p.exists()), candidates[0])
    remote = user_library / "Remote Scripts" / "Ableton_Live_MCP"
    required = [remote / "__init__.py", remote / "Ableton_Live_MCP" / "__init__.py", remote / "Ableton_Live_MCP" / "bridge.py"]
    missing = [str(p) for p in required if not p.is_file()]
    nested_extra = (remote / "Ableton_Live_MCP" / "Ableton_Live_MCP").is_dir()
    log_candidates = list((home / "Library/Preferences/Ableton").glob("Live */Log.txt"))
    latest_log = max(log_candidates, key=lambda p: p.stat().st_mtime) if log_candidates else None
    relevant: list[str] = []
    loaded_evidence = False
    if latest_log:
        try:
            lines = latest_log.read_text(encoding="utf-8", errors="replace").splitlines()[-5000:]
            pattern = re.compile(r"Ableton_Live_MCP|RemoteScript|traceback|importerror|modulenotfound|syntaxerror", re.I)
            relevant = [line[-1000:] for line in lines if pattern.search(line)][-30:]
            loaded_evidence = any("Ableton_Live_MCP" in line and not re.search(r"error|traceback|failed", line, re.I) for line in relevant)
        except OSError:
            pass
    files_installed = remote.is_dir() and not missing and not nested_extra
    bridge_live = _probe(8765)
    likely_mismatch = bool(configured and not remote.exists() and any((p / "Remote Scripts/Ableton_Live_MCP").exists() for p in candidates[1:]))
    credential = bool(os.environ.get("OPENAI_API_KEY"))
    if not credential:
        try:
            credential = bool(json.loads((state / "secrets.json").read_text()).get("openai_api_key"))
        except Exception:
            pass
    return {
        "manifest_path": str(manifest_path), "manifest_user_library": configured,
        "user_library": str(user_library), "expected_remote_script": str(remote),
        "required_files": [str(p) for p in required], "missing_required_files": missing,
        "extra_nested_folder": nested_extra, "files_installed": files_installed,
        "bridge": {"endpoint": "127.0.0.1:8765", "responding": bridge_live},
        "companion": {"endpoint": "127.0.0.1:8766", "responding": _probe(8766)},
        "openai_credential_configured": credential,
        "latest_ableton_log": str(latest_log or ""), "relevant_log_lines": relevant,
        "live_loaded_script_evidence": loaded_evidence or bridge_live,
        "installed_but_not_loaded": files_installed and not (loaded_evidence or bridge_live),
        "likely_user_library_mismatch": likely_mismatch,
        "inference_note": "User-Library mismatch and log loading status are diagnostics, not proof, unless the bridge responds.",
        "repair": "Select the manifest User Library in Live, ensure exactly one Remote Scripts/Ableton_Live_MCP folder with the required nested package, then restart Live and select Ableton_Live_MCP as a Control Surface.",
    }
