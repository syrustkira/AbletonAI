from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import hashlib,hmac,json,shutil,tempfile,time,zipfile
from typing import Protocol
from n0te_network import NetworkPolicy
from n0te_state import atomic_write_json

class UpdateState(str,Enum):
 IDLE="IDLE";CHECKING="CHECKING";UPDATE_AVAILABLE="UPDATE_AVAILABLE";DOWNLOADING="DOWNLOADING";STAGED="STAGED";READY_TO_INSTALL="READY_TO_INSTALL";INSTALLING="INSTALLING";VERIFYING="VERIFYING";UPDATED="UPDATED";PAUSED_BY_NETWORK_POLICY="PAUSED_BY_NETWORK_POLICY";PENDING_HOST_CLOSE="PENDING_HOST_CLOSE";PENDING_RESTART="PENDING_RESTART";FAILED="FAILED";ROLLING_BACK="ROLLING_BACK";ROLLED_BACK="ROLLED_BACK"
class UpdateChannel(str,Enum):STABLE="STABLE";BETA="BETA";DEVELOPER="DEVELOPER"
@dataclass
class UpdateSettings:
 automatic_checking:bool=True;automatic_safe_install:bool=True;channel:UpdateChannel=UpdateChannel.STABLE
 def select_channel(self,channel,explicit=False):
  channel=UpdateChannel(channel)
  if channel is not UpdateChannel.STABLE and not explicit:raise PermissionError("Beta and Developer channels require explicit opt-in")
  self.channel=channel
@dataclass
class UpdateComponent:
 component_id:str;version:str;platform:str;architecture:str;sha256:str;signature:str;payload:str;dependencies:list[str]=field(default_factory=list);required_core_version:str="";host_family:str="";supported_host_versions:list[str]=field(default_factory=list);restart_required:bool=False;host_close_required:bool=False;migration_version:str="";capabilities_fixed:list[str]=field(default_factory=list);capabilities_requiring_revalidation:list[str]=field(default_factory=list);capabilities_unchanged:list[str]=field(default_factory=list)
@dataclass
class ReleaseManifest:
 release_id:str;release_version:str;channel:UpdateChannel;published_at:str;release_notes:str;minimum_core_version:str;rollback_compatible:bool;components:list[UpdateComponent];signature:str="";signature_required:bool=True
class SignatureVerifier(Protocol):
 def verify(self,data:bytes,signature:str)->bool:...
class TestOnlyHMACVerifier:
 """Deterministic test fixture only; production release keys are externally provisioned."""
 def __init__(self,key:bytes):self.key=key
 def sign(self,data):return hmac.new(self.key,data,hashlib.sha256).hexdigest()
 def verify(self,data,signature):return hmac.compare_digest(self.sign(data),signature)
def manifest_bytes(manifest):
 value=asdict(manifest);value["channel"]=manifest.channel.value;value.pop("signature",None)
 return json.dumps(value,sort_keys=True,separators=(",",":")).encode()
