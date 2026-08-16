"""Platform-owned mutable paths; application resources are always read-only."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os, platform, shutil

@dataclass(frozen=True)
class ProductPaths:
 data:Path;logs:Path;cache:Path;recovery:Path;updates:Path;rollback:Path;temporary:Path
 def ensure(self):
  for path in (self.data,self.logs,self.cache,self.recovery,self.updates,self.rollback,self.temporary):path.mkdir(parents=True,exist_ok=True)
  return self

def product_paths(home:Path|None=None,system:str|None=None,environment:dict|None=None):
 home=Path(home or Path.home());system=(system or platform.system()).lower()
 environment=environment or os.environ
 if system in {"darwin","macos","mac"}:
  support=home/"Library/Application Support/N0TE";cache=home/"Library/Caches/N0TE";logs=home/"Library/Logs/N0TE"
 elif system=="windows":
  support=Path(environment.get("APPDATA",home/"AppData/Roaming"))/"N0TE";local=Path(environment.get("LOCALAPPDATA",home/"AppData/Local"))/"N0TE";cache=local/"Cache";logs=local/"Logs"
 elif system=="linux":
  support=Path(environment.get("XDG_DATA_HOME",home/".local/share"))/"n0te";cache=Path(environment.get("XDG_CACHE_HOME",home/".cache"))/"n0te";state=Path(environment.get("XDG_STATE_HOME",home/".local/state"))/"n0te";logs=state/"logs"
 else:
  support=home/".n0te-ableton-ai";cache=support/"cache";logs=support/"logs"
 return ProductPaths(support,logs,cache,support/"Recovery",support/"Updates",support/"Rollback",cache/"Temporary")

def migrate_legacy_macos(paths:ProductPaths,home:Path|None=None):
 """Non-destructive one-time copy; never deletes the legacy state."""
 legacy=Path(home or Path.home())/".n0te-ableton-ai"
 if paths.data.exists() or not legacy.is_dir():return False
 paths.data.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(legacy,paths.data);return True
