import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_daw_discovery import *
from n0te_setup import *


class DawSetupTests(unittest.TestCase):
    def test_multiple_daws_and_versions_remain_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            [(root / name).mkdir() for name in ("Live 12.3.app", "Live 12.4 Beta.app", "Logic Pro.app", "Pro Tools 2025.app")]
            service = DawDiscoveryService([root], platform_name="darwin", architecture="arm64")
            rows = service.discover()
            self.assertEqual(len(rows), 4)
            ableton = [x for x in rows if x.host_family is HostFamily.ABLETON_LIVE]
            self.assertEqual(len(ableton), 2)
            self.assertNotEqual(ableton[0].installation_id, ableton[1].installation_id)
            logic = next(x for x in rows if x.host_family is HostFamily.LOGIC_PRO)
            self.assertEqual(logic.implementation_maturity, IntegrationTier.DETECTED_UNSUPPORTED)
            self.assertEqual(logic.target_maturity, IntegrationTier.DEEP)
            self.assertTrue(all(not hasattr(x, "song_id") for x in rows))

    def test_missing_hosts_are_truthful_healthy_setup_states(self):
        with tempfile.TemporaryDirectory() as td:
            rows = DawDiscoveryService([Path(td)], platform_name="darwin").discover(include_missing=True)
            self.assertEqual({x.host_family for x in rows}, set(HostFamily))
            self.assertTrue(all(not x.installed for x in rows))
            self.assertTrue(all(x.target_maturity is IntegrationTier.DEEP for x in rows))

    def test_first_run_and_runtime_share_detector_and_optional_offline_finishes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detector = DawDiscoveryService([root], platform_name="darwin")
            setup = FirstRunService(root / "setup.json", detector)
            self.assertEqual(setup.detect_daws(), [x.status() for x in detector.discover(include_missing=True)])
            while not setup.state.complete:
                setup.advance({
                    "ai_mode": "OFF",
                    "network_mode": "OFFLINE",
                    "obs_enabled": False,
                    "camera_enabled": False,
                    "local_ai_enabled": False,
                })
            self.assertTrue(setup.status()["healthy"])
            self.assertEqual(setup.status()["step"], "READY")
            restored = FirstRunService(root / "setup.json", detector)
            self.assertTrue(restored.status()["complete"])
            self.assertEqual(restored.status()["network_mode"], "OFFLINE")

    def test_fresh_first_run_seeds_fail_closed_runtime_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detector = DawDiscoveryService([root], platform_name="darwin")
            FirstRunService(root / "first_run.json", detector)
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["ai_provider"], "off")
            self.assertEqual(config["network_mode"], "offline")
            self.assertFalse(config["community_enabled"])
            self.assertFalse(config["automatic_update_checking"])
            self.assertFalse(config["automatic_safe_install"])

    def test_first_run_preserves_explicit_choices_and_fills_missing_safe_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            existing = {
                "ai_provider": "gemini",
                "network_mode": "full",
                "community_enabled": True,
                "automatic_update_checking": True,
                "custom_setting": "keep-me",
            }
            (root / "config.json").write_text(json.dumps(existing), encoding="utf-8")
            detector = DawDiscoveryService([root], platform_name="darwin")
            FirstRunService(root / "first_run.json", detector)
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            for key, value in existing.items():
                self.assertEqual(config[key], value)
            self.assertFalse(config["automatic_safe_install"])

    def test_corrupt_runtime_config_is_preserved_and_replaced_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_bytes(b"{broken")
            detector = DawDiscoveryService([root], platform_name="darwin")
            FirstRunService(root / "first_run.json", detector)
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["ai_provider"], "off")
            self.assertEqual(config["network_mode"], "offline")
            recovery = list((root / "Recovery").glob("config-corrupt-*.json"))
            self.assertEqual(len(recovery), 1)
            self.assertEqual(recovery[0].read_bytes(), b"{broken")

    def test_explicit_offline_first_run_choice_updates_runtime_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detector = DawDiscoveryService([root], platform_name="darwin")
            setup = FirstRunService(root / "first_run.json", detector)
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            config["ai_provider"] = "gemini"
            config["network_mode"] = "full"
            (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
            setup.advance({"ai_mode": "OFF", "network_mode": "OFFLINE"})
            synced = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(synced["ai_provider"], "off")
            self.assertEqual(synced["network_mode"], "offline")

    def test_adapter_state_is_separate_from_host_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Live 12.4.app").mkdir()
            adapter = AdapterInstallation(
                "ABLETON_ADAPTER",
                True,
                "1.8.3",
                ComponentState.DEGRADED,
                ComponentState.READY,
                True,
                True,
                {"READY": 46, "DEGRADED": 1, "NEEDS_REVALIDATION": 2},
                True,
                "fixture-doctor",
            )
            row = DawDiscoveryService([root], {"ABLETON_ADAPTER": adapter}, platform_name="darwin").discover()[0]
            self.assertTrue(row.installed and row.adapter_installed)
            self.assertTrue(row.adapter_evidence_verified)
            self.assertEqual(row.adapter_evidence_source, "fixture-doctor")
            self.assertEqual(row.aggregate_health, ComponentState.DEGRADED)
            self.assertEqual(row.capability_counts["READY"], 46)

    def test_unverified_adapter_claim_cannot_promote_ready_health(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Live 12.4.app").mkdir()
            claimed = AdapterInstallation(
                "ABLETON_ADAPTER",
                True,
                "1.8.3",
                ComponentState.READY,
                ComponentState.READY,
                True,
                False,
                {"READY": 49},
            )
            row = DawDiscoveryService([root], {"ABLETON_ADAPTER": claimed}, platform_name="darwin").discover()[0]
            self.assertTrue(row.installed)
            self.assertFalse(row.adapter_installed)
            self.assertFalse(row.adapter_evidence_verified)
            self.assertEqual(row.aggregate_health, ComponentState.UNAVAILABLE)
            self.assertEqual(row.connection_state, ComponentState.UNAVAILABLE)
            self.assertEqual(row.capability_counts, {})
            self.assertTrue(row.repair_available)


if __name__ == "__main__":
    unittest.main()
