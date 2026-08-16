import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_tool_profiles import CapabilityEvidence, ParameterMapping, ToolProfile, ToolProfileStore


class ToolProfileTests(unittest.TestCase):
    def test_marketing_name_does_not_create_automation_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            store = ToolProfileStore(Path(td))
            store.save(ToolProfile("stereo-magic", "Stereo Magic", capabilities={"width": "DECLARED"}))
            self.assertIsNone(store.automation_mapping("stereo-magic", "stereo_width"))

    def test_unknown_and_documented_mapping_fall_back_from_automation(self):
        for evidence in (CapabilityEvidence.UNKNOWN, CapabilityEvidence.DECLARED, CapabilityEvidence.DOCUMENTED,
                         CapabilityEvidence.OBSERVED):
            self.assertFalse(ParameterMapping("width", "Width", evidence).safe_for_automation)

    def test_characterized_mapping_round_trips_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            store = ToolProfileStore(Path(td))
            store.save(ToolProfile("utility", "Utility", vendor="Ableton", version="12", formats=["native"],
                                   hosts=["ableton"], parameters=["Width"], mappings=[ParameterMapping(
                                       "stereo_width", "Width", CapabilityEvidence.CHARACTERIZED, "local characterization")]))
            profile = store.get("utility")
            self.assertEqual(profile.vendor, "Ableton")
            self.assertEqual(store.automation_mapping("utility", "stereo_width").parameter, "Width")


if __name__ == "__main__": unittest.main()
