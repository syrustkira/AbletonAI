import tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_daw_discovery import *
from n0te_setup import *
class DawSetupTests(unittest.TestCase):
 def test_multiple_daws_and_versions_remain_distinct(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);[ (root/name).mkdir() for name in ("Live 12.3.app","Live 12.4 Beta.app","Logic Pro.app","Pro Tools 2025.app") ]
   service=DawDiscoveryService([root],platform_name="darwin",architecture="arm64");rows=service.discover()
   self.assertEqual(len(rows),4);ableton=[x for x in rows if x.host_family is HostFamily.ABLETON_LIVE];self.assertEqual(len(ableton),2);self.assertNotEqual(ableton[0].installation_id,ableton[1].installation_id)
   logic=next(x for x in rows if x.host_family is HostFamily.LOGIC_PRO);self.assertEqual(logic.implementation_maturity,IntegrationTier.DETECTED_UNSUPPORTED);self.assertEqual(logic.target_maturity,IntegrationTier.DEEP)
   self.assertTrue(all(not hasattr(x,"song_id") for x in rows))
 def test_missing_hosts_are_truthful_healthy_setup_states(self):
  with tempfile.TemporaryDirectory() as td:
   rows=DawDiscoveryService([Path(td)],platform_name="darwin").discover(include_missing=True)
   self.assertEqual({x.host_family for x in rows},set(HostFamily));self.assertTrue(all(not x.installed for x in rows));self.assertTrue(all(x.target_maturity is IntegrationTier.DEEP for x in rows))
 def test_first_run_and_runtime_share_detector_and_optional_offline_finishes(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);detector=DawDiscoveryService([root],platform_name="darwin");setup=FirstRunService(root/"setup.json",detector)
   self.assertEqual(setup.detect_daws(),[x.status() for x in detector.discover(include_missing=True)])
   while not setup.state.complete:setup.advance({"ai_mode":"OFF","network_mode":"OFFLINE","obs_enabled":False,"camera_enabled":False,"local_ai_enabled":False})
   self.assertTrue(setup.status()["healthy"]);self.assertEqual(setup.status()["step"],"READY")
   restored=FirstRunService(root/"setup.json",detector);self.assertTrue(restored.status()["complete"]);self.assertEqual(restored.status()["network_mode"],"OFFLINE")
 def test_adapter_state_is_separate_from_host_detection(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/"Live 12.4.app").mkdir();adapter=AdapterInstallation("ABLETON_ADAPTER",True,"1.8.3",ComponentState.DEGRADED,ComponentState.READY,True,True,{"READY":46,"DEGRADED":1,"NEEDS_REVALIDATION":2})
   row=DawDiscoveryService([root],{"ABLETON_ADAPTER":adapter},platform_name="darwin").discover()[0]
   self.assertTrue(row.installed and row.adapter_installed);self.assertEqual(row.aggregate_health,ComponentState.DEGRADED);self.assertEqual(row.capability_counts["READY"],46)
if __name__=="__main__":unittest.main()
