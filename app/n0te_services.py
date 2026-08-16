from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import threading
from typing import Any
from n0te_creator import ArtistMode,ArtistWorld,ArtistWorldStore,CreatorEngine,EditOperation,Recipe,Visibility
from n0te_media import MockSocialAdapter,PublicationEngine,PublicationRecord,StreamEngine,StreamScene
from n0te_setup import FirstRunService
class DawManagementService:
 """One application façade over the shared detector for setup/runtime/settings/diagnostics."""
 def __init__(self,discovery,setup_path):self.discovery=discovery;self.setup=FirstRunService(setup_path,discovery)
 def integrations(self,include_missing=True):return [x.status() for x in self.discovery.discover(include_missing=include_missing)]
 def first_run_status(self):return self.setup.status()
 def first_run_advance(self,data):return self.setup.advance(data)
class CreatorService:
 """Application orchestration; domain engines retain all authority rules."""
 def __init__(self,state:Path,safety,stream_backend):
  self.artist=ArtistWorldStore(state);self.creator=CreatorEngine(state,safety);self.stream=StreamEngine(stream_backend,safety);self.publications={};self.publisher=PublicationEngine(safety);self._lock=threading.RLock()
 def artist_read(self):
  with self._lock:return asdict(self.artist.load())
 def artist_update(self,data):
  with self._lock:return asdict(self.artist.save(ArtistWorld(**{k:data.get(k,{}) for k in ("identity","visual","sonic","public_voice","content")})))
 def artist_guidance(self,mode):
  with self._lock:return self.artist.guidance(ArtistMode(mode))
 def project_create(self,song_id,title):
  with self._lock:return asdict(self.creator.create(song_id,title))
 def project_read(self,id):
  with self._lock:
   p=self.creator.get(id)
   if not p:raise LookupError("Unknown content project")
   return asdict(p)
 def projects(self):
  with self._lock:return [asdict(x) for x in self.creator.list()]
 def recipe(self,id,kind,sections,marks,aspect="9:16",artist_mode="USE_ARTIST_WORLD"):
  with self._lock:
   p=self.creator.get(id)
   if not p:raise LookupError("Unknown content project")
   return self.creator.recipe(p,Recipe(kind),sections,marks,aspect=aspect,artist_mode=ArtistMode(artist_mode))
 def edit(self,id,index,operation,params):
  with self._lock:
   p=self.creator.get(id)
   if not p:raise LookupError("Unknown content project")
   self.creator.add_edit(p,int(index),EditOperation(operation),**(params or {}));return asdict(p)
 def visibility(self,id,value,authority,explicit):
  with self._lock:
   p=self.creator.get(id)
   if not p:raise LookupError("Unknown content project")
   return asdict(self.creator.set_visibility(p,Visibility(value),authority=authority,explicit=explicit))
 def stream_state(self):
  with self._lock:return asdict(self.stream.session)
 def stream_test(self,scene):
  with self._lock:return asdict(self.stream.test(StreamScene(scene)))
 def stream_live(self,scene,authority,explicit,reconnect=False):
  with self._lock:return asdict(self.stream.go_live(StreamScene(scene),authority=authority,explicit=explicit,reconnect=reconnect))
 def stream_stop(self):
  with self._lock:self.stream.enter_safe();return asdict(self.stream.session)
 def publication_prepare(self,project_id,destination):
  with self._lock:
   p=self.creator.get(project_id)
   if not p:raise LookupError("Unknown content project")
   r=PublicationRecord(project_id+":"+destination,project_id,p.revision,destination);self.publications[r.id]=r;return asdict(r)
 def publication_approve(self,id,authority,revision):
  with self._lock:
   r=self.publications[id];self.publisher.approve(r,authority=authority,revision=int(revision));return asdict(r)
 def publication_publish(self,id):
  with self._lock:
   r=self.publications[id];p=self.creator.get(r.project_id)
   if not p:raise LookupError("Unknown content project")
   return asdict(self.publisher.publish(r,MockSocialAdapter(),current_revision=p.revision))
