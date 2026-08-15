from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
class PanicOperation(str,Enum):
 RELEASE_GENERATED_NOTES="RELEASE_GENERATED_NOTES";SUSTAIN_OFF="SUSTAIN_OFF";ALL_NOTES_OFF="ALL_NOTES_OFF";ALL_SOUND_OFF="ALL_SOUND_OFF";STOP_N0TE_PERFORMANCE="STOP_N0TE_PERFORMANCE"
class HostPanicAdapter(Protocol):
 def execute_panic(self,operations:list[dict])->str:...
@dataclass(frozen=True)
class GeneratedNote:workspace:str;source:str;target:str;channel:int;pitch:int
class MusicalPanic:
 def __init__(self):self.notes:set[GeneratedNote]=set();self.sustain:set[tuple[str,str,str,int]]=set();self.recovery_required=False
 def note_on(self,n:GeneratedNote):self.notes.add(n)
 def note_off(self,n:GeneratedNote):self.notes.discard(n)
 def set_sustain(self,workspace,source,target,channel,on):
  key=(workspace,source,target,channel);self.sustain.add(key) if on else self.sustain.discard(key)
 def plan(self,workspace):
  notes=[n for n in self.notes if n.workspace==workspace];sustain=[x for x in self.sustain if x[0]==workspace]
  operations=[{"operation":PanicOperation.RELEASE_GENERATED_NOTES.value,"target":n.target,"channel":n.channel,"pitch":n.pitch} for n in sorted(notes,key=lambda x:(x.target,x.channel,x.pitch))]
  operations += [{"operation":PanicOperation.SUSTAIN_OFF.value,"target":x[2],"channel":x[3]} for x in sorted(sustain)]
  operations += [{"operation":PanicOperation.ALL_NOTES_OFF.value},{"operation":PanicOperation.ALL_SOUND_OFF.value},{"operation":PanicOperation.STOP_N0TE_PERFORMANCE.value}]
  return operations
 def execute(self,workspace,adapter:HostPanicAdapter):
  result=adapter.execute_panic(self.plan(workspace))
  if result=="CONFIRMED":
   self.notes={n for n in self.notes if n.workspace!=workspace};self.sustain={x for x in self.sustain if x[0]!=workspace};return True
  self.recovery_required=True;return False
