from __future__ import annotations
from dataclasses import dataclass
import sys,time
try:
 import resource as _resource
except ImportError:  # Windows
 _resource=None
@dataclass(frozen=True)
class CompactHealth:
 state:str;uptime_seconds:float;rss_bytes:int|None;daw_online:bool;ai_state:str;network_mode:str;safe:bool;recovery_required:bool
class ObservabilityEngine:
 """Cheap process-local sampling. Unsupported external metrics stay absent."""
 def __init__(self,started_at=None):self.started_at=started_at or time.monotonic()
 def _rss(self):
  if _resource is None:return None
  value=_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
  return int(value*(1 if sys.platform=="darwin" else 1024))
 def sample(self,*,daw_online,ai,network,community,safety,recovery,capabilities=(),song=None,workspace=None,queues=None,workers=None,counts=None,guardian="AUTO"):
  rss=self._rss();compact=CompactHealth("DEGRADED" if recovery.get("recovery_required") else "READY",max(0,time.monotonic()-self.started_at),rss,bool(daw_online),str(ai.get("state","UNAVAILABLE")),str(network.get("mode","OFFLINE")),bool(safety.get("safe")),bool(recovery.get("recovery_required")))
  unsupported=["daw_cpu","audio_xruns","audio_latency","camera_dropped_frames","stream_bitrate"]
  if rss is None:unsupported.append("process_rss")
  detailed={**compact.__dict__,"community_state":community.get("state","OFF"),"song_id":song,"workspace_id":workspace,
   "capabilities":list(capabilities),"queues":dict(queues or {}),"workers":dict(workers or {}),"counts":dict(counts or {}),
   "guardian_profile":guardian,"quarantined_components":sorted(recovery.get("quarantine",{})),
   "unsupported_metrics":unsupported}
  return {"compact":compact.__dict__,"detailed":detailed}
