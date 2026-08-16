from __future__ import annotations
from dataclasses import asdict,dataclass
from enum import Enum
from pathlib import Path
import json,time,threading,uuid
from typing import Any
from n0te_state import atomic_write_json
class FaultDomain(str,Enum):
 KERNEL="KERNEL";DAW="DAW";DAW_ADAPTER="DAW_ADAPTER";AI_PROVIDER="AI_PROVIDER";PLUGIN_HOST="PLUGIN_HOST";ARK="ARK";STORAGE_SYNC="STORAGE_SYNC";CAMERA="CAMERA";STREAM_BACKEND="STREAM_BACKEND";SOCIAL_ADAPTER="SOCIAL_ADAPTER";UNKNOWN="UNKNOWN"
@dataclass
class FaultRecord:
 id:str;component:str;domain:FaultDomain;signature:str;message:str;timestamp:float;transaction_state:str="KNOWN";optional:bool=True
class RecoveryEngine:
 def __init__(self,state:Path,threshold=3,max_faults=200):
  self.path=Path(state)/"recovery_state.json";self.threshold=threshold;self.max_faults=max_faults;self._lock=threading.RLock()
 def _load(self):
  try:v=json.loads(self.path.read_text());return v if isinstance(v,dict) else {}
  except (OSError,ValueError):return {"faults":[],"quarantine":{},"heartbeat":0}
 def heartbeat(self,context=None):
  with self._lock:
   s=self._load();s["heartbeat"]=time.time();s["context"]=context or {};atomic_write_json(self.path,s);return s
 def record(self,component,domain:FaultDomain,signature,message,*,optional=True,transaction_state="KNOWN"):
  with self._lock:
   s=self._load();fault=FaultRecord(uuid.uuid4().hex,component,domain,signature,message,time.time(),transaction_state,optional)
   rows=(s.get("faults") or [])+[asdict(fault)];rows[-1]["domain"]=domain.value;s["faults"]=rows[-self.max_faults:]
   repeats=sum(x.get("component")==component and x.get("signature")==signature for x in s["faults"])
   if optional and repeats>=self.threshold:s.setdefault("quarantine",{})[component]={"signature":signature,"at":time.time(),"reversible":True}
   if transaction_state=="UNKNOWN":s["recovery_required"]=True
   atomic_write_json(self.path,s);return {"fault":rows[-1],"circuit_open":component in s.get("quarantine",{}),"recovery_required":bool(s.get("recovery_required"))}
 def available(self,component):return component not in self._load().get("quarantine",{})
 def clear_quarantine(self,component,*,explicit=False):
  if not explicit:raise PermissionError("Quarantine release requires explicit confirmation")
  with self._lock:s=self._load();s.setdefault("quarantine",{}).pop(component,None);atomic_write_json(self.path,s)
 def crash_capsule(self):
  s=self._load();return {"schema_version":1,"heartbeat":s.get("heartbeat"),"context":s.get("context",{}),"recent_faults":s.get("faults",[])[-50:],"quarantine":s.get("quarantine",{}),"recovery_required":bool(s.get("recovery_required")),"automatic_creative_undo":False}
 def safe_start_plan(self):return {"start_core":True,"quarantined_optional_components":sorted(self._load().get("quarantine",{})),"retry_identical_failures":False}
