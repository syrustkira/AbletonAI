from __future__ import annotations
from dataclasses import dataclass,field
from enum import Enum
import hashlib,json,time,uuid
from typing import Any,Protocol
class CameraState(str,Enum):OFF="OFF";STARTING="STARTING";PREVIEW="PREVIEW";RECORDING="RECORDING";DEGRADED="DEGRADED";UNAVAILABLE="UNAVAILABLE"
class CameraSourceType(str,Enum):WEBCAM="WEBCAM";CAPTURE_CARD="CAPTURE_CARD";NETWORK_CAMERA="NETWORK_CAMERA";PHONE_CAMERA="PHONE_CAMERA";VIRTUAL_CAMERA="VIRTUAL_CAMERA";MOCK="MOCK"
@dataclass
class CameraSource:id:str;source_type:CameraSourceType;state:CameraState=CameraState.OFF;capabilities:set[str]=field(default_factory=set)
@dataclass(frozen=True)
class MotionEvent:kind:str;confidence:float;values:dict[str,float];timestamp:float
@dataclass(frozen=True)
class GestureMapping:gesture:str;target:str;minimum_confidence:float=.8;requires_confirmation:bool=True
class MockMotionBackend:
 def __init__(self,events=()):self.events=list(events)
 def poll(self):return self.events.pop(0) if self.events else None
class MotionMapper:
 SAFE_TARGETS={"MIDI_INTENT","OSC_INTENT","DAW_PARAMETER_INTENT","N0TE_MACRO","MARK","CAMERA_SWITCH","STREAM_SCENE_INTENT"}
 def map(self,event,mapping):
  if mapping.target not in self.SAFE_TARGETS:raise PermissionError("Gesture target is not authority-safe")
  if event.kind!=mapping.gesture or event.confidence<mapping.minimum_confidence:return None
  return {"target":mapping.target,"values":event.values,"requires_confirmation":mapping.requires_confirmation,"authority":"untrusted_motion"}
class StreamState(str,Enum):OFF="OFF";STARTING="STARTING";TESTING="TESTING";READY="READY";LIVE="LIVE";DEGRADED="DEGRADED";FAILED="FAILED";STOPPING="STOPPING"
class StreamScene(str,Enum):PRODUCING="PRODUCING";PERFORMANCE="PERFORMANCE";TALKING="TALKING";DAW_FULL="DAW_FULL";BREAK="BREAK"
class StreamBackend(Protocol):
 def test(self,scene:str)->bool:...
 def start(self,scene:str)->bool:...
 def stop(self)->bool:...
class MockStreamBackend:
 def __init__(self):self.live=False;self.calls=[]
 def test(self,scene):self.calls.append(("test",scene));return True
 def start(self,scene):self.calls.append(("start",scene));self.live=True;return True
 def stop(self):self.calls.append(("stop",));self.live=False;return True
@dataclass
class StreamSession:id:str;state:StreamState=StreamState.OFF;scene:StreamScene=StreamScene.PRODUCING;public_authorized:bool=False
class StreamEngine:
 def __init__(self,backend,safety):self.backend=backend;self.safety=safety;self.session=StreamSession(uuid.uuid4().hex)
 def test(self,scene):
  self.session.scene=scene;self.session.state=StreamState.TESTING
  try:ready=bool(self.backend.test(scene.value))
  except Exception:
   self.session.state=StreamState.FAILED;raise
  self.session.state=StreamState.READY if ready else StreamState.FAILED
  if not ready:raise RuntimeError("Stream backend test failed")
  return self.session
 def go_live(self,scene,*,authority="",explicit=False,reconnect=False):
  if reconnect or authority!="user" or not explicit:raise PermissionError("GO LIVE requires fresh explicit user authority")
  if self.safety.status().get("safe"):raise PermissionError("SAFE prevents GO LIVE")
  self.session.scene=scene;self.session.state=StreamState.STARTING;self.session.public_authorized=False
  try:started=bool(self.backend.start(scene.value))
  except Exception:
   self.session.state=StreamState.FAILED;raise
  if not started:
   self.session.state=StreamState.FAILED;raise RuntimeError("Stream backend failed to start")
  self.session.state=StreamState.LIVE;self.session.public_authorized=True;return self.session
 def enter_safe(self):
  if self.session.state is StreamState.LIVE:
   self.session.state=StreamState.STOPPING
   try:stopped=bool(self.backend.stop())
   except Exception:
    self.session.state=StreamState.FAILED;self.session.public_authorized=False;raise
   self.session.state=StreamState.OFF if stopped else StreamState.FAILED
  self.session.public_authorized=False
class PublicationState(str,Enum):DRAFT="DRAFT";READY_FOR_REVIEW="READY_FOR_REVIEW";APPROVED="APPROVED";PUBLISHING="PUBLISHING";PUBLISHED="PUBLISHED";FAILED="FAILED";CANCELLED="CANCELLED"
@dataclass
class PublicationRecord:id:str;project_id:str;revision:int;destination:str;state:PublicationState=PublicationState.DRAFT;approval:dict[str,Any]=field(default_factory=dict);receipt:dict[str,Any]=field(default_factory=dict)
class MockSocialAdapter:
 def publish(self,record):return {"external_id":"mock-"+record.id,"at":time.time()}
class PublicationEngine:
 def __init__(self,safety):self.safety=safety
 def content_hash(self,project_id,revision):return hashlib.sha256(f"{project_id}:{revision}".encode()).hexdigest()
 def approve(self,r,*,authority,revision):
  if authority!="user" or revision!=r.revision:raise PermissionError("Fresh user approval required")
  r.approval={"authority":"user","revision":revision,"hash":self.content_hash(r.project_id,revision),"destination":r.destination,"timestamp":time.time()};r.state=PublicationState.APPROVED
 def publish(self,r,adapter,*,current_revision,reconnect=False):
  if reconnect or self.safety.status().get("safe"):raise PermissionError("Publishing denied")
  if r.state is not PublicationState.APPROVED or current_revision!=r.approval.get("revision") or self.content_hash(r.project_id,current_revision)!=r.approval.get("hash"):raise PermissionError("Approval invalid after content change")
  r.state=PublicationState.PUBLISHING
  try:r.receipt=adapter.publish(r)
  except Exception:
   r.state=PublicationState.FAILED;raise
  r.state=PublicationState.PUBLISHED;return r
