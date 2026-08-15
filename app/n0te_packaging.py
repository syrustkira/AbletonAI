from dataclasses import dataclass,field
from enum import Enum
class Component(str,Enum):CORE="CORE";STANDALONE="STANDALONE";ARK="ARK";ABLETON_ADAPTER="ABLETON_ADAPTER";VST3="VST3";AU="AU";AAX="AAX";CLAP="CLAP";LOCAL_AI="LOCAL_AI";OFFLINE_KNOWLEDGE="OFFLINE_KNOWLEDGE";CREATOR="CREATOR";OBS_ADAPTER="OBS_ADAPTER";CAMERA_COMPONENTS="CAMERA_COMPONENTS"
@dataclass
class ComponentManifest:id:Component;version:str;platforms:set[str];architectures:set[str];dependencies:set[Component]=field(default_factory=set);optional_dependencies:set[Component]=field(default_factory=set);files:dict[str,str]=field(default_factory=dict);restart_required:bool=False;in_use:bool=False;rollback_source:str="";preserve_user_data:bool=True
class PackagingPlanner:
 def __init__(self,manifests):self.items={m.id:m for m in manifests}
 def install(self,selected,platform,arch):
  resolved=set()
  def add(c):
   m=self.items[c]
   if platform not in m.platforms or arch not in m.architectures:raise ValueError(f"{c.value} incompatible")
   for d in m.dependencies:add(d)
   resolved.add(c)
  for c in selected:add(c)
  return {"operation":"INSTALL","components":[x.value for x in sorted(resolved,key=lambda x:x.value)],"preserve_user_data":all(self.items[x].preserve_user_data for x in resolved)}
 def update(self,selected):
  blocked=[x.value for x in selected if self.items[x].in_use]
  if blocked:raise RuntimeError("Loaded components cannot be overwritten: "+", ".join(blocked))
  missing=[x.value for x in selected if not self.items[x].rollback_source]
  if missing:raise RuntimeError("Rollback source required: "+", ".join(missing))
  return {"operation":"UPDATE","components":[x.value for x in selected],"rollback":True}
 def uninstall(self,selected):return {"operation":"UNINSTALL","components":[x.value for x in selected],"preserve_user_data":True}
