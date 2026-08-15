from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
from typing import Any,Protocol
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
@dataclass
class HostAdapterDescriptor:
 host:str;tier:IntegrationTier;target_tier:IntegrationTier=IntegrationTier.DEEP;available_capabilities:set[str]=field(default_factory=set);host_extensions:set[str]=field(default_factory=set);healthy:bool=True
 def effective_tier(self):
  if self.healthy:return self.tier
  if self.tier is IntegrationTier.DEEP:return IntegrationTier.ENHANCED if self.available_capabilities else IntegrationTier.GENERIC
  if self.tier is IntegrationTier.ENHANCED:return IntegrationTier.GENERIC
  return self.tier
 def status(self):return {"host":self.host,"tier":self.effective_tier().value,"configured_tier":self.tier.value,"target_tier":self.target_tier.value,"healthy":self.healthy,"capabilities":sorted(self.available_capabilities),"host_extensions":sorted(self.host_extensions)}
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
