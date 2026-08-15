from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from typing import Any,Protocol
from n0te_capabilities import ComponentState
class AudioKind(str,Enum):DAW_TAP="DAW_TAP";SYSTEM_TAP="SYSTEM_TAP";PROCESS_TAP="PROCESS_TAP";MIC="MIC";AUDIO_DEVICE="AUDIO_DEVICE";STANDALONE_HOST="STANDALONE_HOST";LOCAL_RECORDER="LOCAL_RECORDER";ANALYSIS="ANALYSIS";STREAM="STREAM";REMOTE="REMOTE"
@dataclass(frozen=True)
class AudioFormat:sample_rate:int;channels:int;sample_type:str="float32"
@dataclass
class AudioNode:id:str;kind:AudioKind;direction:str;format:AudioFormat;clock_domain:str;state:str="CONNECTED"
@dataclass
class AudioRoute:id:str;source:str;sink:str;realtime:bool=True;queue_capacity:int=256;enabled:bool=True;state:str="READY"
class AudioGraph:
 def __init__(self):self.nodes={};self.routes={}
 def add_node(self,n):self.nodes[n.id]=n
 def add_route(self,r):
  if r.source not in self.nodes or r.sink not in self.nodes:raise ValueError("Unknown audio node")
  a,b=self.nodes[r.source],self.nodes[r.sink]
  if a.direction not in {"SOURCE","BOTH"} or b.direction not in {"SINK","BOTH"}:raise ValueError("Invalid direction")
  if a.format!=b.format:raise ValueError("Format conversion must be explicit")
  if r.queue_capacity<1 or r.queue_capacity>8192:raise ValueError("Queue must be bounded")
  self.routes[r.id]=r
 def realtime_contract(self,rid):
  if rid not in self.routes:raise LookupError(rid)
  return {"no_ai":True,"no_db":True,"no_network":True,"no_sync":True,"no_blocking_logging":True,"bounded_queue":True}
 def reconnect_plan(self):return [{"node":n.id,"action":"RECONNECT"} for n in self.nodes.values() if n.state in {"DISCONNECTED","DEGRADED"}]
@dataclass(frozen=True)
class ProtocolVersion:major:int;minor:int
@dataclass
class PluginHandshake:protocol:ProtocolVersion;features:set[str];song_id:str;workspace_id:str
class CoreConnectionState(str,Enum):DISCONNECTED="DISCONNECTED";CONNECTING="CONNECTING";NEGOTIATING="NEGOTIATING";READY="READY";DEGRADED="DEGRADED";INCOMPATIBLE="INCOMPATIBLE";RECOVERING="RECOVERING"
class PluginSession:
 def __init__(self,core_version,features):self.core_version=core_version;self.features=set(features);self.state=CoreConnectionState.DISCONNECTED;self.song_id="";self.workspace_id=""
 def negotiate(self,h):
  self.state=CoreConnectionState.NEGOTIATING
  if h.protocol.major!=self.core_version.major:self.state=CoreConnectionState.INCOMPATIBLE;return set()
  self.song_id=h.song_id;self.workspace_id=h.workspace_id;self.state=CoreConnectionState.READY;return self.features & h.features
 def reconnect(self,h):
  old=(self.song_id,self.workspace_id);features=self.negotiate(h)
  if old!=("","") and old!=(self.song_id,self.workspace_id):raise PermissionError("Reconnect cannot change Song/workspace binding")
  return features
class IntegrationTier(str,Enum):DETECTED_UNSUPPORTED="DETECTED_UNSUPPORTED";GENERIC="GENERIC";ENHANCED="ENHANCED";DEEP="DEEP"
class CompatibilityState(str,Enum):
 VERIFIED="VERIFIED";ASSUMED_COMPATIBLE="ASSUMED_COMPATIBLE";NEEDS_REVALIDATION="NEEDS_REVALIDATION";KNOWN_INCOMPATIBLE="KNOWN_INCOMPATIBLE";UNAVAILABLE="UNAVAILABLE"
