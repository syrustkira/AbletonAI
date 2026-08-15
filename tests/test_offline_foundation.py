import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_capabilities import Capability, CapabilityRegistry, ComponentState
from n0te_network import NetworkMode, NetworkPolicy
import n0te_provider as provider
import n0te_server as server


class FakeAdapter:
    def __init__(self, adapter_id, state, capabilities):
        self.adapter_id = adapter_id
        self._state = state
        self._capabilities = tuple(capabilities)

    def health(self): return self._state
    def capabilities(self): return self._capabilities
    def protocol_version(self): return "1"


class OfflineFoundationTests(unittest.TestCase):
    def test_offline_policy_allows_loopback_and_denies_non_loopback(self):
        policy = NetworkPolicy(NetworkMode.OFFLINE)
        self.assertTrue(policy.decide("http://127.0.0.1:8765").allowed)
        self.assertTrue(policy.decide("http://localhost:11434").allowed)
        for url in ("https://api.openai.com/v1", "https://example.com", "http://192.168.1.2"):
            self.assertFalse(policy.decide(url).allowed)
            with self.assertRaises(PermissionError):
                policy.require(url)

    def test_unknown_network_mode_fails_closed(self):
        self.assertEqual(NetworkPolicy.from_value("surprise").mode, NetworkMode.OFFLINE)

    def test_capability_resolution_does_not_silently_escalate_cost_or_cloud(self):
        registry = CapabilityRegistry()
        cloud = FakeAdapter("cloud", ComponentState.READY, [Capability("reason", local=False, cost_class="metered")])
        local = FakeAdapter("local", ComponentState.READY, [Capability("reason")])
        registry.register(cloud)
        self.assertIsNone(registry.resolve("reason"))
        registry.register(local)
        self.assertIs(registry.resolve("reason"), local)
        registry.unregister("local")
        self.assertIs(registry.resolve("reason", allow_remote=True, allow_cost=True), cloud)

    def test_unavailable_and_mutating_adapters_are_not_implicitly_selected(self):
        registry = CapabilityRegistry()
        unavailable = FakeAdapter("down", ComponentState.UNAVAILABLE, [Capability("edit")])
        mutator = FakeAdapter("mutator", ComponentState.READY, [Capability("edit", mutation_authority=True)])
        registry.register(unavailable); registry.register(mutator)
        self.assertIsNone(registry.resolve("edit"))
        self.assertIs(registry.resolve("edit", allow_mutation=True), mutator)

    def test_ai_off_requires_no_key_and_reports_intentional_off_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text(json.dumps({"ai_provider": "off", "network_mode": "offline"}))
            with patch.object(provider, "STATE", root), patch.object(provider, "CONFIG_PATH", root / "config.json"), \
                    patch.object(provider, "SECRET_PATH", root / "secrets.json"), patch.dict(provider.os.environ, {}, clear=True):
                status = provider.provider_status()
                self.assertEqual(status["provider"], "off")
                self.assertEqual(status["state"], "OFF")
                self.assertFalse(status["key_required"])
                req = urllib.request.Request(provider.OPENAI_RESPONSES_URL, data=b"{}")
                with self.assertRaisesRegex(provider.ProviderUnavailableError, "intentionally OFF"):
                    provider.routed_urlopen(req)

    def test_offline_policy_blocks_cloud_ai_before_transport(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text(json.dumps({"ai_provider": "openai", "network_mode": "offline"}))
            with patch.object(provider, "STATE", root), patch.object(provider, "CONFIG_PATH", root / "config.json"), \
                    patch.object(provider, "SECRET_PATH", root / "secrets.json"), patch.object(provider, "_ORIGINAL_URLOPEN") as network:
                req = urllib.request.Request(provider.OPENAI_RESPONSES_URL, data=b"{}")
                with self.assertRaises(PermissionError): provider.routed_urlopen(req)
                network.assert_not_called()

    def test_server_ai_off_refuses_inference_without_touching_transport(self):
        with patch.object(server, "load_config", return_value={"ai_provider": "off"}), \
                patch.object(server.urllib.request, "urlopen") as network:
            with self.assertRaisesRegex(server.DependencyUnavailableError, "intentionally OFF"):
                server.ask_openai("status", {})
            network.assert_not_called()

    def test_status_distinguishes_ai_network_and_community_intentional_off(self):
        config = {"ai_provider": "off", "network_mode": "offline", "community_enabled": False, "context_sync_path": ""}
        ai = {"provider": "off", "state": "OFF", "key_required": False}
        with patch.object(server, "load_config", return_value=config), patch.object(server, "provider_status", return_value=ai), \
                patch.object(server, "get_snapshot", side_effect=ConnectionError("Ableton offline")):
            status = server.status_payload()
        self.assertFalse(status["ok"])
        self.assertEqual(status["services"]["ai"]["state"], "OFF")
        self.assertEqual(status["services"]["network"]["mode"], "OFFLINE")
        self.assertEqual(status["services"]["community"]["state"], "OFF")


if __name__ == "__main__":
    unittest.main()
