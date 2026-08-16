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
            self.assertIn("uid:-:1:-", registry.quarantine)
            self.assertNotIn("uid:-:2:-", registry.quarantine)
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

    def test_registry_persists_quarantine_mapping_and_reenable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"registry.json";registry=PluginRegistry(path);mapping=SemanticMapping("uid","1","4",{"title":"Attack"},"attack_time","manual",1,binary_hash="hash",class_id="class",verification_status="VERIFIED")
            registry.add_mapping(mapping);registry.quarantine_plugin("uid","1","crash","hash","class")
            loaded=PluginRegistry(path);self.assertEqual(loaded.mappings,[mapping]);self.assertEqual(next(iter(loaded.quarantine.values()))["failure_kind"],"PROCESS_FAILED")
            self.assertEqual(loaded.invalidate_changed_binary("uid","1","new","class"),["4"]);loaded.reenable("uid","1","hash","class");self.assertFalse(PluginRegistry(path).quarantine)

    def test_module_identity_survives_move_and_install_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as first,tempfile.TemporaryDirectory() as second:
            a=Path(first)/"Tool.vst3";b=Path(second)/"Tool.vst3";a.write_bytes(b"same module");b.write_bytes(b"same module")
            left=PluginScanner().scan([first])[0];right=PluginScanner().scan([second])[0]
            self.assertEqual(left.uid,right.uid);self.assertNotEqual(left.install_fingerprint,right.install_fingerprint)

    def test_corrupt_registry_fails_safe_and_preserves_recovery_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"registry.json";path.write_text("{broken")
            registry=PluginRegistry(path);self.assertEqual(registry.recovery,"CORRUPT_STATE_IGNORED");self.assertFalse(registry.quarantine);self.assertTrue(list(Path(tmp).glob("registry.json.corrupt-*")))


if __name__ == "__main__":
    unittest.main()
