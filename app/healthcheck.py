from pathlib import Path
import json, os, socket, sys


def probe(host, port):
    try:
        with socket.create_connection((host, port), 1):
            return True
    except OSError:
        return False

home = Path.home()
state = home / ".n0te-ableton-ai"
candidates = []
env = os.environ.get("ABLETON_USER_LIBRARY")
if env:
    candidates.append(Path(env).expanduser())
manifest = state / "install_manifest.json"
if manifest.is_file():
    try:
        recorded = str(json.loads(manifest.read_text(encoding="utf-8")).get("ableton_user_library") or "").strip()
        if recorded:
            candidates.append(Path(recorded).expanduser())
    except Exception:
        pass
candidates += [home / "Music" / "Ableton" / "User Library", home / "Documents" / "Ableton" / "User Library"]
library = next((p for p in candidates if p.exists()), candidates[0] if candidates else home / "Music" / "Ableton" / "User Library")
lib_index = state / "library" / "library_index.json"
context_pack = state / "context" / "N0TE_CONTEXT_PACK.json"
checks = {
    "python_3_10_plus": sys.version_info >= (3, 10),
    "user_library": str(library),
    "remote_script": (library / "Remote Scripts" / "Ableton_Live_MCP").is_dir(),
    "audio_tap": (library / "Presets" / "Audio Effects" / "Max Audio Effect" / "AgentAudioTap.amxd").is_file(),
    "ableton_bridge_live": probe("127.0.0.1", 8765),
    "n0te_ui_live": probe("127.0.0.1", 8766),
    "context_pack": context_pack.is_file(),
    "library_index": lib_index.is_file(),
    "library_index_bytes": lib_index.stat().st_size if lib_index.is_file() else 0,
    "transactions": len(list((state / "transactions").glob("*.json"))) if (state / "transactions").exists() else 0,
    "checkpoints": len(list((state / "checkpoints").rglob("*.json"))) if (state / "checkpoints").exists() else 0,
}
print(json.dumps(checks, indent=2))
