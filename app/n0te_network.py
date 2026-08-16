from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ipaddress
import urllib.parse


class NetworkMode(str, Enum):
    OFFLINE = "offline"
    LAN = "lan"
    COLLABORATION = "collaboration"
    FULL = "full"


@dataclass(frozen=True)
class NetworkDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class NetworkPolicy:
    """Central, fail-closed policy for N0TE-owned outbound connections."""

    mode: NetworkMode = NetworkMode.OFFLINE

    @classmethod
    def from_value(cls, value: object) -> "NetworkPolicy":
        try:
            return cls(NetworkMode(str(value or "offline").strip().lower()))
        except ValueError:
            return cls(NetworkMode.OFFLINE)

    def decide(self, url: str, *, collaboration: bool = False) -> NetworkDecision:
        parsed = urllib.parse.urlsplit(str(url or ""))
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            return NetworkDecision(False, "invalid or unsupported network destination")
        loopback = host == "localhost"
        private = False
        try:
            address = ipaddress.ip_address(host)
            loopback = loopback or address.is_loopback
            private = address.is_private
        except ValueError:
            pass
        if loopback:
            return NetworkDecision(True, "loopback is always available to local N0TE components")
        if self.mode is NetworkMode.OFFLINE:
            return NetworkDecision(False, "network mode is OFFLINE")
        if self.mode is NetworkMode.LAN:
            return NetworkDecision(private, "LAN permits private addresses only" if private else "destination is outside the LAN")
        if self.mode is NetworkMode.COLLABORATION:
            return NetworkDecision(collaboration, "approved collaboration destination" if collaboration else "destination is not an approved collaboration connection")
        return NetworkDecision(True, "network mode is FULL")

    def require(self, url: str, *, collaboration: bool = False) -> None:
        decision = self.decide(url, collaboration=collaboration)
        if not decision.allowed:
            raise PermissionError(decision.reason)

    def status(self) -> dict[str, object]:
        return {"mode": self.mode.value.upper(), "intentional_offline": self.mode is NetworkMode.OFFLINE}