class UpdateEngine:
 KNOWN_COMPONENTS={"CORE","STANDALONE","ARK","ABLETON_ADAPTER","LOGIC_ADAPTER","FL_STUDIO_ADAPTER","PRO_TOOLS_ADAPTER","VST3","AU","AAX","CLAP","LOCAL_AI","OFFLINE_KNOWLEDGE","CREATOR","OBS_ADAPTER","CAMERA_COMPONENTS"}
 def __init__(self,state_dir:Path,network_policy:NetworkPolicy,verifier:SignatureVerifier,platform:str,architecture:str,current:dict[str,str],settings=None,policies=None,song_id="",supported_migrations=None):
  self.state_dir=Path(state_dir);self.state_dir.mkdir(parents=True,exist_ok=True);self.policy=network_policy;self.verifier=verifier;self.platform=platform;self.architecture=architecture;self.current=dict(current);self.settings=settings or UpdateSettings();self.policies=dict(policies or {});self.song_id=song_id;self.supported_migrations=set(supported_migrations or []);self.state=UpdateState.IDLE;self.manifest=None;self.plan=[];self.last_check=0;self.stage_path=None
 def check(self,url,fetch):
  if not self.settings.automatic_checking:return {"state":self.state.value,"disabled":True}
  decision=self.policy.decide(url)
  if not decision.allowed:self.state=UpdateState.PAUSED_BY_NETWORK_POLICY;return {"state":self.state.value,"intentional":True,"reason":"Updates paused by NetworkPolicy."}
  self.state=UpdateState.CHECKING;manifest=fetch(url);self.validate_manifest(manifest);self.manifest=manifest;self.last_check=time.time();self.plan=self.build_plan(manifest);self.state=UpdateState.UPDATE_AVAILABLE if self.plan else UpdateState.IDLE;return self.status()
 def validate_manifest(self,manifest):
  if manifest.signature_required and (not manifest.signature or not self.verifier.verify(manifest_bytes(manifest),manifest.signature)):raise PermissionError("Invalid or missing release signature")
  if manifest.channel is not self.settings.channel:raise ValueError("Release channel does not match configured channel")
  if manifest.minimum_core_version and _version(self.current.get("CORE","0"))<_version(manifest.minimum_core_version):raise ValueError("Incompatible Core")
  for item in manifest.components:
   if item.component_id not in self.KNOWN_COMPONENTS:raise ValueError("Unknown component")
   if item.platform!=self.platform:raise ValueError("Wrong platform")
   if item.architecture!=self.architecture:raise ValueError("Wrong architecture")
   if item.required_core_version and _version(self.current.get("CORE","0"))<_version(item.required_core_version):raise ValueError("Incompatible Core")
   if item.migration_version and item.migration_version not in self.supported_migrations:raise ValueError("Unsupported migration")
  return True
 def build_plan(self,manifest):
  changed={x.component_id:x for x in manifest.components if self.current.get(x.component_id)!=x.version}
  def add_deps(item):
   for dep in item.dependencies:
    if dep in changed:add_deps(changed[dep])
    elif dep not in self.current:raise ValueError(f"Missing dependency: {dep}")
  for item in tuple(changed.values()):add_deps(item)
  return [changed[x] for x in sorted(changed)]
 def stage(self,payloads:dict[str,bytes]):
  if not self.manifest:raise RuntimeError("No verified release")
  stage=Path(tempfile.mkdtemp(prefix="n0te-update-",dir=self.state_dir));self.state=UpdateState.DOWNLOADING
  for item in self.plan:
   data=payloads.get(item.payload)
   if data is None or hashlib.sha256(data).hexdigest()!=item.sha256:raise ValueError(f"Hash mismatch: {item.component_id}")
   if item.signature and not self.verifier.verify(data,item.signature):raise PermissionError(f"Invalid payload signature: {item.component_id}")
   (stage/item.component_id).write_bytes(data)
  self.stage_path=stage;self.state=UpdateState.STAGED
  self.state=UpdateState.PENDING_HOST_CLOSE if any(x.host_close_required for x in self.plan) else UpdateState.READY_TO_INSTALL
  return {"state":self.state.value,"stage":str(stage),"components":[x.component_id for x in self.plan]}
 def install(self,hosts_open=False):
  if hosts_open and any(x.host_close_required for x in self.plan):self.state=UpdateState.PENDING_HOST_CLOSE;return self.status()
  installed=self.state_dir/"installed-components";backup=self.state_dir/"rollback-components";shutil.rmtree(backup,ignore_errors=True);backup.mkdir(parents=True)
  for item in self.plan:
   old=installed/item.component_id
   if old.is_file():shutil.copy2(old,backup/item.component_id)
  snapshot={"components":dict(self.current),"policies":dict(self.policies),"song_id":self.song_id};atomic_write_json(self.state_dir/"rollback.json",snapshot)
  self.state=UpdateState.INSTALLING
  try:
   installed.mkdir(parents=True,exist_ok=True)
   for item in self.plan:
    if not self.stage_path:raise RuntimeError("Verified stage required")
    source=self.stage_path/item.component_id;target=installed/item.component_id;temporary=target.with_suffix(".new");shutil.copy2(source,temporary);temporary.replace(target)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=item.sha256:raise RuntimeError("Installed payload verification failed")
    self.current[item.component_id]=item.version
   self.state=UpdateState.VERIFYING;atomic_write_json(self.state_dir/"update_receipt.json",{"release":self.manifest.release_id,"components":dict(self.current),"song_id":self.song_id,"creative_state_untouched":True})
   self.state=UpdateState.PENDING_RESTART if any(x.restart_required for x in self.plan) else UpdateState.UPDATED
   return self.status()
  except Exception:self.rollback();raise
 def rollback(self):
  self.state=UpdateState.ROLLING_BACK;data=json.loads((self.state_dir/"rollback.json").read_text());installed=self.state_dir/"installed-components";backup=self.state_dir/"rollback-components"
  for item in self.plan:
   target=installed/item.component_id;old=backup/item.component_id
   if old.is_file():shutil.copy2(old,target)
   else:target.unlink(missing_ok=True)
  self.current=data["components"];self.policies=data["policies"]
  if self.song_id!=data["song_id"]:raise RuntimeError("Rollback refused: Song identity changed")
  self.state=UpdateState.ROLLED_BACK;return self.status()
 def import_offline(self,package:Path):
  with zipfile.ZipFile(package) as archive:
   if any(Path(name).is_absolute() or ".." in Path(name).parts for name in archive.namelist()):raise ValueError("Unsafe update package")
   raw=json.loads(archive.read("release.json"));manifest=_manifest_from_dict(raw);self.validate_manifest(manifest);self.manifest=manifest;self.plan=self.build_plan(manifest)
   payloads={x.payload:archive.read("payloads/"+x.payload) for x in self.plan}
  return self.stage(payloads)
 def status(self):return {"state":self.state.value,"channel":self.settings.channel.value,"automatic_checking":self.settings.automatic_checking,"automatic_safe_install":self.settings.automatic_safe_install,"last_successful_check":self.last_check,"network_permission":self.policy.status(),"available_release":self.manifest.release_version if self.manifest else "","pending_components":[x.component_id for x in self.plan],"pending_host_close":self.state is UpdateState.PENDING_HOST_CLOSE,"pending_restart":self.state is UpdateState.PENDING_RESTART,"rollback_available":(self.state_dir/"rollback.json").exists(),"signature_status":"VERIFIED" if self.manifest else "NOT_CHECKED","song_id":self.song_id}
def _manifest_from_dict(raw):
 components=[UpdateComponent(**x) for x in raw["components"]];return ReleaseManifest(**{**raw,"channel":UpdateChannel(raw["channel"]),"components":components})
def _version(value):
 parts=[]
 for item in str(value).split("."):
  digits="".join(x for x in item if x.isdigit());parts.append(int(digits or 0))
 return tuple(parts)
