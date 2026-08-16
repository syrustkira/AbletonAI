import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_network import NetworkMode, NetworkPolicy


class NetworkDefaultTests(unittest.TestCase):
    def test_network_policy_defaults_fail_closed(self):
        with patch.dict(os.environ, {"N0TE_ROUTED_PROVIDER_BASE_URL": ""}, clear=False):
            self.assertEqual(NetworkPolicy().mode, NetworkMode.OFFLINE)
            self.assertEqual(NetworkPolicy.from_value(None).mode, NetworkMode.OFFLINE)
            self.assertFalse(NetworkPolicy().decide("https://api.openai.com/v1").allowed)
            self.assertTrue(NetworkPolicy().decide("http://127.0.0.1:8766").allowed)

    def test_offline_legacy_openai_shape_allows_local_ollama_route_only(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            (state / "config.json").write_text(json.dumps({"ai_provider": "ollama"}), encoding="utf-8")
            with patch.dict(os.environ, {"N0TE_STATE_DIR": str(state)}, clear=False):
                os.environ.pop("N0TE_ROUTED_PROVIDER_BASE_URL", None)
                decision = NetworkPolicy(NetworkMode.OFFLINE).decide("https://api.openai.com/v1/responses")
            self.assertTrue(decision.allowed)

    def test_offline_legacy_openai_shape_still_blocks_cloud_route(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            (state / "config.json").write_text(json.dumps({"ai_provider": "gemini"}), encoding="utf-8")
            with patch.dict(os.environ, {"N0TE_STATE_DIR": str(state)}, clear=False):
                os.environ.pop("N0TE_ROUTED_PROVIDER_BASE_URL", None)
                decision = NetworkPolicy(NetworkMode.OFFLINE).decide("https://api.openai.com/v1/responses")
            self.assertFalse(decision.allowed)


if __name__ == "__main__":
    unittest.main()
