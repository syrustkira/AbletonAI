from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from typing import Any
from n0te_creator import ArtistMode,ArtistWorld,ArtistWorldStore,CreatorEngine,EditOperation,Recipe,Visibility
from n0te_media import MockSocialAdapter,PublicationEngine,PublicationRecord,StreamEngine,StreamScene
class CreatorService:
 """Application orchestration; domain engines retain all authority rules."""
 def __init__(self,state:Path,safety,stream_backend):
  self.artist=ArtistWorldStore(state);self.creator=CreatorEngine(state,safety);self.stream=StreamEngine(stream_backend,safety);self.publications={};self.publisher=PublicationEngine(safety)
 def artist_read(self):return asdict(self.artist.load())
 def artist_update(self,data):return asdict(self.artist.save(ArtistWorld(**{k:data.get(k,{}) for k in ("identity","visual","sonic","public_voice","content")})))
 def artist_guidance(self,mode):return self.artist.guidance(ArtistMode(mode))
 def project_create(self,song_id,title):return asdict(self.creator.create(song_id,title))
 def project_read(self,id):
  p=self.creator.get(id)
  if not p:raise LookupError("Unknown content project")
  return asdict(p)
 def projects(self):return [asdict(x) for x in self.creator.list()]
 def recipe(self,id,kind,sections,marks,aspect="9:16",artist_mode="USE_ARTIST_WORLD"):
  p=self.creator.get(id)
  if not p:raise LookupError("Unknown content project")
  result=self.creator.recipe(p,Recipe(kind),sections,marks,aspect=aspect,artist_mode=ArtistMode(artist_mode));self.creator.save(p);return result
 def edit(self,id,index,operation,params):
  p=self.creator.get(id)
  if not p:raise LookupError("Unknown content project")
  self.creator.add_edit(p,int(index),EditOperation(operation),**(params or {}));return asdict(p)
 def visibility(self,id,value,authority,explicit):
  p=self.creator.get(id)
  if not p:raise LookupError("Unknown content project")
  return asdict(self.creator.set_visibility(p,Visibility(value),authority=authority,explicit=explicit))
 def stream_state(self):return asdict(self.stream.session)
 def stream_test(self,scene):return asdict(self.stream.test(StreamScene(scene)))
 def stream_live(self,scene,authority,explicit,reconnect=False):return asdict(self.stream.go_live(StreamScene(scene),authority=authority,explicit=explicit,reconnect=reconnect))
 def stream_stop(self):self.stream.enter_safe();return asdict(self.stream.session)
 def publication_prepare(self,project_id,destination):
  p=self.creator.get(project_id)
  if not p:raise LookupError("Unknown content project")
  r=PublicationRecord(project_id+":"+destination,project_id,p.revision,destination);self.publications[r.id]=r;return asdict(r)
 def publication_approve(self,id,authority,revision):r=self.publications[id];self.publisher.approve(r,authority=authority,revision=int(revision));return asdict(r)
 def publication_publish(self,id):
  r=self.publications[id];p=self.creator.get(r.project_id);return asdict(self.publisher.publish(r,MockSocialAdapter(),current_revision=p.revision))