@dataclass
class HostCapabilityDescriptor:
 capability_id:str;supported:bool;integration_depth:IntegrationTier;runtime_state:ComponentState;implementation_id:str;evidence:str="UNKNOWN";reason:str="";last_verified:float=0;fallback_candidates:list[str]=field(default_factory=list);authority_requirements:set[str]=field(default_factory=set);host_extensions:dict[str,Any]=field(default_factory=dict);adapter_version:str="";host_family:str="";host_version:str="";platform:str="";architecture:str="";protocol_version:str="";compatibility:CompatibilityState=CompatibilityState.VERIFIED
 def usable(self):return self.supported and self.runtime_state in {ComponentState.READY,ComponentState.BUSY} and self.compatibility in {CompatibilityState.VERIFIED,CompatibilityState.ASSUMED_COMPATIBLE}
@dataclass
class HostAdapterDescriptor:
 host:str;implementation_maturity:IntegrationTier;target_maturity:IntegrationTier=IntegrationTier.DEEP;capabilities:dict[str,HostCapabilityDescriptor]=field(default_factory=dict);host_extensions:set[str]=field(default_factory=set);adapter_state:ComponentState=ComponentState.READY;song_id:str="";workspace_id:str=""
 @property
 def overall_health(self):
  if self.adapter_state is ComponentState.UNAVAILABLE:return ComponentState.UNAVAILABLE
  useful=[x for x in self.capabilities.values() if x.usable()]
  if not useful:return ComponentState.UNAVAILABLE if self.capabilities else self.adapter_state
  return ComponentState.DEGRADED if any(x.runtime_state in {ComponentState.DEGRADED,ComponentState.UNAVAILABLE,ComponentState.RECOVERING} for x in self.capabilities.values()) else self.adapter_state
 def resolve(self,capability_id):
  item=self.capabilities.get(capability_id);return item if item and item.usable() else None
 def mark_state(self,capability_id,state,reason=""):
  item=self.capabilities[capability_id];item.runtime_state=state;item.reason=reason
 def status(self):return {"host":self.host,"implementation_maturity":self.implementation_maturity.value,"target_maturity":self.target_maturity.value,"overall_health":self.overall_health.value,"adapter_state":self.adapter_state.value,"summary":f"{self.host} integration is {self.implementation_maturity.value} with {sum(not x.usable() for x in self.capabilities.values())} degraded capabilities.","song_id":self.song_id,"workspace_id":self.workspace_id,"capabilities":{k:{"depth":v.integration_depth.value,"state":v.runtime_state.value,"compatibility":v.compatibility.value,"adapter_version":v.adapter_version,"host_version":v.host_version,"evidence":v.evidence,"last_verified":v.last_verified,"supported":v.supported,"reason":v.reason} for k,v in sorted(self.capabilities.items())},"host_extensions":sorted(self.host_extensions)}

@dataclass(frozen=True)
class CapabilityUpdate:
 adapter_version:str;fixes:set[str]=field(default_factory=set);needs_revalidation:set[str]=field(default_factory=set);unchanged:set[str]=field(default_factory=set)

class HostCompatibilityEngine:
 """Applies host/adapter compatibility evidence to the smallest affected path."""
 def host_updated(self,adapter:HostAdapterDescriptor,host_version:str,states:dict[str,CompatibilityState],reason="Host version changed"):
  for capability_id,state in states.items():
   item=adapter.capabilities.get(capability_id)
   if not item:continue
   item.host_version=host_version;item.compatibility=state;item.reason=reason
   if state is CompatibilityState.NEEDS_REVALIDATION:item.runtime_state=ComponentState.RECOVERING
   elif state in {CompatibilityState.KNOWN_INCOMPATIBLE,CompatibilityState.UNAVAILABLE}:item.runtime_state=ComponentState.UNAVAILABLE
  return adapter.status()
 def stage_adapter_update(self,adapter:HostAdapterDescriptor,update:CapabilityUpdate):
  affected=update.fixes|update.needs_revalidation
  for capability_id in affected:
   item=adapter.capabilities.get(capability_id)
   if item:
    item.adapter_version=update.adapter_version;item.compatibility=CompatibilityState.NEEDS_REVALIDATION;item.runtime_state=ComponentState.RECOVERING;item.reason="Capability verification required after adapter update"
  return {"adapter_version":update.adapter_version,"affected":sorted(affected),"unchanged":sorted(update.unchanged),"song_id":adapter.song_id}
 def verify(self,adapter:HostAdapterDescriptor,capability_id:str,passed:bool,evidence:str,last_verified:float):
  item=adapter.capabilities[capability_id];item.evidence=evidence;item.last_verified=last_verified
  item.compatibility=CompatibilityState.VERIFIED if passed else CompatibilityState.KNOWN_INCOMPATIBLE
  item.runtime_state=ComponentState.READY if passed else ComponentState.UNAVAILABLE
  item.reason="" if passed else "Capability verification failed"

