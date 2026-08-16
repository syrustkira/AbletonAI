"""Durable plugin discovery evidence; native hosting remains a separate claim."""
from __future__ import annotations
from dataclasses import asdict,dataclass,fields
from pathlib import Path
from enum import Enum
import hashlib,json,shutil,subprocess,sys,time
from n0te_state import atomic_write_json


@dataclass(frozen=True)
class PluginInstallFingerprint:path:str;size:int;mtime_ns:int
@dataclass(frozen=True)
class PluginModuleIdentity:format:str;binary_hash:str;module_name:str
@dataclass(frozen=True)
class PluginClassIdentity:module_identity:str;class_id:str
@dataclass(frozen=True)
class PluginDescriptor:
 uid:str;name:str;format:str;path:str;version:str="UNKNOWN";vendor:str="UNKNOWN";hostability:str="NATIVE_HOST_REQUIRED";sha256:str="";install_fingerprint:str="";class_ids:tuple[str,...]=()
class PluginState(str,Enum):SCANNING="SCANNING";LOADING="LOADING";READY="READY";PROCESSING="PROCESSING";FAILED="FAILED";TIMEOUT="TIMEOUT";CRASHED="CRASHED";QUARANTINED="QUARANTINED"
class FailureKind(str,Enum):SCAN_FAILED="SCAN_FAILED";SCAN_TIMEOUT="SCAN_TIMEOUT";LOAD_FAILED="LOAD_FAILED";LOAD_CRASHED="LOAD_CRASHED";PROCESS_FAILED="PROCESS_FAILED";PROCESS_CRASHED="PROCESS_CRASHED";UI_FAILED="UI_FAILED"


class PluginScanner:
 EXT={'.vst3':'VST3','.component':'AU','.clap':'CLAP','.aaxplugin':'AAX'}
 @staticmethod
 def _hash(path):
  digest=hashlib.sha256()
  files=[path] if path.is_file() else sorted(item for item in path.rglob('*') if item.is_file())
  for item in files:
   digest.update(str(item.relative_to(path) if path.is_dir() else item.name).encode())
   with item.open('rb') as handle:
    for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
  return digest.hexdigest()
 def scan(self,roots):
  rows=[]
  for root in map(Path,roots):
   if not root.exists():continue
   candidates=[]
   for path in sorted(root.rglob('*')):
    if self.EXT.get(path.suffix.lower()) and not any(parent in candidates for parent in path.parents):candidates.append(path)
   for path in candidates:
    fmt=self.EXT[path.suffix.lower()];stat=path.stat();binary_hash=self._hash(path);module=PluginModuleIdentity(fmt,binary_hash,path.stem);install=PluginInstallFingerprint(str(path.resolve()),stat.st_size,stat.st_mtime_ns);module_id=hashlib.sha256(json.dumps(asdict(module),sort_keys=True).encode()).hexdigest();fingerprint=hashlib.sha256(json.dumps(asdict(install),sort_keys=True).encode()).hexdigest();rows.append(PluginDescriptor(module_id,path.stem,fmt,str(path),sha256=binary_hash,install_fingerprint=fingerprint))
  return rows


class PluginScanProcess:
 def scan(self,roots,timeout=10):
  module_dir=str(Path(__file__).resolve().parent);code=f'import json,sys;sys.path.insert(0,{module_dir!r});from n0te_plugins import PluginScanner;print(json.dumps([x.__dict__ for x in PluginScanner().scan(sys.argv[1:])]))'
  try:result=subprocess.run([sys.executable,'-I','-c',code,*map(str,roots)],capture_output=True,text=True,timeout=timeout,check=True)
  except subprocess.TimeoutExpired:return {'state':'TIMEOUT','failure_kind':FailureKind.SCAN_TIMEOUT.value,'plugins':[]}
  except Exception as error:return {'state':'FAILED','failure_kind':FailureKind.SCAN_FAILED.value,'plugins':[],'reason':type(error).__name__}
  return {'state':'READY','plugins':json.loads(result.stdout)}


