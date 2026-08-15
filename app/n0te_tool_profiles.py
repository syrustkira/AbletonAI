from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import json
import threading
from typing import Any

from n0te_state import atomic_write_json


class CapabilityEvidence(str, Enum):
    DECLARED = "DECLARED"
    DOCUMENTED = "DOCUMENTED"
    OBSERVED = "OBSERVED"
    CHARACTERIZED = "CHARACTERIZED"
    MEASURED = "MEASURED"
    USER_CONFIRMED = "USER_CONFIRMED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ParameterMapping:
    job: str
    parameter: str
    evidence: CapabilityEvidence = CapabilityEvidence.UNKNOWN
    source: str = ""

    @property
    def safe_for_automation(self) -> bool:
        return self.evidence in {CapabilityEvidence.CHARACTERIZED, CapabilityEvidence.MEASURED,
                                 CapabilityEvidence.USER_CONFIRMED}


@dataclass
class ToolProfile:
    tool_id: str
    name: str
    vendor: str = ""
    version: str = ""
    formats: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    capabilities: dict[str, str] = field(default_factory=dict)
    parameters: list[str] = field(default_factory=list)
    mappings: list[ParameterMapping] = field(default_factory=list)
    latency: dict[str, Any] = field(default_factory=dict)
    reliability: dict[str, Any] = field(default_factory=dict)
    portability: str = "UNKNOWN"
    characterization: str = "UNKNOWN"

    def mapping_for(self, job: str) -> ParameterMapping | None:
        return next((item for item in self.mappings if item.job == job and item.safe_for_automation), None)


class ToolProfileStore:
    def __init__(self, state: Path):
        self.path = Path(state) / "tool_profiles.json"
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self, profile: ToolProfile) -> None:
        with self._lock:
            data = self._load()
            row = asdict(profile)
            for mapping in row["mappings"]:
                mapping["evidence"] = mapping["evidence"].value
            data[profile.tool_id] = row
            atomic_write_json(self.path, {key: data[key] for key in sorted(data)})

    def get(self, tool_id: str) -> ToolProfile | None:
        with self._lock:
            row = self._load().get(tool_id)
        if not isinstance(row, dict):
            return None
        row = dict(row)
        row["mappings"] = [ParameterMapping(**{**item, "evidence": CapabilityEvidence(item.get("evidence", "UNKNOWN"))})
                           for item in row.get("mappings") or [] if isinstance(item, dict)]
        return ToolProfile(**row)

    def automation_mapping(self, tool_id: str, job: str) -> ParameterMapping | None:
        profile = self.get(tool_id)
        return profile.mapping_for(job) if profile else None
