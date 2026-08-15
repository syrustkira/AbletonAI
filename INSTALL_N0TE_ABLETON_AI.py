#!/usr/bin/env python3
"""
N0TE Ableton AI Python Installer

macOS-focused, standard-library-only installer/update/uninstaller for the
N0TE Ableton AI companion and pinned Ableton Remote Script.

Usage:
    python3 INSTALL_N0TE_ABLETON_AI.py
    python3 INSTALL_N0TE_ABLETON_AI.py install
    python3 INSTALL_N0TE_ABLETON_AI.py update
    python3 INSTALL_N0TE_ABLETON_AI.py uninstall
    python3 INSTALL_N0TE_ABLETON_AI.py health
    python3 INSTALL_N0TE_ABLETON_AI.py start

Optional:
    --user-library "/path/to/Ableton/User Library"
    --no-audio-tap
    --no-desktop-shortcuts
"""
from __future__ import annotations

import argparse
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

APP_NAME = "N0TE Ableton AI"
APP_VERSION = "1.2.4"
UPSTREAM_REPO = "bschoepke/ableton-live-mcp"
UPSTREAM_COMMIT = "70f7df9192b78d9bd9405f369c9e046c88f1610e"
UPSTREAM_URL = f"https://codeload.github.com/{UPSTREAM_REPO}/zip/{UPSTREAM_COMMIT}"
MIN_PYTHON = (3, 10)
UPSTREAM_BRIDGE_BLOB_SHA1 = "ecc4fd7945ea748582b0534bf5ea119a878933eb"
MANIFEST_SCHEMA = 2

SCRIPT_DIR = Path(__file__).resolve().parent
HOME = Path.home()
INSTALL_ROOT = HOME / "Library" / "Application Support" / APP_NAME
STATE = HOME / ".n0te-ableton-ai"
BACKUPS = STATE / "backups"
MANIFEST = STATE / "install_manifest.json"


def say(message: str = "") -> None:
    print(message, flush=True)


def require_python() -> None:
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required; "
            f"found {sys.version.split()[0]}."
        )


