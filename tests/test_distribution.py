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
 def test_uninstall_restores_file_displaced_by_install(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src,cs=self.fixture(r);stage=r/"s";DistributionBuilder(src).stage(stage,cs,Profile.STANDARD);state=r/"state";state.mkdir();destination=r/"install";(destination/"app").mkdir(parents=True);target=destination/"app/core.py";target.write_text("pre-n0te")
   tx=InstallTransaction(stage,destination,state);tx.install(["CORE"],"mac","arm64");self.assertEqual(target.read_text(),"core");result=tx.uninstall();self.assertEqual(target.read_text(),"pre-n0te");self.assertTrue(result["previous_files_restored"])
 def test_distribution_paths_cannot_escape_source_stage_or_destination(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src,cs=self.fixture(r);digest=cs[0].files[0].sha256
   cs[0].files[0]=PayloadFile("../outside.py","app/core.py",digest)
   with self.assertRaises(ValueError):DistributionBuilder(src).stage(r/"stage-source",cs,Profile.STANDARD)
   cs[0].files[0]=PayloadFile("core.py","../escape.py",digest)
   with self.assertRaises(ValueError):DistributionBuilder(src).stage(r/"stage-destination",cs,Profile.STANDARD)
if __name__=="__main__":unittest.main()
