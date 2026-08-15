"""Deterministic Remote Script and local-service diagnostics."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
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
    configured_path = Path(configured).expanduser() if configured else None
    fallbacks = [home / "Music/Ableton/User Library", home / "Documents/Ableton/User Library"]
    fallback_existing = next((path for path in fallbacks if path.exists()), None)
    # A missing explicitly configured path remains the inspected/failed path;
    # a default candidate must not silently make it look healthy.
    user_library = configured_path or fallback_existing or fallbacks[0]
    remote = user_library / "Remote Scripts" / "Ableton_Live_MCP"
    # The pinned upstream package is copied directly into Remote Scripts/Ableton_Live_MCP.
    # Its required files live at the Remote Script root; an additional
    # Ableton_Live_MCP subfolder is the accidental extra-nesting case.
    required = [remote / "__init__.py", remote / "bridge.py"]
    missing = [str(p) for p in required if not p.is_file()]
    nested_extra = (remote / "Ableton_Live_MCP").is_dir()
    log_candidates = list((home / "Library/Preferences/Ableton").glob("Live */Log.txt"))
    latest_log = max(log_candidates, key=lambda p: p.stat().st_mtime) if log_candidates else None
    relevant: list[str] = []
    loaded_evidence = False
    if latest_log:
        try:
            lines = latest_log.read_text(encoding="utf-8", errors="replace").splitlines()[-5000:]
            pattern = re.compile(r"Ableton_Live_MCP|RemoteScript|traceback|importerror|modulenotfound|syntaxerror", re.I)
            relevant = [line[-1000:] for line in lines if pattern.search(line)][-30:]
            if relevant:
                latest = relevant[-1]
                loaded_evidence = "Ableton_Live_MCP" in latest and not re.search(r"error|traceback|failed|exception|syntax", latest, re.I)
        except OSError:
            pass
    files_installed = remote.is_dir() and not missing and not nested_extra
    bridge_live = _probe(8765)
    likely_mismatch = bool(configured_path and not configured_path.exists()) or bool(configured_path and not remote.exists() and any((p / "Remote Scripts/Ableton_Live_MCP").exists() for p in fallbacks))
    credential = bool(os.environ.get("OPENAI_API_KEY"))
    if not credential:
        credential = bool((state / "api_key").is_file() and (state / "api_key").stat().st_size)
    if not credential and sys.platform == "darwin":
        try:
            cp = subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", "N0TE_Ableton_AI_OpenAI", "-w"], capture_output=True, text=True, timeout=3)
            credential = cp.returncode == 0 and bool(cp.stdout.strip())
        except Exception:
            pass
    return {
        "manifest_path": str(manifest_path), "manifest_user_library": configured,
        "configured_user_library": str(configured_path or ""), "configured_path_exists": bool(configured_path and configured_path.exists()),
        "fallback_candidates": [str(path) for path in fallbacks], "fallback_existing": str(fallback_existing or ""),
        "verified_user_library": str(user_library) if user_library.exists() else "",
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
        "repair": "Select the manifest User Library in Live, ensure exactly one Remote Scripts/Ableton_Live_MCP folder containing __init__.py and bridge.py, then restart Live and select Ableton_Live_MCP as a Control Surface.",
    }
