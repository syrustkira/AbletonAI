import tempfile,unittest,hashlib
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_distribution import *
class DistributionTests(unittest.TestCase):
 def fixture(self,root):
  src=root/"src";src.mkdir();(src/"core.py").write_text("core");f=PayloadFile("core.py","app/core.py",hashlib.sha256((src/"core.py").read_bytes()).hexdigest());return src,[DistributionComponent("CORE","1",["mac","win"],["arm64","x64"],[f])]
 def test_standard_ai_off_no_obs_camera_stages_and_installs(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src,cs=self.fixture(r);stage=r/"stage";m=DistributionBuilder(src).stage(stage,cs,Profile.STANDARD);self.assertEqual(m["profile"],"STANDARD")
   tx=InstallTransaction(stage,r/"install",r/"state");tx.state.mkdir();tx.install(["CORE"],"mac","arm64");self.assertEqual(tx.verify(),[])
 def test_hash_missing_platform_and_license_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src,cs=self.fixture(r);cs[0].files[0].sha256="bad"
   with self.assertRaises(ValueError):DistributionBuilder(src).stage(r/"s",cs,Profile.STANDARD)
   cs[0].files[0].sha256=hashlib.sha256((src/"core.py").read_bytes()).hexdigest();cs[0].redistribution_status="unknown"
   with self.assertRaises(PermissionError):DistributionBuilder(src).stage(r/"s",cs,Profile.STANDARD)
 def test_repair_and_uninstall_preserve_user_data(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src,cs=self.fixture(r);stage=r/"s";DistributionBuilder(src).stage(stage,cs,Profile.FULL_OFFLINE);state=r/"state";state.mkdir();tx=InstallTransaction(stage,r/"i",state);tx.install(["CORE"],"win","x64");(r/"i/app/core.py").write_text("broken");self.assertTrue(tx.repair()["repaired"]);self.assertTrue(tx.uninstall()["user_data_preserved"])
if __name__=="__main__":unittest.main()