def load_existing_manifest() -> dict:
    if not MANIFEST.is_file():
        return {}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def choose_user_library_gui() -> Path | None:
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return None
    script = (
        'try\n'
        'set chosenFolder to choose folder with prompt "Select your Ableton User Library folder"\n'
        'POSIX path of chosenFolder\n'
        'on error number -128\n'
        'return ""\n'
        'end try'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_dir() else None


def resolve_user_library(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("ABLETON_USER_LIBRARY"):
        candidates.append(Path(os.environ["ABLETON_USER_LIBRARY"]).expanduser())

    previous = load_existing_manifest()
    previous_path = previous.get("ableton_user_library")
    if previous_path:
        candidates.append(Path(str(previous_path)).expanduser())

    candidates.extend(
        [
            HOME / "Music" / "Ableton" / "User Library",
            HOME / "Documents" / "Ableton" / "User Library",
        ]
    )
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            return path.resolve()

    chosen = choose_user_library_gui()
    if chosen is not None:
        return chosen

    tried = "\n".join(f"  - {p}" for p in candidates)
    raise RuntimeError(
        "Could not locate an Ableton User Library.\n"
        "Rerun and select it when prompted, pass --user-library '/path/to/User Library', "
        "or set ABLETON_USER_LIBRARY.\n"
        f"Checked:\n{tried}"
    )


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def download(url: str, destination: Path, attempts: int = 3) -> None:
    last_error = None
    headers = {"User-Agent": f"N0TE-Ableton-AI/{APP_VERSION}"}
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            say(f"Downloading pinned Ableton bridge ({attempt}/{attempts})…")
            with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as out:
                shutil.copyfileobj(response, out)
            if destination.stat().st_size < 1024:
                raise RuntimeError("Downloaded bridge archive is unexpectedly small.")
            return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError) as exc:
            last_error = exc
            if destination.exists():
                destination.unlink()
            if attempt < attempts:
                time.sleep(min(attempt * 1.5, 3.0))
    raise RuntimeError(f"Could not download pinned bridge: {last_error}")


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def unpack_upstream(archive: Path, destination: Path) -> Path:
    destination = destination.resolve()
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"Bridge archive failed ZIP integrity at {bad}.")
        for info in zf.infolist():
            target = (destination / info.filename).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(f"Unsafe path in bridge archive: {info.filename}")
        zf.extractall(destination)

    expected = destination / f"ableton-live-mcp-{UPSTREAM_COMMIT}"
    if not expected.is_dir():
        raise RuntimeError("Pinned bridge archive did not unpack to the expected commit directory.")
    required = [
        expected / "Ableton_Live_MCP" / "bridge.py",
        expected / "Ableton_Live_MCP" / "__init__.py",
        expected / "scripts" / "build_agent_audio_tap.py",
        expected / "LICENSE",
    ]
    missing = [str(path.relative_to(expected)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Pinned bridge archive is incomplete: " + ", ".join(missing))
    actual_blob = _git_blob_sha1(expected / "Ableton_Live_MCP" / "bridge.py")
    if actual_blob != UPSTREAM_BRIDGE_BLOB_SHA1:
        raise RuntimeError(
            "Pinned bridge content verification failed for Ableton_Live_MCP/bridge.py. "
            f"Expected Git blob {UPSTREAM_BRIDGE_BLOB_SHA1}, got {actual_blob}."
        )
    return expected


class InstallTransaction:
    def __init__(self, stamp: str, previous_manifest: dict | None = None):
        self.stamp = stamp
        self.previous_manifest = previous_manifest or {}
        self.previous_touched = {str(Path(p).expanduser()) for p in self.previous_manifest.get("touched_paths", [])}
        prior_restore = self.previous_manifest.get("restore_backups")
        if prior_restore is None:
            prior_restore = self.previous_manifest.get("backups", [])
        self.carried_restore_backups = [dict(item) for item in (prior_restore or []) if isinstance(item, dict)]
        self.touched: list[Path] = []
        self.backed: list[dict] = []
        self.completed = False

    def backup(self, path: Path, restore_on_uninstall: bool | None = None) -> Path | None:
        if not path.exists() and not path.is_symlink():
            return None
        if restore_on_uninstall is None:
            restore_on_uninstall = str(path) not in self.previous_touched
        BACKUPS.mkdir(parents=True, exist_ok=True)
        destination = BACKUPS / f"{path.name}_{self.stamp}_{len(self.backed)}"
        say(f"Backing up existing: {path}")
        shutil.move(str(path), str(destination))
        self.backed.append({
            "original": path,
            "backup": destination,
            "restore_on_uninstall": bool(restore_on_uninstall),
        })
        return destination

    def touch(self, path: Path) -> None:
        if path not in self.touched:
            self.touched.append(path)

    def restore_specific(self, target: Path) -> bool:
        for entry in reversed(self.backed):
            original = entry["original"]
            backup = entry["backup"]
            if original != target:
                continue
            if not backup.exists() and not backup.is_symlink():
                continue
            if original.exists() or original.is_symlink():
                remove_path(original)
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup), str(original))
            return True
        return False

    def rollback(self) -> None:
        if self.completed:
            return
        say()
        say("Install failed. Rolling back N0TE-managed changes…")
        for path in reversed(self.touched):
            try:
                if path.exists() or path.is_symlink():
                    remove_path(path)
            except Exception as exc:
                say(f"Warning: could not remove {path}: {exc}")
        for entry in reversed(self.backed):
            original = entry["original"]
            backup = entry["backup"]
            try:
                if not backup.exists() and not backup.is_symlink():
                    continue
                if original.exists() or original.is_symlink():
                    continue
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(backup), str(original))
                say(f"Restored: {original}")
            except Exception as exc:
                say(f"Warning: could not restore {original}: {exc}")

    def manifest(self, user_library: Path, audio_status: str) -> dict:
        restore_backups = list(self.carried_restore_backups)
        rollback_backups = []
        for entry in self.backed:
            item = {"original": str(entry["original"]), "backup": str(entry["backup"])}
            if entry["restore_on_uninstall"]:
                restore_backups.append(item)
            else:
                rollback_backups.append(item)

        # Preserve ordering but avoid exact duplicate entries across upgrades.
        seen = set()
        restore_unique = []
        for item in restore_backups:
            key = (str(item.get("original", "")), str(item.get("backup", "")))
            if not all(key) or key in seen:
                continue
            seen.add(key)
            restore_unique.append({"original": key[0], "backup": key[1]})

        return {
            "manifest_schema": MANIFEST_SCHEMA,
            "product": APP_NAME,
            "version": APP_VERSION,
            "installed_at": time.time(),
            "upstream_repo": UPSTREAM_REPO,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_bridge_blob_sha1": UPSTREAM_BRIDGE_BLOB_SHA1,
            "ableton_user_library": str(user_library),
            "audio_tap": audio_status,
            "touched_paths": [str(p) for p in self.touched],
            "backups": restore_unique,
            "restore_backups": restore_unique,
            "rollback_backups": rollback_backups,
            "install_transaction": "complete",
            "installer": "python",
            "python": sys.version.split()[0],
            "python_executable": str(Path(sys.executable).resolve()),
        }


