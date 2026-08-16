import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from n0te_paths import product_paths
from n0te_platform import AudioFormat, AudioGraph, AudioKind, AudioNode, AudioRoute


class PlatformParityTests(unittest.TestCase):
    def test_linux_uses_xdg_locations(self):
        paths = product_paths(Path("/home/test"), "Linux", {
            "XDG_DATA_HOME": "/data", "XDG_CACHE_HOME": "/cache", "XDG_STATE_HOME": "/state"
        })
        self.assertEqual(paths.data, Path("/data/n0te"))
        self.assertEqual(paths.logs, Path("/state/n0te/logs"))
        self.assertEqual(paths.cache, Path("/cache/n0te"))

    def test_windows_separates_roaming_data_from_local_cache(self):
        paths = product_paths(Path("C:/Users/Test"), "Windows", {
            "APPDATA": "C:/Roaming", "LOCALAPPDATA": "C:/Local"
        })
        self.assertEqual(paths.data, Path("C:/Roaming/N0TE"))
        self.assertEqual(paths.cache, Path("C:/Local/N0TE/Cache"))

    def test_audio_routes_reject_feedback_cycles_and_model_latency(self):
        graph = AudioGraph(); fmt = AudioFormat(48000, 2)
        graph.add_node(AudioNode("a", AudioKind.DAW_TAP, "BOTH", fmt, "host"))
        graph.add_node(AudioNode("b", AudioKind.ANALYSIS, "BOTH", fmt, "host"))
        graph.add_route(AudioRoute("forward", "a", "b"))
        with self.assertRaisesRegex(ValueError, "feedback cycle"):
            graph.add_route(AudioRoute("feedback", "b", "a"))
        latency = graph.latency("forward", buffer_frames=128, plugin_frames=64)
        self.assertEqual(latency["total_frames"], 192)
        self.assertAlmostEqual(latency["total_ms"], 4)
        self.assertFalse(latency["measured"])


if __name__ == "__main__":
    unittest.main()
