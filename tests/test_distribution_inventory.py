import hashlib,tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_distribution import *
class InventoryTests(unittest.TestCase):
 def test_third_party_unknown_redistribution_fails(self):
  with self.assertRaises(PermissionError):validate_third_party_inventory([ThirdPartyComponent("mystery","1","?","unknown","unknown","")])
  self.assertTrue(validate_third_party_inventory([ThirdPartyComponent("bridge","1","GPL-3.0","project","approved","LICENSE.txt")]))
 def test_private_runtime_must_be_present_and_verified(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);runtime=PrivateRuntimeManifest("3.14","mac","arm64","python.tar.zst","bad","approved")
   with self.assertRaises(FileNotFoundError):validate_private_runtime(runtime,root)
   (root/runtime.payload_path).write_bytes(b"runtime");runtime=PrivateRuntimeManifest("3.14","mac","arm64",runtime.payload_path,hashlib.sha256(b"runtime").hexdigest(),"approved");self.assertTrue(validate_private_runtime(runtime,root))
if __name__=="__main__":unittest.main()
