import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_safety import SafetyController
import n0te_server as server


class SafetyTests(unittest.TestCase):
    def test_safe_persists_authority_freeze_without_undo(self):
        with tempfile.TemporaryDirectory() as td:
            controller = SafetyController(Path(td))
            state = controller.enter("panic button")
            self.assertFalse(state["mutation_authority"])
            self.assertFalse(state["remote_authority"])
            self.assertTrue(SafetyController(Path(td)).status()["safe"])
            with self.assertRaises(PermissionError): controller.require_mutation_authority()

    def test_leaving_safe_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            controller = SafetyController(Path(td)); controller.enter()
            with self.assertRaises(PermissionError): controller.leave()
            self.assertTrue(controller.leave(explicit_user_confirmation=True)["mutation_authority"])

    def test_apply_authority_is_revoked_before_proposal_lookup_or_live_access(self):
        with patch.object(server.safety, "require_mutation_authority", side_effect=PermissionError("SAFE")), \
                patch.object(server, "get_snapshot") as live:
            with self.assertRaises(PermissionError): server.apply_proposal("anything")
        live.assert_not_called()


if __name__ == "__main__": unittest.main()