def copy_app() -> None:
    source = SCRIPT_DIR / "app"
    if not source.is_dir():
        raise RuntimeError(f"Bundled app directory is missing: {source}")
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, INSTALL_ROOT, dirs_exist_ok=True)


def install_license_files(upstream: Path, remote: Path) -> None:
    third_party = INSTALL_ROOT / "third_party"
    third_party.mkdir(parents=True, exist_ok=True)
    upstream_license = upstream / "LICENSE"
    if upstream_license.is_file():
        shutil.copy2(upstream_license, remote / "LICENSE")
        shutil.copy2(upstream_license, third_party / "ableton-live-mcp-LICENSE.txt")
    project_license = SCRIPT_DIR / "LICENSE"
    if project_license.is_file():
        shutil.copy2(project_license, INSTALL_ROOT / "LICENSE")
    modifications = SCRIPT_DIR / "MODIFICATIONS.md"
    if modifications.is_file():
        shutil.copy2(modifications, INSTALL_ROOT / "MODIFICATIONS.md")


def write_launchers() -> tuple[Path, Path, Path]:
    launchers = INSTALL_ROOT / "launchers"
    launchers.mkdir(parents=True, exist_ok=True)
    start = launchers / "START_N0TE.command"
    health = launchers / "HEALTHCHECK.command"
    uninstall = launchers / "UNINSTALL_N0TE.command"

    python_exe = str(Path(sys.executable).resolve())
    quoted_python = "'" + python_exe.replace("'", "'\"'\"'") + "'"
    start.write_text(
        '#!/bin/bash\n'
        'set -e\n'
        'APP="$HOME/Library/Application Support/N0TE Ableton AI"\n'
        f'exec {quoted_python} "$APP/n0te_server.py"\n',
        encoding="utf-8",
    )
    health.write_text(
        '#!/bin/bash\n'
        'APP="$HOME/Library/Application Support/N0TE Ableton AI"\n'
        f'{quoted_python} "$APP/healthcheck.py"\n'
        'echo\n'
        'read -n 1 -s -r -p "Press any key to close…"\n',
        encoding="utf-8",
    )
    uninstall.write_text(
        '#!/bin/bash\n'
        'set -e\n'
        'APP="$HOME/Library/Application Support/N0TE Ableton AI"\n'
        f'exec {quoted_python} "$APP/n0te_uninstall.py"\n',
        encoding="utf-8",
    )
    for path in (start, health, uninstall):
        path.chmod(0o755)
    return start, health, uninstall


