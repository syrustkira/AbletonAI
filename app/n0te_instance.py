from __future__ import annotations
from pathlib import Path
import json,os,socket,time
try:import fcntl
except ImportError:fcntl=None
class AlreadyRunningError(RuntimeError):pass
class SingleInstance:
 def __init__(self,path:Path,port=8766):self.path=Path(path);self.port=port;self.handle=None
 def acquire(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);self.handle=self.path.open("a+")
  if fcntl is None:raise RuntimeError("Single-instance locking unavailable")
  try:fcntl.flock(self.handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError as exc:
   self.handle.close();self.handle=None;raise AlreadyRunningError("N0TE is already running") from exc
  self.handle.seek(0);self.handle.truncate();json.dump({"pid":os.getpid(),"port":self.port,"started_at":time.time()},self.handle);self.handle.flush();os.fsync(self.handle.fileno());return self
 def existing_server(self):
  try:
   with socket.create_connection(("127.0.0.1",self.port),.3):return True
  except OSError:return False
 def release(self):
  if self.handle:
   fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN);self.handle.close();self.handle=None
 def __enter__(self):return self.acquire()
 def __exit__(self,*_):self.release()
