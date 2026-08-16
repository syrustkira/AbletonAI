import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import n0te_app
import n0te_provider_bootstrap


class _Lock:
    def __init__(self, events):
        self.events = events
    def acquire(self): self.events.append("lock")
    def release(self): self.events.append("unlock")
    def existing_server(self): return False


class AppBootstrapTests(unittest.TestCase):
    def test_app_migrates_before_ensure_and_bootstraps_provider_after_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = []
            paths = types.SimpleNamespace(
                data=root / "data", logs=root / "logs", cache=root / "cache", recovery=root / "recovery"
            )
            def ensure():
                events.append("ensure")
                for path in (paths.data, paths.logs, paths.cache, paths.recovery): path.mkdir(parents=True, exist_ok=True)
                return paths
            paths.ensure = ensure
            fake_server = types.ModuleType("n0te_server")
            fake_server.main = lambda: events.append("server") or 0
            def migrate(value):
                self.assertIs(value, paths);events.append("migrate");return True
            def bootstrap():
                self.assertEqual(os.environ["N0TE_STATE_DIR"], str(paths.data));events.append("provider")
            with patch.dict(os.environ, {"N0TE_APP_BUNDLE": "", "N0TE_STATE_DIR": "", "N0TE_LOG_DIR": "", "N0TE_CACHE_DIR": ""}, clear=False), \
                 patch.dict(sys.modules, {"n0te_server": fake_server}), \
                 patch.object(n0te_app, "product_paths", return_value=paths), \
                 patch.object(n0te_app, "migrate_legacy_macos", side_effect=migrate), \
                 patch.object(n0te_app, "install_for_application", side_effect=bootstrap), \
                 patch.object(n0te_app, "SingleInstance", side_effect=lambda _: _Lock(events)):
                for key in ("N0TE_STATE_DIR", "N0TE_LOG_DIR", "N0TE_CACHE_DIR"):
                    os.environ.pop(key, None)
                self.assertEqual(n0te_app.main(), 0)
            self.assertLess(events.index("migrate"), events.index("ensure"))
            self.assertLess(events.index("ensure"), events.index("provider"))
            self.assertEqual(events[-3:], ["lock", "server", "unlock"])

    def test_packaged_provider_bootstrap_rebinds_state_exposes_route_and_seeds_safe_config(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            provider = types.ModuleType("n0te_provider")
            provider.STATE = Path("/legacy")
            provider.CONFIG_PATH = provider.STATE / "config.json"
            provider.SECRET_PATH = provider.STATE / "secrets.json"
            provider.provider_config = lambda: {"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1"}
            provider._update_provider_settings = lambda payload: {"provider": payload.get("provider", "ollama")}
            provider.install_provider_router = Mock()
            gemini = types.ModuleType("n0te_gemini_native")
            gemini.install = Mock()
            with patch.dict(sys.modules, {"n0te_provider": provider, "n0te_gemini_native": gemini}), \
                 patch.dict(os.environ, {"N0TE_STATE_DIR": str(state)}, clear=False):
                os.environ.pop("N0TE_ROUTED_PROVIDER_BASE_URL", None)
                n0te_provider_bootstrap._BOOTSTRAPPED = False
                n0te_provider_bootstrap.install_for_application(start_switchboard=False)
                self.assertEqual(provider.STATE, state)
                self.assertEqual(provider.CONFIG_PATH, state / "config.json")
                self.assertEqual(provider.SECRET_PATH, state / "secrets.json")
                seeded = json.loads((state / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(seeded["ai_provider"], "off")
                self.assertEqual(seeded["network_mode"], "offline")
                self.assertFalse(seeded["automatic_update_checking"])
                self.assertFalse(seeded["automatic_safe_install"])
                self.assertEqual(os.environ["N0TE_ROUTED_PROVIDER_BASE_URL"], "http://127.0.0.1:11434/v1")
                gemini.install.assert_called_once_with(provider)
                provider.install_provider_router.assert_called_once_with(start_switchboard=False)


if __name__ == "__main__":
    unittest.main()
