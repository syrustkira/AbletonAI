import tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_recovery import RecoveryEngine,FaultDomain
from n0te_guardian import *
class RecoveryGuardianTests(unittest.TestCase):
 def test_identical_failure_circuit_breaks_and_is_reversible(self):
  with tempfile.TemporaryDirectory() as td:
   e=RecoveryEngine(Path(td),threshold=3)
   for _ in range(3):result=e.record("camera",FaultDomain.CAMERA,"crash-x","boom")
   self.assertTrue(result["circuit_open"]);self.assertFalse(e.available("camera"));self.assertFalse(e.safe_start_plan()["retry_identical_failures"])
   with self.assertRaises(PermissionError):e.clear_quarantine("camera")
   e.clear_quarantine("camera",explicit=True);self.assertTrue(e.available("camera"))
 def test_unknown_transaction_requires_recovery_without_undo(self):
  with tempfile.TemporaryDirectory() as td:
   e=RecoveryEngine(Path(td));e.record("daw",FaultDomain.DAW,"lost","disconnect",transaction_state="UNKNOWN")
   c=e.crash_capsule();self.assertTrue(c["recovery_required"]);self.assertFalse(c["automatic_creative_undo"])
 def test_guardian_preserves_realtime_and_defers_background(self):
  s=WorkScheduler();s.set_sensitive(True)
  self.assertEqual(s.decision(WorkItem("audio",Priority.REALTIME,"audio")),"RUN")
  self.assertEqual(s.decision(WorkItem("render",Priority.BULK,"render")),"DEFER")
  self.assertEqual(s.decision(WorkItem("ui",Priority.INTERACTIVE,"ui")),"RUN")
 def test_battery_profile_throttles_noncritical_work(self):
  s=WorkScheduler(GuardianProfile.TRAVEL_BATTERY);self.assertEqual(s.decision(WorkItem("scan",Priority.BACKGROUND,"indexing")),"THROTTLE")
if __name__=="__main__":unittest.main()
