"""Concrete, non-terminating platform discovery and process observation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import configparser,os,platform,subprocess


class ProcessState(str,Enum):RUNNING="RUNNING";NOT_RUNNING="NOT_RUNNING";UNKNOWN="UNKNOWN"


@dataclass(frozen=True)
class Application:
 identity:str;name:str;version:str;executable:str;source:str;architecture:str="UNKNOWN"


class LinuxApplicationDiscovery:
 def __init__(self,roots=None):self.roots=[Path(x) for x in (roots or [Path.home()/".local/share/applications","/usr/local/share/applications","/usr/share/applications"])]
 def discover(self):
  applications=[]
  for root in self.roots:
   if not root.is_dir():continue
   for path in sorted(root.glob("*.desktop")):
    parser=configparser.ConfigParser(interpolation=None,strict=False)
    try:parser.read(path,encoding="utf-8");section=parser["Desktop Entry"]
    except Exception:continue
    if section.get("Type","Application")!="Application" or section.getboolean("NoDisplay",fallback=False):continue
    executable=section.get("Exec","").split()[0].replace("%u","").replace("%U","").replace("%f","").replace("%F","")
    applications.append(Application(path.stem,section.get("Name",path.stem),section.get("X-AppImage-Version",section.get("Version","UNKNOWN")),executable,str(path),platform.machine()))
  return applications


class LinuxProcessDetector:
 def __init__(self,proc_root="/proc"):self.proc_root=Path(proc_root)
 def state(self,names):
  try:
   wanted={x.lower() for x in names}
   for item in self.proc_root.iterdir():
    if not item.name.isdigit():continue
    try:
     comm=(item/"comm").read_text(errors="replace").strip().lower();cmd=Path((item/"cmdline").read_bytes().split(b"\0")[0].decode(errors="replace")).name.lower()
    except (OSError,IndexError):continue
    if comm in wanted or cmd in wanted:return ProcessState.RUNNING
   return ProcessState.NOT_RUNNING
  except OSError:return ProcessState.UNKNOWN


class WindowsRegistryDiscovery:
 """Parses registry records supplied by winreg or deterministic fixtures."""
 HOSTS={"Ableton":"ABLETON_LIVE","FL Studio":"FL_STUDIO","Avid Pro Tools":"PRO_TOOLS","Pro Tools":"PRO_TOOLS"}
 def parse(self,records):
  result=[]
  for record in records:
   display=record.get("DisplayName","");family=next((value for key,value in self.HOSTS.items() if key.lower() in display.lower()),None)
   if not family:continue
   path=record.get("InstallLocation") or record.get("DisplayIcon","").split(",")[0]
   identity=f'{family}:{record.get("DisplayVersion","UNKNOWN")}:{path}'
   result.append(Application(identity,display,record.get("DisplayVersion","UNKNOWN"),path,record.get("RegistryKey","UNKNOWN"),record.get("Architecture","UNKNOWN")))
  return result
 def discover(self):
  if os.name!="nt":return []
  try:
   import winreg
   records=[]
   for view,arch in ((winreg.KEY_WOW64_64KEY,"x86_64"),(winreg.KEY_WOW64_32KEY,"x86")):
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
     try:key=winreg.OpenKey(hive,r"Software\Microsoft\Windows\CurrentVersion\Uninstall",0,winreg.KEY_READ|view)
     except OSError:continue
     for index in range(winreg.QueryInfoKey(key)[0]):
      try:
       name=winreg.EnumKey(key,index);sub=winreg.OpenKey(key,name);record={"RegistryKey":name,"Architecture":arch}
       for field in ("DisplayName","DisplayVersion","InstallLocation","DisplayIcon"):
        try:record[field]=winreg.QueryValueEx(sub,field)[0]
        except OSError:pass
       records.append(record)
      except OSError:continue
   return self.parse(records)
  except OSError:return []


class WindowsProcessDetector:
 def state(self,names):
  if os.name!="nt":return ProcessState.UNKNOWN
  try:
   output=subprocess.run(["tasklist","/FO","CSV","/NH"],capture_output=True,text=True,timeout=5,check=True).stdout.lower()
   return ProcessState.RUNNING if any(f'"{name.lower()}"' in output for name in names) else ProcessState.NOT_RUNNING
  except (OSError,subprocess.SubprocessError):return ProcessState.UNKNOWN
