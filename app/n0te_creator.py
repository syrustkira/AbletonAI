from __future__ import annotations
from dataclasses import asdict,dataclass,field
from enum import Enum
from pathlib import Path
import json,time,uuid
from typing import Any
from n0te_state import atomic_write_json
class ArtistMode(str,Enum):USE_ARTIST_WORLD="USE_ARTIST_WORLD";TRY_SOMETHING_DIFFERENT="TRY_SOMETHING_DIFFERENT";IGNORE_ARTIST_WORLD="IGNORE_ARTIST_WORLD"
@dataclass
class ArtistWorld:
 identity:dict[str,Any]=field(default_factory=dict);visual:dict[str,Any]=field(default_factory=dict);sonic:dict[str,Any]=field(default_factory=dict);public_voice:dict[str,Any]=field(default_factory=dict);content:dict[str,Any]=field(default_factory=dict);updated_at:float=0
class ArtistWorldStore:
 def __init__(self,state:Path):self.path=Path(state)/"artist_world.json"
 def save(self,w):w.updated_at=time.time();atomic_write_json(self.path,asdict(w));return w
 def load(self):
  try:return ArtistWorld(**json.loads(self.path.read_text()))
  except (OSError,ValueError,TypeError):return ArtistWorld()
 def guidance(self,mode:ArtistMode):return {"mode":mode.value,"guidance":asdict(self.load()) if mode is ArtistMode.USE_ARTIST_WORLD else {},"blocking":False}
class Visibility(str,Enum):PRIVATE="PRIVATE";COLLABORATORS="COLLABORATORS";CONTENT_DRAFT="CONTENT_DRAFT";PUBLIC="PUBLIC"
class Recipe(str,Enum):BEAT_BUILD="BEAT_BUILD";BEFORE_AFTER="BEFORE_AFTER";STUDIO_STORY="STUDIO_STORY";PERFORMANCE_CLIP="PERFORMANCE_CLIP";PRODUCTION_BREAKDOWN="PRODUCTION_BREAKDOWN"
class EditOperation(str,Enum):TRIM="TRIM";SPLIT="SPLIT";CROP="CROP";REFRAME="REFRAME";TEXT="TEXT";CAPTION="CAPTION";OVERLAY="OVERLAY";FADE_IN="FADE_IN";FADE_OUT="FADE_OUT";THUMBNAIL_MARKER="THUMBNAIL_MARKER";AUDIO_SYNC="AUDIO_SYNC";CAMERA_SWITCH="CAMERA_SWITCH"
@dataclass
class TimelineSegment:start:float;end:float;source:str;section:str="";operations:list[dict[str,Any]]=field(default_factory=list);provenance:str="song_timing"
@dataclass
class ContentProject:
 id:str;song_id:str;title:str;visibility:Visibility=Visibility.PRIVATE;revision:int=1;media:list[dict[str,Any]]=field(default_factory=list);timeline:list[TimelineSegment]=field(default_factory=list);publication_approved:bool=False
class CreatorEngine:
 ASPECTS={"9:16","16:9","1:1","4:5"}
 def __init__(self,state:Path,safety):self.root=Path(state)/"content_projects";self.safety=safety
 def create(self,song_id,title):
  p=ContentProject(uuid.uuid4().hex,song_id,title);self.save(p);return p
 def save(self,p):
  self.root.mkdir(parents=True,exist_ok=True);row=asdict(p);row["visibility"]=p.visibility.value;atomic_write_json(self.root/f"{p.id}.json",row)
 def get(self,id):
  try:r=json.loads((self.root/f"{id}.json").read_text());r["visibility"]=Visibility(r["visibility"]);r["timeline"]=[TimelineSegment(**x) for x in r.get("timeline",[])];return ContentProject(**r)
  except (OSError,ValueError,TypeError):return None
 def list(self):return [p for p in (self.get(x.stem) for x in sorted(self.root.glob("*.json"))) if p]
 def set_visibility(self,p,visibility,*,authority="",explicit=False):
  if visibility is Visibility.PUBLIC:
   if self.safety.status().get("safe"):raise PermissionError("SAFE prevents public action")
   if not explicit or authority!="user":raise PermissionError("PUBLIC requires explicit user approval")
   p.publication_approved=True
  elif p.visibility is Visibility.PUBLIC or p.publication_approved:
   p.publication_approved=False
  p.visibility=visibility;p.revision+=1;self.save(p);return p
 def recipe(self,p,kind:Recipe,sections,marks,*,aspect="9:16",artist_mode=ArtistMode.USE_ARTIST_WORLD):
  if aspect not in self.ASPECTS:raise ValueError("Unsupported aspect")
  chosen=sections[:2] or [{"name":"Song","start":0,"end":30}]
  p.timeline=[TimelineSegment(float(s.get("start",0)),float(s.get("end",30)),"selected_media",str(s.get("name","")),provenance="song_section") for s in chosen]
  p.revision+=1;p.publication_approved=False;self.save(p)
  return {"recipe":kind.value,"sections":chosen,"marks":[m.get("id") for m in marks],"media_requirements":["camera or selected media","clean song audio"],"timeline":[asdict(x) for x in p.timeline],"transitions":[x.end for x in p.timeline[:-1]],"caption_placeholder":"Describe the musical change.","aspect":aspect,"target_duration":sum(x.end-x.start for x in p.timeline),"artist_world_mode":artist_mode.value,"evidence":["song sections","explicit MARKs"],"ai_required":False,"revision":p.revision}
 def add_edit(self,p,index,operation:EditOperation,**params):
  if index<0 or index>=len(p.timeline):raise IndexError("Unknown segment")
  p.timeline[index].operations.append({"operation":operation.value,"params":params});p.revision+=1;p.publication_approved=False;self.save(p)