def create_symlink(link: Path, target: Path, tx: InstallTransaction) -> None:
    if link.exists() or link.is_symlink():
        tx.backup(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    tx.touch(link)


def build_audio_tap(upstream: Path, user_library: Path, tx: InstallTransaction) -> str:
    tap = user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AgentAudioTap.amxd"
    tap_js = user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "agent_audio_tap.js"
    log = Path(tempfile.gettempdir()) / "n0te_audio_tap.log"

    tx.backup(tap)
    tx.backup(tap_js)

    env = os.environ.copy()
    env["ABLETON_USER_LIBRARY"] = str(user_library)
    command = [sys.executable, str(upstream / "scripts" / "build_agent_audio_tap.py"), "--install"]
    say("Building AgentAudioTap…")
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=upstream,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    if result.returncode == 0:
        if tap.exists():
            tx.touch(tap)
        if tap_js.exists():
            tx.touch(tap_js)
        return "installed"

    # AudioTap is optional. Restore only the prior AudioTap assets and continue.
    for item in (tap, tap_js):
        if item.exists() or item.is_symlink():
            remove_path(item)
        tx.restore_specific(item)
    say("Audio Tap build did not complete. Previous tap was restored where available.")
    say(f"Details: {log}")
    return "previous_restored_or_not_installed"


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _installed_python_from_manifest() -> str:
    data = load_existing_manifest()
    candidate = str(data.get("python_executable") or "")
    if candidate and Path(candidate).is_file():
        return candidate
    return sys.executable


def cleanup_old_rollback_backups(manifest: dict) -> list[str]:
    """Remove rollback-only snapshots from a previous completed install.

    They exist only to recover a failed update. Once a newer update has
    completed successfully, retaining older version snapshots creates
    untracked state and disk growth without providing an exposed rollback path.
    """
    warnings = []
    for item in manifest.get("rollback_backups", []) or []:
        backup = Path(str(item.get("backup") or "")).expanduser()
        if not _backup_source_allowed(backup):
            warnings.append(f"Refused old rollback cleanup outside N0TE backup directory: {backup}")
            continue
        try:
            if backup.exists() or backup.is_symlink():
                remove_path(backup)
        except Exception as exc:
            warnings.append(f"Could not remove old rollback snapshot {backup}: {exc}")
    return warnings


def install(args: argparse.Namespace) -> int:
    require_python()
    if sys.platform != "darwin":
        say("Warning: this installer is designed and tested for macOS/Ableton Live.")

    user_library = resolve_user_library(args.user_library)
    STATE.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    say(f"== {APP_NAME} {APP_VERSION} ==")
    say(f"Ableton User Library: {user_library}")
    say(f"Pinned Ableton bridge: {UPSTREAM_REPO}@{UPSTREAM_COMMIT}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    previous_manifest = load_existing_manifest()
    tx = InstallTransaction(stamp, previous_manifest)

    remote = user_library / "Remote Scripts" / "Ableton_Live_MCP"
    tap = user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AgentAudioTap.amxd"
    tap_js = user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "agent_audio_tap.js"
    desktop_start = HOME / "Desktop" / "START N0TE Ableton AI.command"
    desktop_health = HOME / "Desktop" / "N0TE Ableton AI Healthcheck.command"

    prototypes = [
        user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AbletonMCP_M4L",
        user_library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AbletonMCP.amxd",
    ]

    try:
        # Validate/download before moving working files.
        with tempfile.TemporaryDirectory(prefix="n0te_install_") as tmp_text:
            tmp = Path(tmp_text)
            archive = tmp / "upstream.zip"
            extracted = tmp / "src"
            extracted.mkdir()
            download(UPSTREAM_URL, archive)
            upstream = unpack_upstream(archive, extracted)

            for prototype in prototypes:
                tx.backup(prototype)

            tx.backup(remote)
            tx.backup(INSTALL_ROOT)
            if not args.no_desktop_shortcuts:
                tx.backup(desktop_start)
                tx.backup(desktop_health)

            remote.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(upstream / "Ableton_Live_MCP", remote)
            tx.touch(remote)

            copy_app()
            tx.touch(INSTALL_ROOT)
            install_license_files(upstream, remote)

            if args.no_audio_tap:
                audio_status = "skipped"
            else:
                audio_status = build_audio_tap(upstream, user_library, tx)

            start_launcher, health_launcher, uninstall_launcher = write_launchers()

            if not args.no_desktop_shortcuts:
                # Already backed above; create directly to avoid double backup.
                desktop_start.parent.mkdir(parents=True, exist_ok=True)
                desktop_start.symlink_to(start_launcher)
                desktop_health.symlink_to(health_launcher)
                tx.touch(desktop_start)
                tx.touch(desktop_health)

        manifest_data = tx.manifest(user_library, audio_status)
        atomic_write_json(MANIFEST, manifest_data)
        tx.completed = True
        for warning in cleanup_old_rollback_backups(previous_manifest):
            say(f"Warning: {warning}")
    except Exception:
        tx.rollback()
        raise

    say()
    say("Installed successfully.")
    say("1) Restart Ableton Live.")
    say("2) In Live Preferences > MIDI, select Control Surface: Ableton_Live_MCP if needed.")
    say(f"3) Run: {sys.executable} INSTALL_N0TE_ABLETON_AI.py start")
    if not args.no_desktop_shortcuts:
        say("   Or double-click: ~/Desktop/START N0TE Ableton AI.command")
    say("4) Open Settings in N0TE and save your OpenAI API key.")
    say(f"Audio Tap status: {audio_status}")
    say("Your N0TE state/history in ~/.n0te-ableton-ai is preserved across upgrades.")
    return 0


def _allowed_managed_paths(data: dict) -> set[Path]:
    raw_user = str(data.get("ableton_user_library") or "").strip()
    allowed = {
        INSTALL_ROOT,
        HOME / "Desktop" / "START N0TE Ableton AI.command",
        HOME / "Desktop" / "N0TE Ableton AI Healthcheck.command",
    }
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


def _backup_source_allowed(path: Path) -> bool:
    try:
        path.resolve().relative_to(BACKUPS.resolve())
        return True
    except (ValueError, FileNotFoundError):
        return False


def uninstall(_args: argparse.Namespace) -> int:
    if not MANIFEST.is_file():
        say("No N0TE install manifest found. Nothing will be guessed or deleted.")
        return 0

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allowed = _allowed_managed_paths(data)
    errors = []

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
        original = Path(item["original"]).expanduser()
        backup = Path(item["backup"]).expanduser()
        if original not in allowed:
            errors.append(f"Refused unexpected restore destination from manifest: {original}")
            continue
        if not _backup_source_allowed(backup):
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

    # Rollback-only version snapshots are N0TE-owned and are not restored on uninstall.
    for item in data.get("rollback_backups", []) or []:
        backup = Path(str(item.get("backup") or "")).expanduser()
        if not _backup_source_allowed(backup):
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
    if archive.exists():
        archive.unlink()
    MANIFEST.replace(archive)
    say("Uninstalled N0TE-managed files and restored pre-N0TE backups where safe.")
    say(f"State/journal retained at {STATE}.")
    return 0


def run_installed_script(filename: str) -> int:
    script = INSTALL_ROOT / filename
    if not script.is_file():
        say(f"N0TE is not installed: {script} is missing.")
        say("Run this installer first.")
        return 1
    python_exe = _installed_python_from_manifest()
    return subprocess.call([python_exe, str(script)])


def health(_args: argparse.Namespace) -> int:
    return run_installed_script("healthcheck.py")


def start(_args: argparse.Namespace) -> int:
    script = INSTALL_ROOT / "n0te_server.py"
    if not script.is_file():
        say("N0TE is not installed yet. Run install first.")
        return 1
    python_exe = _installed_python_from_manifest()
    os.execv(python_exe, [python_exe, str(script)])
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Install, update, launch, health-check, or uninstall N0TE Ableton AI.",
    )
    p.add_argument(
        "command",
        nargs="?",
        default="install",
        choices=("install", "update", "uninstall", "health", "start"),
        help="Action to perform. Default: install.",
    )
    p.add_argument(
        "--user-library",
        help="Explicit Ableton User Library path.",
    )
    p.add_argument(
        "--no-audio-tap",
        action="store_true",
        help="Skip optional AgentAudioTap build/install.",
    )
    p.add_argument(
        "--no-desktop-shortcuts",
        action="store_true",
        help="Do not create Desktop launch/health-check shortcuts.",
    )
    return p


def main() -> int:
    args = parser().parse_args()
    actions = {
        "install": install,
        "update": install,
        "uninstall": uninstall,
        "health": health,
        "start": start,
    }
    try:
        return actions[args.command](args)
    except KeyboardInterrupt:
        say("\nCancelled.")
        return 130
    except Exception as exc:
        say(f"\nERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
