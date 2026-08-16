import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from n0te_audio import AudioBuffer, analyze, closed_loop_peak, diagnose, masking


class AudioIntelligenceTests(unittest.TestCase):
    def tone(self, frequency=1000, amplitude=.5, right_phase=0):
        rate = 8000
        left = tuple(amplitude * math.sin(2 * math.pi * frequency * i / rate) for i in range(rate))
        right = tuple(amplitude * math.sin(2 * math.pi * frequency * i / rate + right_phase) for i in range(rate))
        return AudioBuffer(rate, (left, right), "fixture")

    def test_measurements_are_deterministic_and_source_scoped(self):
        report = analyze(self.tone())
        self.assertAlmostEqual(report["levels"]["sample_peak"], .5, places=6)
        self.assertAlmostEqual(report["stereo"]["correlation"], 1, places=6)
        self.assertEqual(report["source"], "fixture")
        self.assertIn("K-weighting/gating not applied", report["levels"]["loudness_standard"])

    def test_phase_and_clipping_diagnoses_separate_interpretation(self):
        report = analyze(self.tone(amplitude=1, right_phase=math.pi))
        codes = {item["code"] for item in diagnose(report)}
        self.assertEqual(codes, {"CLIPPING", "PHASE_RISK"})

    def test_pairwise_masking_is_not_instrument_specific(self):
        same = masking(self.tone(400), self.tone(400))
        different = masking(self.tone(100), self.tone(2500))
        self.assertGreater(same["maximum_overlap"], different["maximum_overlap"])

    def test_closed_loop_creates_preview_without_applying(self):
        result = closed_loop_peak(self.tone(amplitude=.9), -6)
        self.assertTrue(result["improved"])
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["applied"])


if __name__ == "__main__":
    unittest.main()
