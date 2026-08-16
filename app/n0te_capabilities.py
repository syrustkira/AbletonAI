from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import threading
from typing import Protocol


class ComponentState(str, Enum):
    OFF = "OFF"
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"


class SolutionTier(str, Enum):
    CURRENT_PROJECT = "CURRENT_PROJECT"
    DAW_NATIVE = "DAW_NATIVE"
    OWNED_TOOL = "OWNED_TOOL"
    OWNED_COMBINATION = "OWNED_COMBINATION"
    OS_NATIVE = "OS_NATIVE"
    N0TE_ORCHESTRATION = "N0TE_ORCHESTRATION"
    N0TE_GAP_FILL = "N0TE_GAP_FILL"
    OPTIONAL_EXTERNAL = "OPTIONAL_EXTERNAL"
    GUIDED_MANUAL = "GUIDED_MANUAL"


@dataclass(frozen=True)
class Capability:
    name: str
    version: str = "1"
    local: bool = True
    mutation_authority: bool = False
    cost_class: str = "none"
    solution_tier: SolutionTier = SolutionTier.N0TE_ORCHESTRATION
    owned: bool = True
    portability: int = 50
    reliability: int = 50
    user_interaction: int = 0


class CapabilityAdapter(Protocol):
    adapter_id: str
    def health(self) -> ComponentState: ...
    def capabilities(self) -> tuple[Capability, ...]: ...
    def protocol_version(self) -> str: ...


class CapabilityRegistry:
    """Runtime capability resolution without implicit privacy/cost escalation."""

    def __init__(self) -> None:
        self._adapters: dict[str, CapabilityAdapter] = {}
        self._lock = threading.RLock()

    def register(self, adapter: CapabilityAdapter) -> None:
        with self._lock:
            self._adapters[adapter.adapter_id] = adapter

    def unregister(self, adapter_id: str) -> None:
        with self._lock:
            self._adapters.pop(adapter_id, None)

    def resolve(self, name: str, *, allow_remote: bool = False, allow_cost: bool = False, allow_mutation: bool = False) -> CapabilityAdapter | None:
        with self._lock:
            adapters = tuple(self._adapters.values())
        ranked: list[tuple[tuple[int, ...], str, CapabilityAdapter]] = []
        tier_rank = {tier: position for position, tier in enumerate(SolutionTier)}
        for adapter in adapters:
            if adapter.health() is not ComponentState.READY:
                continue
            for capability in adapter.capabilities():
                if capability.name != name:
                    continue
                if not capability.local and not allow_remote:
                    continue
                if capability.cost_class != "none" and not allow_cost:
                    continue
                if capability.mutation_authority and not allow_mutation:
                    continue
                rank = (tier_rank[capability.solution_tier], 0 if capability.local else 1,
                        0 if capability.cost_class == "none" else 1, 0 if not capability.mutation_authority else 1,
                        0 if capability.owned else 1, -max(0, min(capability.reliability, 100)),
                        -max(0, min(capability.portability, 100)), max(0, capability.user_interaction))
                ranked.append((rank, adapter.adapter_id, adapter))
        return min(ranked, default=((), "", None))[2]

    def status(self) -> list[dict[str, object]]:
        with self._lock:
            adapters = tuple(self._adapters.values())
        return [{"adapter_id": item.adapter_id, "protocol_version": item.protocol_version(), "state": item.health().value,
                 "capabilities": [asdict(cap) for cap in item.capabilities()]} for item in adapters]
