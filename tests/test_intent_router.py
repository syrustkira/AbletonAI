import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_intent import ExecutionTier, IntentRouter
import n0te_server as server

SNAP = {"set": {"set_signature": "sig", "tracks": [{"id": 10, "index": 2, "name": "Bass"}]},
        "song": {"id": 1, "properties": {}}, "selected_track_summary": {"id": 10, "index": 2, "name": "Bass"},
        "selected_device": {"id": 9, "name": "Utility"}, "selected_clip_notes": {"notes": [{"pitch": 60}]}}


class IntentRouterTests(unittest.TestCase):
    def setUp(self): self.router = IntentRouter()

    def test_information_routes_are_deterministic(self):
        self.assertIn("Bass", self.router.route("what is the selected track", SNAP).message)
        self.assertIn("1 exposed", self.router.route("inspect selected midi notes", SNAP).message)
        self.assertEqual(self.router.route("status", SNAP).tier, ExecutionTier.INFORMATION_ONLY)

    def test_explicit_mutations_become_approval_gated_actions(self):
        cases = {
            "set tempo to 128 bpm": ("set_tempo", 0),
            "rename selected track to Sub Bass": ("rename_track", 2),
            "mute selected track": ("set_track_mute", 2),
            "disarm selected track": ("set_track_arm", 2),
        }
        for command, (kind, index) in cases.items():
            with self.subTest(command=command):
                plan = self.router.route(command, SNAP)
                self.assertEqual(plan.tier, ExecutionTier.APPROVAL_GATED)
                self.assertEqual(plan.actions[0]["kind"], kind)
                self.assertEqual(plan.actions[0]["track_index"], index)

    def test_ambiguity_and_unsupported_routing_fail_to_guided_manual(self):
        ambiguous = self.router.route("make it better", SNAP)
        self.assertEqual(ambiguous.tier, ExecutionTier.GUIDED_MANUAL)
        self.assertTrue(ambiguous.choices)
        routing = self.router.route("route this sidechain to the bass", SNAP)
        self.assertEqual(routing.tier, ExecutionTier.GUIDED_MANUAL)
        self.assertIn("does not expose", routing.manual.reason)

    def test_undo_text_does_not_bypass_explicit_undo_authority(self):
        plan = self.router.route("undo N0TE", SNAP)
        self.assertEqual(plan.actions, [])
        self.assertEqual(plan.tier, ExecutionTier.GUIDED_MANUAL)

    def test_server_ai_off_reply_never_invokes_provider(self):
        with patch.object(server.projects, "load_song", return_value={}), patch.object(server, "ask_openai") as provider:
            reply = server.deterministic_reply("rename selected track to Low End", SNAP)
        provider.assert_not_called()
        self.assertEqual(reply["actions"][0]["kind"], "rename_track")
        self.assertEqual(reply["execution_plan"]["tier"], "APPROVAL_GATED")


if __name__ == "__main__": unittest.main()