@dataclass(frozen=True)
class SemanticMapping:
 plugin_uid:str;plugin_version:str;parameter_id:str;parameter_metadata:dict;semantic:str;evidence_source:str;verified_at:float;host_environment:str="";binary_hash:str="";verification_status:str="CANDIDATE";class_id:str=""


class PluginRegistry:
 SCHEMA=3
 def __init__(self,path):self.path=Path(path);self.plugins=[];self.quarantine={};self.mappings=[];self.recovery="";self.load()
 def load(self):
  if not self.path.exists():return self
  try:value=json.loads(self.path.read_text())
  except (OSError,json.JSONDecodeError):
   self.recovery="CORRUPT_STATE_IGNORED";backup=self.path.with_suffix(self.path.suffix+f'.corrupt-{int(time.time())}')
   try:shutil.copy2(self.path,backup)
   except OSError:pass
   return self
  if not isinstance(value,dict) or value.get('schema') not in {1,2,3}:self.recovery="UNSUPPORTED_SCHEMA_IGNORED";return self
  allowed={field.name for field in fields(SemanticMapping)}
  self.plugins=[row for row in value.get('plugins',[]) if isinstance(row,dict)];self.quarantine=value.get('quarantine',{}) if isinstance(value.get('quarantine',{}),dict) else {}
  for row in value.get('mappings',[]):
   if isinstance(row,dict):
    try:self.mappings.append(SemanticMapping(**{key:item for key,item in row.items() if key in allowed}))
    except TypeError:continue
  return self
 def save(self,plugins=None):
  if plugins is not None:self.plugins=[asdict(item) if hasattr(item,'__dataclass_fields__') else item for item in plugins]
  atomic_write_json(self.path,{'schema':self.SCHEMA,'plugins':self.plugins,'quarantine':self.quarantine,'mappings':[asdict(item) for item in self.mappings]})
 def _key(self,uid,version,binary_hash='',class_id=''):return ':'.join((uid,class_id or '-',version,binary_hash or '-'))
 def quarantine_plugin(self,uid,version,reason,binary_hash='',class_id='',failure_kind=FailureKind.PROCESS_FAILED):self.quarantine[self._key(uid,version,binary_hash,class_id)]={'reason':reason,'failure_kind':FailureKind(failure_kind).value,'at':time.time()};self.save()
 def reenable(self,uid,version,binary_hash='',class_id=''):self.quarantine.pop(self._key(uid,version,binary_hash,class_id),None);self.save()
 def add_mapping(self,mapping):self.mappings=[item for item in self.mappings if not (item.plugin_uid==mapping.plugin_uid and item.plugin_version==mapping.plugin_version and item.class_id==mapping.class_id and item.parameter_id==mapping.parameter_id)];self.mappings.append(mapping);self.save()
 def invalidate_changed_binary(self,uid,version,binary_hash,class_id=''):
  return [item.parameter_id for item in self.mappings if item.plugin_uid==uid and item.plugin_version==version and item.class_id==class_id and item.binary_hash and item.binary_hash!=binary_hash]


def mapping_valid_for(mapping,uid,version,binary_hash=None,class_id=None):return mapping.plugin_uid==uid and mapping.plugin_version==version and (binary_hash is None or mapping.binary_hash==binary_hash) and (class_id is None or mapping.class_id==class_id)
def candidate_mapping(plugin,parameter,class_id=''):
 title=str(parameter.get('title','')).lower();semantic='UNKNOWN';rules=((('gain','trim'),'gain'),(('threshold',),'threshold'),(('attack',),'attack_time'),(('release',),'release_time'),(('ratio',),'ratio'),(('mix','wet'),'mix'))
 for words,value in rules:
  if any(word in title for word in words):semantic=value;break
 return SemanticMapping(plugin.uid,plugin.version,str(parameter.get('id','')),dict(parameter),semantic,'parameter_metadata',time.time(),binary_hash=plugin.sha256,verification_status='CANDIDATE',class_id=class_id)
