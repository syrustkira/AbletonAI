from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import plistlib,subprocess
from n0te_daw_discovery import HostFamily
BUNDLE_FAMILIES={"com.apple.logic10":HostFamily.LOGIC_PRO,"com.image-line.flstudio":HostFamily.FL_STUDIO,"com.avid.protools":HostFamily.PRO_TOOLS}
class HostRunState(str,Enum):RUNNING="RUNNING";NOT_RUNNING="NOT_RUNNING";UNKNOWN="UNKNOWN"
@dataclass(frozen=True)
class MacApplicationMetadata:path:Path;bundle_id:str;name:str;version:str;architecture:str="UNKNOWN"
class MacOSApplicationDiscovery:
 def __init__(self,roots=None):self.roots=tuple(Path(x) for x in (roots or (Path('/Applications'),Path.home()/'Applications')))
 def applications(self):
  rows=[]
  for root in self.roots:
   if not root.is_dir():continue
   for app in sorted(root.glob('*.app')):
    plist=app/'Contents/Info.plist'
    try:data=plistlib.loads(plist.read_bytes())
    except (OSError,plistlib.InvalidFileException):continue
    bid=str(data.get('CFBundleIdentifier') or '').lower();family=self.family(bid)
    if family:rows.append((family,MacApplicationMetadata(app,bid,str(data.get('CFBundleDisplayName') or data.get('CFBundleName') or app.stem),str(data.get('CFBundleShortVersionString') or data.get('CFBundleVersion') or 'UNKNOWN'))))
  return rows
 @staticmethod
 def family(bundle_id):
  if bundle_id.startswith('com.ableton.live'):return HostFamily.ABLETON_LIVE
  return BUNDLE_FAMILIES.get(bundle_id)
class MacOSHostProcessDetector:
 def __init__(self,runner=None):self.runner=runner or self._run
 def _run(self):return subprocess.run(['/bin/ps','-axo','command='],capture_output=True,text=True,timeout=3,check=True).stdout
 def state(self,application:MacApplicationMetadata):
  try:commands=self.runner()
  except Exception:return HostRunState.UNKNOWN
  marker=str(application.path/'Contents/MacOS/')
  return HostRunState.RUNNING if any(marker in line for line in commands.splitlines()) else HostRunState.NOT_RUNNING
