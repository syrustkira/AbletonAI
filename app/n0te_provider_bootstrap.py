"""Explicit provider-router bootstrap for the supported packaged application."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_BOOTSTRAPPED = False


def install_for_application(*, start_switchboard: bool = True) -> None:
    """Bind provider state to product paths and install routing once.

    This is called by ``n0te_app`` after product paths and environment variables
    are established. Direct ``n0te_server.py`` launches retain the legacy
    context bootstrap for developer compatibility.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    import n0te_provider as provider
    from n0te_gemini_native import install as install_gemini_native

    state = Path(os.environ.get("N0TE_STATE_DIR") or provider.STATE)
    provider.STATE = state
    provider.CONFIG_PATH = state / "config.json"
    provider.SECRET_PATH = state / "secrets.json"
    install_gemini_native(provider)
    placeholder = "n0te-provider-router"

    def sync_routing_state(active_provider: str | None = None) -> None:
        config = provider.provider_config()
        provider_name = str(active_provider or config.get("provider") or "off").lower()
        current = str(os.environ.get("OPENAI_API_KEY") or "")
        if provider_name == "openai":
            if current == placeholder:
                os.environ.pop("OPENAI_API_KEY", None)
        elif not current:
            os.environ["OPENAI_API_KEY"] = placeholder
        base_url = str(config.get("base_url") or "").strip()
        if base_url:
            os.environ["N0TE_ROUTED_PROVIDER_BASE_URL"] = base_url
        else:
            os.environ.pop("N0TE_ROUTED_PROVIDER_BASE_URL", None)

    original_update = provider._update_provider_settings

    def update_with_guard(payload: dict[str, Any]) -> dict[str, Any]:
        status = original_update(payload)
        sync_routing_state(str(status.get("provider") or "off"))
        return status

    provider._update_provider_settings = update_with_guard
    sync_routing_state()
    provider.install_provider_router(start_switchboard=start_switchboard)
    _BOOTSTRAPPED = True
