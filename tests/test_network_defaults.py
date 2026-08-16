import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_network import NetworkMode, NetworkPolicy


class NetworkDefaultTests(unittest.TestCase):
    def test_network_policy_defaults_fail_closed(self):
        self.assertEqual(NetworkPolicy().mode, NetworkMode.OFFLINE)
        self.assertEqual(NetworkPolicy.from_value(None).mode, NetworkMode.OFFLINE)
        self.assertFalse(NetworkPolicy().decide("https://api.openai.com/v1").allowed)
        self.assertTrue(NetworkPolicy().decide("http://127.0.0.1:8766").allowed)


if __name__ == "__main__":
    unittest.main()
