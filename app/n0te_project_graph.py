from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

class PortabilityStatus(str,Enum):
    FULLY_PORTABLE="FULLY_PORTABLE"; TRANSLATED="TRANSLATED"; COMPENSATED="COMPENSATED"; UNAVAILABLE="UNAVAILABLE"

@dataclass
class GraphNode:
    id:str; kind:str; name:str=""; host_type:str=""; data:dict[str,Any]=field(default_factory=dict); extensions:dict[str,Any]=field(default_factory=dict)

@dataclass
class ProjectGraph:
    song_id:str; workspace_id:str; nodes:list[GraphNode]=field(default_factory=list); edges:list[dict[str,str]]=field(default_factory=list)
    tempo:float|None=None; markers:list[dict[str,Any]]=field(default_factory=list); sections:list[dict[str,Any]]=field(default_factory=list)
    VALID_KINDS=frozenset({"Track","Device","ClipRegion","MIDI","AudioAsset","Routing","Automation","Transport","Tempo","Marker","Section"})
    def validate(self):
        ids=set()
        for node in self.nodes:
            if node.kind not in self.VALID_KINDS: raise ValueError(f"Unknown universal kind: {node.kind}")
            if not node.id or node.id in ids: raise ValueError("Node IDs must be unique")
            ids.add(node.id)
        for edge in self.edges:
            if edge.get("from") not in ids or edge.get("to") not in ids: raise ValueError("Edge references unknown node")
        return True
    def to_dict(self): self.validate(); return asdict(self)
    @classmethod
    def from_dict(cls,row):
        value=cls(**{**row,"nodes":[GraphNode(**n) for n in row.get("nodes",[])]}); value.validate(); return value

class PortabilityEngine:
    METRICS=("MUSICAL_PRESERVATION","AUDIO_PRESERVATION","EDITABILITY","AUTOMATION_ROUTING_FIDELITY")
    def assess(self,graph:ProjectGraph)->dict[str,Any]:
        graph.validate(); results=[]
        for node in graph.nodes:
            status=PortabilityStatus.FULLY_PORTABLE
            reason="universal representation"
            if node.kind=="Device" and not node.data.get("portable",False): status=PortabilityStatus.UNAVAILABLE; reason="host/plugin implementation unavailable"
            elif node.host_type: status=PortabilityStatus.TRANSLATED; reason="host-specific semantics retained in extensions"
            results.append({"node_id":node.id,"status":status.value,"reason":reason})
        unavailable=sum(x["status"]==PortabilityStatus.UNAVAILABLE.value for x in results)
        score=max(0,100-round(100*unavailable/max(1,len(results))))
        return {"results":results,"metrics":{m:score for m in self.METRICS},"destructive_conversion":False}
    def survival_manifest(self,song,graph:ProjectGraph,**ledgers):
        report=self.assess(graph)
        return {"schema_version":1,"song":asdict(song),"graph":graph.to_dict(),"portability":report,
                "plugin_inventory":ledgers.get("plugin_inventory",[]),"decisions":ledgers.get("decisions",[]),
                "checkpoints":ledgers.get("checkpoints",[]),"job_ledger":ledgers.get("job_ledger",[]),
                "reference_bounces":ledgers.get("reference_bounces",[]),"export_candidates_only":True}
