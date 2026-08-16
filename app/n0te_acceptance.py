from __future__ import annotations
from dataclasses import asdict,dataclass
from pathlib import Path
import time
from n0te_state import atomic_write_json
@dataclass(frozen=True)
class CapabilityAcceptance:
 host:str;host_version:str;adapter_version:str;platform:str;architecture:str;capability:str;operation_risk:str;result:str;compatibility_state:str;evidence_source:str;timestamp:float
class CapabilityAcceptanceStore:
 def __init__(self,path:Path):self.path=Path(path)
 def record(self,**values):
  values.setdefault('timestamp',time.time());item=CapabilityAcceptance(**values);rows=self.load();rows.append(asdict(item));atomic_write_json(self.path,{"schema":1,"records":rows});return asdict(item)
 def load(self):
  import json
  try:return json.loads(self.path.read_text()).get('records',[])
  except Exception:return []
