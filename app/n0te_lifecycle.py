from __future__ import annotations
from dataclasses import asdict,dataclass,field
from enum import Enum
from pathlib import Path
import json,time,uuid,threading
from typing import Any
from n0te_state import atomic_write_json
class VersionState(str,Enum):WORKING="WORKING";FINAL_FOR_RECORDING="FINAL_FOR_RECORDING";FINAL_FOR_MIX="FINAL_FOR_MIX";APPROVED_FOR_MASTERING="APPROVED_FOR_MASTERING";RELEASE_LOCKED="RELEASE_LOCKED"
@dataclass(frozen=True)
class SongVersion:
 id:str;song_id:str;state:VersionState;created_at:float;reason:str;parent_id:str="";workspace_state:dict[str,Any]=field(default_factory=dict);assets:tuple[str,...]=();decisions:tuple[str,...]=();events:tuple[str,...]=();checkpoint:str=""
class VersionStore:
 def __init__(self,state:Path):self.root=Path(state)/"versions";self._lock=threading.RLock()
 def create(self,song_id,state=VersionState.WORKING,reason="",parent_id="",**links):
  if state is VersionState.RELEASE_LOCKED and not reason:raise ValueError("Locking a release requires a reason")
  v=SongVersion(uuid.uuid4().hex,song_id,state,time.time(),reason,parent_id,**links)
  self.root.mkdir(parents=True,exist_ok=True);row=asdict(v);row["state"]=state.value;atomic_write_json(self.root/f"{v.id}.json",row);return v
 def reopen(self,version_id,reason):
  if not reason:raise ValueError("Reopening requires explicit intent/reason")
  v=self.get(version_id)
  if not v:raise LookupError("Unknown version")
  return self.create(v.song_id,VersionState.WORKING,reason,v.id)
 def get(self,id):
  try:r=json.loads((self.root/f"{id}.json").read_text());r["state"]=VersionState(r["state"]);r["assets"]=tuple(r.get("assets",()));r["decisions"]=tuple(r.get("decisions",()));r["events"]=tuple(r.get("events",()));return SongVersion(**r)
  except (OSError,ValueError):return None
class SyncState(str,Enum):LOCAL_ONLY="LOCAL_ONLY";QUEUED="QUEUED";SYNCING="SYNCING";SYNCED="SYNCED";CONFLICT="CONFLICT";REMOTE_ONLY="REMOTE_ONLY";ARCHIVED="ARCHIVED"
@dataclass
class SyncIntent:id:str;record_id:str;revision:str;parent_revision:str="";state:SyncState=SyncState.LOCAL_ONLY;private_vault:bool=False;explicit_approval:bool=False
class SyncOutbox:
 def __init__(self,state:Path):self.path=Path(state)/"sync_outbox.json";self._lock=threading.RLock()
 def _load(self):
  try:v=json.loads(self.path.read_text());return v if isinstance(v,list) else []
  except (OSError,ValueError):return []
 def queue(self,record_id,revision,parent_revision="",*,private_vault=False):
  if private_vault:raise PermissionError("Private Vault cannot enter sync")
  i=SyncIntent(uuid.uuid4().hex,record_id,revision,parent_revision,SyncState.QUEUED);rows=self._load()+[asdict(i)];rows[-1]["state"]=i.state.value;atomic_write_json(self.path,rows);return i
 def ready(self,*,network_reconnected=False,auto_sync_policy=False,explicit_ids=()):
  # reconnect is intentionally not consent
  allowed=set(explicit_ids);return [r for r in self._load() if r["id"] in allowed or auto_sync_policy]
class KnowledgeClass(str,Enum):CANONICAL="CANONICAL";PROJECT="PROJECT";LEARNED="LEARNED";IMPORTED="IMPORTED";CACHE="CACHE"
class EditorialState(str,Enum):DRAFT="DRAFT";REVIEWED="REVIEWED";PUBLISHED="PUBLISHED";SUPERSEDED="SUPERSEDED";RETIRED="RETIRED"
@dataclass
class KnowledgeRecord:id:str;kind:KnowledgeClass;state:EditorialState;text:str;provenance:str;created_at:float;pinned:bool=False;song_id:str="";usage_count:int=0;last_used:float=0;supersedes:str="";song_critical:bool=False
class KnowledgeStore:
 def __init__(self,state:Path):self.root=Path(state)/"knowledge"
 def save(self,r):
  self.root.mkdir(parents=True,exist_ok=True);row=asdict(r);row["kind"]=r.kind.value;row["state"]=r.state.value;atomic_write_json(self.root/f"{r.id}.json",row)
 def prune(self,limit):
  rows=[]
  for p in self.root.glob("*.json"):
   try:r=json.loads(p.read_text());rows.append((p,r))
   except ValueError:continue
  protected=lambda r:r.get("kind")=="CANONICAL" or r.get("pinned") or r.get("song_critical") or r.get("provenance")=="rights"
  order=lambda x:({"CACHE":0,"IMPORTED":2}.get(x[1].get("kind"),1),0 if x[1].get("state")=="SUPERSEDED" else 1,x[1].get("last_used",0))
  removed=[]
  for p,r in sorted((x for x in rows if not protected(x[1])),key=order)[:max(0,len(rows)-limit)]:p.unlink();removed.append(r["id"])
  return removed
