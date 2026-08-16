import os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"));sys.path.insert(0,str(ROOT/"scripts"))
from n0te_native_platforms import *
from build_linux_appdir import build

class NativePlatformTests(unittest.TestCase):
 def test_linux_desktop_multiple_installations(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for name,version in (("tool-stable","1"),("tool-beta","2")):(root/f"{name}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name}\nExec=/opt/{name}\nX-AppImage-Version={version}\n")
   rows=LinuxApplicationDiscovery([root]).discover();self.assertEqual([x.version for x in rows],["2","1"])
 def test_linux_process_detector_observes_current_process(self):
  name=(Path("/proc/self/comm").read_text().strip());self.assertEqual(LinuxProcessDetector().state([name]),ProcessState.RUNNING);self.assertEqual(LinuxProcessDetector().state(["n0te-definitely-not-running"]),ProcessState.NOT_RUNNING)
 def test_windows_registry_fixture_parsing(self):
  rows=WindowsRegistryDiscovery().parse([{"DisplayName":"Ableton Live 12 Suite","DisplayVersion":"12.1","InstallLocation":"C:/Ableton","RegistryKey":"x","Architecture":"x86_64"},{"DisplayName":"Unrelated"}]);self.assertEqual(len(rows),1);self.assertIn("ABLETON_LIVE:12.1",rows[0].identity)
 def test_linux_appdir_requires_and_contains_private_runtime(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);runtime=root/"runtime";(runtime/"bin").mkdir(parents=True);(runtime/"bin/python3").write_text("#!/bin/sh\necho Python 3.14.4\n");(runtime/"bin/python3").chmod(0o755);(runtime/"LICENSE").write_text("test runtime fixture")
   manifest=build(root/"N0TE.AppDir",runtime);self.assertTrue(manifest["runtime_present"]);self.assertTrue((root/"N0TE.AppDir/AppRun").stat().st_mode&0o111);self.assertIn("usr/runtime/bin/python3",manifest["files"]);self.assertIn("PYTHONHOME",(root/"N0TE.AppDir/AppRun").read_text())
if __name__=="__main__":unittest.main()
