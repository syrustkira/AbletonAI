from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import hashlib, platform as host_platform, re
from typing import Iterable

from n0te_capabilities import ComponentState
from n0te_platform import IntegrationTier


class HostFamily(str, Enum):
    ABLETON_LIVE = "ABLETON_LIVE"
    LOGIC_PRO = "LOGIC_PRO"
    FL_STUDIO = "FL_STUDIO"
    PRO_TOOLS = "PRO_TOOLS"


@dataclass(frozen=True)
class HostDefinition:
    family: HostFamily
    display_name: str
    patterns: tuple[str, ...]
    adapter_component_id: str
    adapter_available: bool = False
    implementation_maturity: IntegrationTier = IntegrationTier.DETECTED_UNSUPPORTED
    target_maturity: IntegrationTier = IntegrationTier.DEEP


OFFICIAL_HOSTS = (
    HostDefinition(HostFamily.ABLETON_LIVE, "Ableton Live", (r"Live (?P<version>.+)\.app$", r"Ableton Live (?P<version>.+)$"), "ABLETON_ADAPTER", True, IntegrationTier.DEEP),
    HostDefinition(HostFamily.LOGIC_PRO, "Logic Pro", (r"Logic Pro(?: (?P<version>.+))?\.app$",), "LOGIC_ADAPTER"),
    HostDefinition(HostFamily.FL_STUDIO, "FL Studio", (r"FL Studio(?: (?P<version>.+))?\.app$", r"FL Studio(?: (?P<version>.+))?$"), "FL_STUDIO_ADAPTER"),
    HostDefinition(HostFamily.PRO_TOOLS, "Pro Tools", (r"Pro Tools(?: (?P<version>.+))?\.app$", r"Pro Tools(?: (?P<version>.+))?$"), "PRO_TOOLS_ADAPTER"),
)


@dataclass
class AdapterInstallation:
    component_id: str
    installed: bool = False
    version: str = ""
    aggregate_health: ComponentState = ComponentState.OFF
    connection_state: ComponentState = ComponentState.OFF
    repair_available: bool = False
    update_available: bool = False
    capability_counts: dict[str, int] = field(default_factory=dict)
    evidence_verified: bool = False
    evidence_source: str = ""


@dataclass
class DawInstallationDescriptor:
    installation_id: str
    host_family: HostFamily
    display_name: str
    installed: bool
    detected_version: str
    installation_path: str
    platform: str
    architecture: str
    adapter_available: bool
    adapter_installed: bool
    adapter_version: str
    implementation_maturity: IntegrationTier
    target_maturity: IntegrationTier
    aggregate_health: ComponentState
    connection_state: ComponentState
    install_available: bool
    repair_available: bool
    update_available: bool
    capability_counts: dict[str, int] = field(default_factory=dict)
    adapter_evidence_verified: bool = False
    adapter_evidence_source: str = ""

    def status(self):
        value = asdict(self)
        for key in ("host_family", "implementation_maturity", "target_maturity", "aggregate_health", "connection_state"):
            value[key] = getattr(self, key).value
        return value


class DawDiscoveryService:
    """Single detector shared by setup, runtime, settings, diagnostics and updater."""
    def __init__(self, search_roots: Iterable[Path] | None = None, adapters: dict[str, AdapterInstallation] | None = None, *, platform_name: str | None = None, architecture: str | None = None, definitions=OFFICIAL_HOSTS, metadata_backend=None):
        self.platform = platform_name or host_platform.system().lower()
        self.architecture = architecture or host_platform.machine().lower()
        self.search_roots = tuple(Path(x) for x in (search_roots or self.default_roots(self.platform)))
        self.adapters = adapters or {}
        self.definitions = tuple(definitions)
        self.metadata_backend = metadata_backend

    @staticmethod
    def default_roots(platform_name: str):
        if platform_name in {"darwin", "mac", "macos"}: return (Path("/Applications"), Path.home()/"Applications")
        if platform_name in {"windows", "win32", "win"}: return (Path("C:/Program Files"), Path("C:/Program Files (x86)"))
        return ()

    def discover(self, *, include_missing=False):
        found=[]
        for definition in self.definitions:
            matches=[]
            if self.metadata_backend:
                matches.extend((meta.path,meta.version) for family,meta in self.metadata_backend.applications() if family is definition.family)
            for root in self.search_roots:
                if not root.is_dir(): continue
                for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                    version=self._match(definition, path.name)
                    if version is not None and all(existing[0] != path for existing in matches): matches.append((path, version or "UNKNOWN"))
            for path,version in matches: found.append(self._descriptor(definition,path,version,True))
            if include_missing and not matches: found.append(self._descriptor(definition,None,"",False))
        return found

    def _match(self, definition, name):
        for pattern in definition.patterns:
            match=re.fullmatch(pattern,name,re.I)
            if match:return (match.groupdict().get("version") or "").removesuffix(" Beta") + (" Beta" if "Beta" in name else "")
        return None

    def _descriptor(self, definition, path, version, installed):
        adapter=self.adapters.get(definition.adapter_component_id, AdapterInstallation(definition.adapter_component_id))
        identity=hashlib.sha256(f"{definition.family.value}|{path or ''}|{version}".encode()).hexdigest()[:20]
        evidence_verified=bool(adapter.evidence_verified)
        adapter_installed=bool(adapter.installed and evidence_verified)
        if evidence_verified:
            aggregate_health=adapter.aggregate_health
            connection_state=adapter.connection_state
            capability_counts=dict(adapter.capability_counts)
        elif adapter.installed:
            aggregate_health=ComponentState.UNAVAILABLE
            connection_state=ComponentState.UNAVAILABLE
            capability_counts={}
        else:
            aggregate_health=ComponentState.OFF
            connection_state=ComponentState.OFF
            capability_counts={}
        install_available=bool(definition.adapter_available and not adapter.installed)
        repair_available=bool(adapter.repair_available or (adapter.installed and not evidence_verified))
        return DawInstallationDescriptor(
            identity,definition.family,definition.display_name,installed,version,str(path or ""),self.platform,self.architecture,
            definition.adapter_available,adapter_installed,adapter.version,definition.implementation_maturity,definition.target_maturity,
            aggregate_health,connection_state,install_available,repair_available,adapter.update_available,capability_counts,
            evidence_verified,adapter.evidence_source if evidence_verified else ""
        )