class CapabilityCircuitBreaker:
 def __init__(self,threshold=3):self.threshold=threshold;self.failures={}
 def failure(self,adapter:HostAdapterDescriptor,capability_id:str,reason:str):
  key=(adapter.host,capability_id);self.failures[key]=self.failures.get(key,0)+1
  if self.failures[key]>=self.threshold:adapter.mark_state(capability_id,ComponentState.UNAVAILABLE,"Circuit open: "+reason)
  return self.failures[key]>=self.threshold
 def recover(self,adapter:HostAdapterDescriptor,capability_id:str):
  self.failures.pop((adapter.host,capability_id),None);adapter.mark_state(capability_id,ComponentState.RECOVERING,"Capability verification pending")

_DEPTH_RANK={tier:index for index,tier in enumerate(IntegrationTier)}

def resolve_job_capabilities(adapters:list[HostAdapterDescriptor],required:list[str]):
 """Resolve each job requirement independently; aggregate adapter health is not a gate."""
 steps=[]
 for capability_id in required:
  candidates=[]
  failed=[]
  for adapter in adapters:
   descriptor=adapter.capabilities.get(capability_id)
   if descriptor and descriptor.usable() and adapter.adapter_state not in {ComponentState.OFF,ComponentState.UNAVAILABLE}:
    candidates.append((_DEPTH_RANK[descriptor.integration_depth],descriptor.last_verified,adapter.host,descriptor))
   elif descriptor:
    failed.append(descriptor)
  if candidates:
   _,_,host,item=max(candidates,key=lambda value:(value[0],value[1],value[2]))
   steps.append({"capability":capability_id,"method":"AUTOMATIC","implementation":item.implementation_id,"host":host,"depth":item.integration_depth.value})
  else:
   fallback=[]
   for item in failed:
    fallback.extend(candidate for candidate in item.fallback_candidates if candidate not in fallback)
   steps.append({"capability":capability_id,"method":"GUIDED_MANUAL","fallback_candidates":fallback,"reason":failed[0].reason if failed else "unsupported"})
 return steps

def plan_job_capabilities(adapter:HostAdapterDescriptor,required:list[str]):
 return resolve_job_capabilities([adapter],required)
class DAWAdapter(Protocol):
 tier:IntegrationTier
 def host_identity(self)->dict:...
 def workspace_identity(self)->dict:...
 def transport_read(self)->dict:...
 def selection_read(self)->dict:...
 def tracks_read(self)->list:...
 def devices_read(self)->list:...
 def clips_read(self)->list:...
 def midi_read(self)->dict:...
 def routing_read(self)->dict:...
 def dirty_state(self)->bool:...
 def validate_action(self,action)->tuple[bool,str]:...
 def execute_action(self,action,authorization)->dict:...
 def observe_action(self,action)->dict:...
def execute_authorized(adapter,action,gate1_authorization):
 if not gate1_authorization or not gate1_authorization.get("approved") or not gate1_authorization.get("revalidated"):raise PermissionError("Gate 1 authorization required")
 ok,reason=adapter.validate_action(action)
 if not ok:raise ValueError(reason)
 return adapter.execute_action(action,gate1_authorization)
