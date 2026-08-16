"""Supported consumer entrypoint executed only by the bundled private runtime."""
from __future__ import annotations
import json,os,sys,webbrowser
from pathlib import Path
from n0te_app_health import startup_health
from n0te_instance import AlreadyRunningError,SingleInstance
from n0te_paths import migrate_legacy_macos,product_paths

def main():
 paths=product_paths().ensure();migrate_legacy_macos(paths)
 os.environ.setdefault("N0TE_STATE_DIR",str(paths.data));os.environ.setdefault("N0TE_LOG_DIR",str(paths.logs));os.environ.setdefault("N0TE_CACHE_DIR",str(paths.cache))
 lock=SingleInstance(paths.data/"n0te.lock")
 bundle=os.environ.get("N0TE_APP_BUNDLE")
 if bundle:
  health=startup_health(Path(bundle),paths);(paths.recovery/"startup-health.json").write_text(json.dumps(health,indent=2)+"\n")
  if not health["healthy"]:raise RuntimeError("N0TE application bundle failed required startup health checks")
 try:lock.acquire()
 except AlreadyRunningError:
  if lock.existing_server():webbrowser.open("http://127.0.0.1:8766");return 0
  raise
 try:
  import n0te_server
  return n0te_server.main()
 finally:lock.release()
if __name__=="__main__":raise SystemExit(main())
