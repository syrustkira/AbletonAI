from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import json
import time

from n0te_state import atomic_write_json


class SetupStep(str, Enum):
    WELCOME = "WELCOME"
    DETECT_DAWS = "DETECT_DAWS"
    DAW_INTEGRATIONS = "DAW_INTEGRATIONS"
    AI_MODE = "AI_MODE"
    NETWORK_MODE = "NETWORK_MODE"
    OPTIONAL_OBS = "OPTIONAL_OBS"
    CAMERA = "CAMERA"
    OPTIONAL_LOCAL_AI = "OPTIONAL_LOCAL_AI"
    ARTIST_IDENTITY = "ARTIST_IDENTITY"
    DIAGNOSTICS = "DIAGNOSTICS"
    READY = "READY"


STEPS = tuple(SetupStep)


@dataclass
class FirstRunState:
    step: SetupStep = SetupStep.WELCOME
    ai_mode: str = "OFF"
    network_mode: str = "OFFLINE"
    obs_enabled: bool = False
    camera_enabled: bool = False
    local_ai_enabled: bool = False
    artist_identity: dict = field(default_factory=dict)
    complete: bool = False


class FirstRunService:
    """Persistent first-run flow with fail-closed runtime defaults."""

    SAFE_CONFIG_DEFAULTS = {
        "ai_provider": "off",
        "network_mode": "offline",
        "community_enabled": False,
        "automatic_update_checking": False,
        "automatic_safe_install": False,
    }

    def __init__(self, path: Path, discovery):
        self.path = Path(path)
        self.config_path = self.path.with_name("config.json")
        self.recovery_dir = self.path.parent / "Recovery"
        self.discovery = discovery
        self.state = FirstRunState()
        self._ensure_safe_runtime_defaults()
        if self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.state = FirstRunState(**{
                    **raw,
                    "step": SetupStep(raw.get("step", "WELCOME")),
                })
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                self.state = FirstRunState()

    def _preserve_corrupt_config(self) -> str:
        try:
            if not self.config_path.is_file():
                return ""
            self.recovery_dir.mkdir(parents=True, exist_ok=True)
            target = self.recovery_dir / f"config-corrupt-{int(time.time() * 1000)}.json"
            target.write_bytes(self.config_path.read_bytes())
            return str(target)
        except OSError:
            return ""

    def _ensure_safe_runtime_defaults(self) -> None:
        """Preserve explicit choices, fill missing safety keys, and fail closed on corrupt config."""
        if not self.config_path.exists():
            atomic_write_json(self.config_path, dict(self.SAFE_CONFIG_DEFAULTS))
            return
        try:
            current = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(current, dict):
                raise ValueError("config must be a JSON object")
        except (OSError, ValueError, json.JSONDecodeError):
            self._preserve_corrupt_config()
            atomic_write_json(self.config_path, dict(self.SAFE_CONFIG_DEFAULTS))
            return
        changed = False
        for key, value in self.SAFE_CONFIG_DEFAULTS.items():
            if key not in current:
                current[key] = value
                changed = True
        if changed:
            atomic_write_json(self.config_path, current)

    def _sync_fail_closed_choices(self) -> None:
        """Persist explicit OFF/OFFLINE choices into the shared runtime config."""
        try:
            current = json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path.exists() else {}
            if not isinstance(current, dict):
                current = {}
        except (OSError, json.JSONDecodeError):
            current = {}
        for key, value in self.SAFE_CONFIG_DEFAULTS.items():
            current.setdefault(key, value)
        if str(self.state.ai_mode).upper() == "OFF":
            current["ai_provider"] = "off"
        current["network_mode"] = str(self.state.network_mode or "OFFLINE").lower()
        atomic_write_json(self.config_path, current)

    def detect_daws(self):
        return [item.status() for item in self.discovery.discover(include_missing=True)]

    def advance(self, values=None):
        values = values or {}
        for key in (
            "ai_mode",
            "network_mode",
            "obs_enabled",
            "camera_enabled",
            "local_ai_enabled",
            "artist_identity",
        ):
            if key in values:
                setattr(self.state, key, values[key])
        self._sync_fail_closed_choices()
        index = STEPS.index(self.state.step)
        if index < len(STEPS) - 1:
            self.state.step = STEPS[index + 1]
        self.state.complete = self.state.step is SetupStep.READY
        atomic_write_json(self.path, {**asdict(self.state), "step": self.state.step.value})
        return self.status()

    def status(self):
        return {
            **asdict(self.state),
            "step": self.state.step.value,
            "healthy": True,
            "optional_skips_allowed": True,
        }
