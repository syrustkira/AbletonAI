from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json, threading, time, uuid
from typing import Any
from n0te_state import atomic_write_json

@dataclass
class Workspace:
    workspace_id: str; song_id: str; host: str; host_project_identity: str
    path: str = ""; saved: bool = False; metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Song:
    song_id: str; title: str = "Untitled"; created_at: float = 0; updated_at: float = 0
    metadata: dict[str, Any] = field(default_factory=dict); context: dict[str, Any] = field(default_factory=dict)
    rights: dict[str, Any] = field(default_factory=dict); assets: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list); events: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list); workspaces: list[Workspace] = field(default_factory=list)

class SongStore:
    """Non-destructive Song-above-workspace identity store."""
    def __init__(self, state: Path):
        self.root=Path(state)/"song_records"; self.map_path=Path(state)/"song_workspace_map.json"; self._lock=threading.RLock()
    def _map(self):
        try:
            value=json.loads(self.map_path.read_text()); return value if isinstance(value,dict) else {}
        except (OSError,ValueError): return {}
    def for_workspace(self, legacy_song_key: str, host: str, host_identity: str, path: str="") -> Song:
        """Idempotently maps proven legacy ownership; never rewrites old ProjectStore data."""
        identity=f"{host}:{host_identity}:{legacy_song_key}"
        with self._lock:
            mapping=self._map(); song_id=mapping.get(identity)
            if song_id:
                song=self.get(song_id)
                if song: return song
            now=time.time(); song_id=uuid.uuid4().hex
            workspace=Workspace(uuid.uuid4().hex,song_id,host,host_identity,path,bool(path),{"legacy_song_key":legacy_song_key})
            song=Song(song_id,Path(path).stem if path else "Untitled",now,now,workspaces=[workspace])
            self.save(song); mapping[identity]=song_id; atomic_write_json(self.map_path,mapping); return song
    def save(self,song:Song):
        song.updated_at=time.time(); self.root.mkdir(parents=True,exist_ok=True)
        row=asdict(song); atomic_write_json(self.root/f"{song.song_id}.json",row)
    def get(self,song_id:str)->Song|None:
        try: row=json.loads((self.root/f"{song_id}.json").read_text())
        except (OSError,ValueError): return None
        row["workspaces"]=[Workspace(**x) for x in row.get("workspaces",[])]; return Song(**row)
    def attach_workspace(self,song_id:str,host:str,host_identity:str,path:str="",metadata=None)->Workspace:
        with self._lock:
            song=self.get(song_id)
            if not song: raise LookupError("Unknown Song")
            existing=next((w for w in song.workspaces if w.host==host and w.host_project_identity==host_identity),None)
            if existing:return existing
            ws=Workspace(uuid.uuid4().hex,song_id,host,host_identity,path,bool(path),metadata or {})
            song.workspaces.append(ws); self.save(song); return ws
