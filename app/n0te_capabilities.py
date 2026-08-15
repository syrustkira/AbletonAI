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


@dataclass(frozen=True)
class Capability:
    name: str
    version: str = "1"
    local: bool = True
    mutation_authority: bool = False
    cost_class: str = "none"


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
                return adapter
        return None

    def status(self) -> list[dict[str, object]]:
        with self._lock:
            adapters = tuple(self._adapters.values())
        return [{"adapter_id": item.adapter_id, "protocol_version": item.protocol_version(), "state": item.health().value,
                 "capabilities": [asdict(cap) for cap in item.capabilities()]} for item in adapters]
