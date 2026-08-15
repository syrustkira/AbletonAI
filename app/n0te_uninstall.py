#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys

APP_NAME = "N0TE Ableton AI"
HOME = Path.home()
INSTALL_ROOT = HOME / "Library" / "Application Support" / APP_NAME
STATE = HOME / ".n0te-ableton-ai"
MANIFEST = STATE / "install_manifest.json"
BACKUPS = STATE / "backups"


def say(message: str = "") -> None:
    print(message, flush=True)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def allowed_managed_paths(data: dict) -> set[Path]:
    allowed = {
        INSTALL_ROOT,
        HOME / "Desktop" / "START N0TE Ableton AI.command",
        HOME / "Desktop" / "N0TE Ableton AI Healthcheck.command",
    }
    raw_user = str(data.get("ableton_user_library") or "").strip()
    if raw_user:
        user_library = Path(raw_user).expanduser()
        allowed.update({
            user_library / "Remote Scripts" / "Ableton_Live_MCP",
            user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AgentAudioTap.amxd",
            user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "agent_audio_tap.js",
            user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AbletonMCP_M4L",
            user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AbletonMCP.amxd",
        })
    return {p.expanduser() for p in allowed}



def backup_source_allowed(path: Path) -> bool:
    try:
        path.resolve().relative_to(BACKUPS.resolve())
        return True
    except (ValueError, FileNotFoundError):
        return False


def uninstall() -> int:
    if not MANIFEST.is_file():
        say("No N0TE install manifest found. Nothing will be guessed or deleted.")
        return 0

    if sys.stdin.isatty():
        answer = input("Uninstall N0TE managed files while keeping your N0TE history/settings? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            say("Cancelled.")
            return 0

    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        say(f"Cannot safely uninstall because the install manifest is unreadable: {exc}")
        return 1

    allowed = allowed_managed_paths(data)
    errors: list[str] = []

    for raw in reversed(data.get("touched_paths", [])):
        path = Path(raw).expanduser()
        if path not in allowed:
            errors.append(f"Refused unexpected touched path from manifest: {path}")
            continue
        if not path.exists() and not path.is_symlink():
            continue
        try:
            say(f"Removing N0TE-managed: {path}")
            remove_path(path)
        except Exception as exc:
            errors.append(f"Could not remove {path}: {exc}")

    restore_items = data.get("restore_backups")
    if restore_items is None:
        restore_items = data.get("backups", [])
    for item in reversed(restore_items or []):
        original = Path(str(item.get("original") or "")).expanduser()
        backup = Path(str(item.get("backup") or "")).expanduser()
        if original not in allowed:
            errors.append(f"Refused unexpected restore destination from manifest: {original}")
            continue
        if not backup_source_allowed(backup):
            errors.append(f"Refused backup source outside N0TE backup directory: {backup}")
            continue
        if not backup.exists() and not backup.is_symlink():
            continue
        if original.exists() or original.is_symlink():
            say(f"Not restoring backup because destination now exists: {original}")
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            say(f"Restoring: {original}")
            shutil.move(str(backup), str(original))
        except Exception as exc:
            errors.append(f"Could not restore {original}: {exc}")

    for item in data.get("rollback_backups", []) or []:
        backup = Path(str(item.get("backup") or "")).expanduser()
        if not backup_source_allowed(backup):
            errors.append(f"Refused rollback snapshot outside N0TE backup directory: {backup}")
            continue
        try:
            if backup.exists() or backup.is_symlink():
                remove_path(backup)
        except Exception as exc:
            errors.append(f"Could not remove rollback snapshot {backup}: {exc}")

    if errors:
        say("Uninstall stopped with recovery-required items:")
        for error in errors:
            say(f"  - {error}")
        say(f"Install manifest retained at {MANIFEST}.")
        return 1

    archive = STATE / "last_uninstalled_manifest.json"
    try:
        archive.unlink(missing_ok=True)
        MANIFEST.replace(archive)
    except Exception as exc:
        say(f"Files were removed, but manifest archival failed: {exc}")
        return 1

    say("Uninstalled N0TE-managed files and restored pre-N0TE backups where safe.")
    say(f"State/journal retained at {STATE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(uninstall())
