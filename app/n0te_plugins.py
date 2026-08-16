from __future__ import annotations
from dataclasses import asdict,dataclass,field
from pathlib import Path
import hashlib,json,subprocess,sys,time
from n0te_state import atomic_write_json
@dataclass(frozen=True)
class PluginDescriptor:uid:str;name:str;format:str;path:str;version:str="UNKNOWN";vendor:str="UNKNOWN";hostability:str="NATIVE_HOST_REQUIRED";sha256:str=""
class PluginScanner:
 EXT={'.vst3':'VST3','.component':'AU','.clap':'CLAP','.aaxplugin':'AAX'}
 @staticmethod
 def _file_hash(path):
  if not path.is_file():return ""
  digest=hashlib.sha256()
  with path.open("rb") as handle:
   for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
  return digest.hexdigest()
 def scan(self,roots):
  rows=[]
  for root in map(Path,roots):
   if not root.exists():continue
   for p in sorted(root.rglob('*')):
    fmt=self.EXT.get(p.suffix.lower())
    if fmt:
     stat=p.stat();uid=hashlib.sha256(f'{p.resolve()}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest();rows.append(PluginDescriptor(uid,p.stem,fmt,str(p),sha256=self._file_hash(p)))
  return rows
class PluginScanProcess:
 def scan(self,roots,timeout=10):
  module_dir=str(Path(__file__).resolve().parent)
  code=f'import json,sys;sys.path.insert(0,{module_dir!r});from n0te_plugins import PluginScanner;print(json.dumps([x.__dict__ for x in PluginScanner().scan(sys.argv[1:])]))'
  try:r=subprocess.run([sys.executable,'-I','-c',code,*map(str,roots)],capture_output=True,text=True,timeout=timeout,check=True)
  except subprocess.TimeoutExpired:return {'state':'TIMEOUT','plugins':[]}
  except Exception as e:return {'state':'FAILED','plugins':[],'reason':type(e).__name__}
  return {'state':'READY','plugins':json.loads(r.stdout)}
class PluginRegistry:
 def __init__(self,path):self.path=Path(path);self.quarantine={}
 def save(self,plugins):atomic_write_json(self.path,{'schema':1,'plugins':[asdict(x) if hasattr(x,'__dataclass_fields__') else x for x in plugins],'quarantine':self.quarantine})
 def quarantine_plugin(self,uid,version,reason):self.quarantine[f'{uid}:{version}']={'reason':reason,'at':time.time()}
 def reenable(self,uid,version):self.quarantine.pop(f'{uid}:{version}',None)
@dataclass(frozen=True)
class SemanticMapping:plugin_uid:str;plugin_version:str;parameter_id:str;parameter_metadata:dict;semantic:str;evidence_source:str;verified_at:float;host_environment:str=""
def mapping_valid_for(mapping,uid,version):return mapping.plugin_uid==uid and mapping.plugin_version==version
