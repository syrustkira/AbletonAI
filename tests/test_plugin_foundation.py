import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from n0te_plugins import PluginRegistry, PluginScanner, PluginScanProcess, SemanticMapping, mapping_valid_for, candidate_mapping


class PluginFoundationTests(unittest.TestCase):
    def test_scanner_recognizes_formats_without_loading_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("Safe.vst3", "Unit.component", "Open.clap", "Pro.aaxplugin"):
                (root / name).write_bytes(b"fixture metadata")
            rows = PluginScanner().scan([root])
            self.assertEqual({row.format for row in rows}, {"VST3", "AU", "CLAP", "AAX"})
            self.assertTrue(all(row.hostability == "NATIVE_HOST_REQUIRED" for row in rows))

    def test_scanning_is_process_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Safe.vst3").write_bytes(b"fixture")
            result = PluginScanProcess().scan([tmp])
            self.assertEqual(result["state"], "READY")
            self.assertEqual(result["plugins"][0]["format"], "VST3")

    def test_quarantine_is_plugin_version_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = PluginRegistry(Path(tmp) / "registry.json")
            registry.quarantine_plugin("uid", "1", "scan crashed")
            self.assertIn("uid:1", registry.quarantine)
            self.assertNotIn("uid:2", registry.quarantine)
            registry.reenable("uid", "1")
            self.assertFalse(registry.quarantine)

    def test_semantics_do_not_cross_versions(self):
        mapping = SemanticMapping("uid", "1", "421", {"name": "Depth"}, "transient_depth", "manual fixture", 1)
        self.assertTrue(mapping_valid_for(mapping, "uid", "1"))
        self.assertFalse(mapping_valid_for(mapping, "uid", "2"))

    def test_candidate_mapping_never_becomes_verified_automation(self):
        plugin = PluginScanner().scan([])
        from n0te_plugins import PluginDescriptor
        candidate = candidate_mapping(PluginDescriptor("uid", "tool", "VST3", "/fixture", "1", sha256="abc"), {"id": 4, "title": "Attack", "units": "ms"})
        self.assertEqual(candidate.semantic, "attack_time")
        self.assertEqual(candidate.verification_status, "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
