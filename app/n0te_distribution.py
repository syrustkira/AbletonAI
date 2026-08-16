from __future__ import annotations
from dataclasses import asdict,dataclass,field
from enum import Enum
from pathlib import Path
import hashlib,json,shutil,tempfile,time
from typing import Any
from n0te_state import atomic_write_json
class Profile(str,Enum):STANDARD="STANDARD";FULL_OFFLINE="FULL_OFFLINE"
class InstallState(str,Enum):INSTALLED="INSTALLED";READY="READY";OPTIONAL_NOT_INSTALLED="OPTIONAL_NOT_INSTALLED";DEGRADED="DEGRADED";FAILED="FAILED";EXTERNAL_ACCEPTANCE_REQUIRED="EXTERNAL_ACCEPTANCE_REQUIRED"
@dataclass
class PayloadFile:source:str;destination:str;sha256:str
@dataclass
class DistributionComponent:
 id:str;version:str;platforms:list[str];architectures:list[str];files:list[PayloadFile];dependencies:list[str]=field(default_factory=list);optional:bool=False;restart_required:bool=False;in_use_restricted:bool=False;rollback_source:str="";preserve_user_data:bool=True;verification:str="sha256";redistribution_status:str="approved"
@dataclass(frozen=True)
class ThirdPartyComponent:name:str;version:str;license:str;source_project:str;redistribution_status:str;notice_location:str
def validate_third_party_inventory(items):
 for item in items:
  if item.redistribution_status not in {"approved","system_not_bundled"}:raise PermissionError(f"Unknown redistribution status: {item.name}")
  if item.redistribution_status=="approved" and (not item.license or not item.notice_location):raise ValueError(f"Missing license notice: {item.name}")
 return True
@dataclass(frozen=True)
class PrivateRuntimeManifest:version:str;platform:str;architecture:str;payload_path:str;sha256:str;redistribution_status:str
def validate_private_runtime(runtime:PrivateRuntimeManifest,root:Path):
 if runtime.redistribution_status!="approved":raise PermissionError("Private runtime redistribution is not approved")
 payload=Path(root)/runtime.payload_path
 if not payload.is_file():raise FileNotFoundError("Private runtime payload is required; offline builds never download it")
 if _hash(payload)!=runtime.sha256:raise ValueError("Private runtime hash mismatch")
 return True
class DistributionBuilder:
 EXCLUDED={".git","tests","__pycache__",".coverage"}
 SECRET_NAMES={"api_key","secrets.json","credentials.json"}
 def __init__(self,source:Path):self.source=Path(source)
 def stage(self,out:Path,components:list[DistributionComponent],profile:Profile):
  out=Path(out);payload=out/"payload";shutil.rmtree(out,ignore_errors=True);payload.mkdir(parents=True)
  for c in sorted(components,key=lambda x:x.id):
   if c.redistribution_status!="approved":raise PermissionError(f"Unknown redistribution status: {c.id}")
   for f in c.files:
    src=(self.source/f.source).resolve()
    if any(x in src.parts for x in self.EXCLUDED) or src.name in self.SECRET_NAMES:raise PermissionError(f"Excluded payload: {f.source}")
    if not src.is_file():raise FileNotFoundError(f.source)
    if _hash(src)!=f.sha256:raise ValueError(f"Hash mismatch: {f.source}")
    dst=payload/c.id/f.destination;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
  manifest={"schema":1,"profile":profile.value,"components":[_component_dict(c) for c in sorted(components,key=lambda x:x.id)],"native_build":{"DMG_BUILD":"EXTERNAL_ACCEPTANCE_PENDING","WINDOWS_EXE_BUILD":"EXTERNAL_ACCEPTANCE_PENDING","SIGNING":"EXTERNAL_ACCEPTANCE_PENDING","NOTARIZATION":"EXTERNAL_ACCEPTANCE_PENDING"}}
  atomic_write_json(out/"distribution.json",manifest);return manifest
class InstallTransaction:
 def __init__(self,staging:Path,destination:Path,state:Path):self.staging=Path(staging);self.destination=Path(destination);self.state=Path(state);self.receipt=self.state/"install_receipt.json"
 def install(self,component_ids:list[str],platform:str,arch:str):
  manifest=json.loads((self.staging/"distribution.json").read_text());items={x["id"]:x for x in manifest["components"]};selected=set()
  def add(i):
   if i not in items:raise LookupError(i)
   x=items[i]
   if platform not in x["platforms"] or arch not in x["architectures"]:raise ValueError(f"Incompatible {i}")
   for d in x["dependencies"]:add(d)
   selected.add(i)
  for i in component_ids:add(i)
  backup=Path(tempfile.mkdtemp(prefix="n0te-rollback-",dir=self.state));changed=[]
  try:
   for i in sorted(selected):
    for f in items[i]["files"]:
     src=self.staging/"payload"/i/f["destination"];dst=self.destination/f["destination"]
     if dst.exists():b=backup/f["destination"];b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,b)
     dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);changed.append(str(Path(f["destination"])))
     if _hash(dst)!=f["sha256"]:raise RuntimeError("post-install verification failed")
   receipt={"profile":manifest["profile"],"components":sorted(selected),"files":changed,"backup":str(backup),"installed_at":time.time(),"preserve_user_data":True};atomic_write_json(self.receipt,receipt);return receipt
  except Exception:
   for rel in changed:
    dst=self.destination/rel;b=backup/rel
    if b.exists():shutil.copy2(b,dst)
    else:dst.unlink(missing_ok=True)
   raise
 def verify(self):
  receipt=json.loads(self.receipt.read_text());manifest=json.loads((self.staging/"distribution.json").read_text());items={x["id"]:x for x in manifest["components"]};bad=[]
  for i in receipt["components"]:
   for f in items[i]["files"]:
    p=self.destination/f["destination"]
    if not p.is_file() or _hash(p)!=f["sha256"]:bad.append({"component":i,"file":f["destination"]})
  return bad
 def repair(self):
  bad=self.verify()
  for x in bad:
   manifest=json.loads((self.staging/"distribution.json").read_text());c=next(c for c in manifest["components"] if c["id"]==x["component"]);f=next(f for f in c["files"] if f["destination"]==x["file"]);dst=self.destination/f["destination"];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(self.staging/"payload"/c["id"]/f["destination"],dst)
  return {"repaired":bad,"remaining":self.verify(),"preserved_user_data":True}
 def uninstall(self,remove_user_data=False):
  receipt=json.loads(self.receipt.read_text());[ (self.destination/x).unlink(missing_ok=True) for x in receipt["files"] ];self.receipt.unlink(missing_ok=True);return {"user_data_removed":bool(remove_user_data),"user_data_preserved":not remove_user_data}
def _hash(path):
 h=hashlib.sha256();h.update(Path(path).read_bytes());return h.hexdigest()
def _component_dict(c):
 d=asdict(c);return d
