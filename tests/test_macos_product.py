from __future__ import annotations
import hashlib,json,os,plistlib,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from n0te_acceptance import *
from n0te_app_health import startup_health
from n0te_daw_discovery import DawDiscoveryService,HostFamily
from n0te_instance import AlreadyRunningError,SingleInstance
from n0te_macos import *
from n0te_paths import *
from n0te_updates import prepare_macos_handoff
class MacOSProductTests(unittest.TestCase):
 def app(self,root,name,bundle_id,version):
  app=root/(name+'.app');info=app/'Contents/Info.plist';info.parent.mkdir(parents=True);info.write_bytes(plistlib.dumps({'CFBundleIdentifier':bundle_id,'CFBundleName':name,'CFBundleShortVersionString':version}));return app
 def test_macos_metadata_discovery_and_multiple_versions(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);self.app(root,'Live 12.3','com.ableton.live','12.3');self.app(root,'Live 12.4 Beta','com.ableton.live.beta','12.4b');self.app(root,'Logic Pro','com.apple.logic10','11.1');self.app(root,'Unrelated','example.other','1')
   backend=MacOSApplicationDiscovery([root]);rows=backend.applications();self.assertEqual(len(rows),3);self.assertEqual(sum(x[0] is HostFamily.ABLETON_LIVE for x in rows),2)
   discovered=DawDiscoveryService([root],platform_name='darwin',metadata_backend=backend).discover();self.assertEqual(len(discovered),3);self.assertEqual({x.detected_version for x in discovered if x.host_family is HostFamily.ABLETON_LIVE},{'12.3','12.4b'})
 def test_host_running_detection_is_safe_and_never_terminates(self):
  app=MacApplicationMetadata(Path('/Applications/Live.app'),'com.ableton.live','Live','12')
  self.assertEqual(MacOSHostProcessDetector(lambda:'/Applications/Live.app/Contents/MacOS/Live\n').state(app),HostRunState.RUNNING)
  self.assertEqual(MacOSHostProcessDetector(lambda:'').state(app),HostRunState.NOT_RUNNING)
  self.assertEqual(MacOSHostProcessDetector(lambda:(_ for _ in ()).throw(OSError())).state(app),HostRunState.UNKNOWN)
 def test_platform_paths_separate_bundle_data_logs_cache_and_recovery(self):
  with tempfile.TemporaryDirectory() as td:
   p=product_paths(Path(td),'darwin').ensure();self.assertIn('Application Support/N0TE',str(p.data));self.assertIn('Library/Logs/N0TE',str(p.logs));self.assertNotEqual(p.cache,p.data);self.assertTrue(p.recovery.is_dir())
 def test_single_instance_refuses_duplicate_without_killing(self):
  with tempfile.TemporaryDirectory() as td:
   first=SingleInstance(Path(td)/'lock').acquire()
   try:
    with self.assertRaises(AlreadyRunningError):SingleInstance(Path(td)/'lock').acquire()
   finally:first.release()
 def test_bundle_builder_info_plist_layout_dmg_and_notices(self):
  with tempfile.TemporaryDirectory() as td:
   out=Path(td)/'out';subprocess.run([sys.executable,str(ROOT/'scripts/build_macos_app.py'),'--output',str(out),'--allow-missing-runtime'],check=True,capture_output=True)
   app=out/'N0TE Development.app';self.assertTrue((app/'Contents/MacOS/N0TE').is_file());self.assertTrue(os.access(app/'Contents/MacOS/N0TE',os.X_OK));plist=plistlib.loads((app/'Contents/Info.plist').read_bytes());self.assertEqual(plist['CFBundleIdentifier'],'app.n0te.N0TE')
   classification=json.loads((app/'Contents/Resources/BUILD_CLASSIFICATION.json').read_text());self.assertFalse(classification['signed']);self.assertFalse(classification['notarized']);self.assertTrue(classification['development_build']);self.assertFalse(classification['consumer_ready'])
   self.assertTrue((out/'dmg-root/Applications').is_symlink());self.assertTrue((out/'dmg-root/THIRD_PARTY_COMPONENTS.json').is_file());self.assertTrue((app/'Contents/Resources/app/context/ableton-live-mcp-LICENSE.txt').is_file())
   self.assertTrue((app/'Contents/Resources/Acceptance/REAL_ABLETON_ACCEPTANCE.md').is_file());self.assertTrue((app/'Contents/Resources/tools/macos_update_helper.py').is_file())
 def test_private_runtime_ingestion_and_dependency_manifest(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);runtime=root/'runtime';exe=runtime/'bin/python3';exe.parent.mkdir(parents=True);exe.write_bytes(b'fixture-runtime');exe.chmod(0o755);out=root/'out';subprocess.run([sys.executable,str(ROOT/'scripts/build_macos_app.py'),'--output',str(out),'--runtime-root',str(runtime)],check=True,capture_output=True)
   self.assertEqual((out/'N0TE Development.app/Contents/Frameworks/Python/bin/python3').read_bytes(),b'fixture-runtime');deps=json.loads((ROOT/'packaging/RUNTIME_DEPENDENCIES.json').read_text());self.assertEqual(deps['external_python_packages_required'],[]);self.assertIn('REQUIRED_RUNTIME',{x['classification'] for x in deps['dependencies']})
 def test_health_keeps_optional_absence_healthy_but_requires_runtime(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bundle=root/'N0TE.app';(bundle/'Contents/Resources/app').mkdir(parents=True);(bundle/'Contents/Resources/app/n0te_server.py').write_text('');p=product_paths(root,'darwin').ensure();health=startup_health(bundle,p);self.assertFalse(health['healthy']);self.assertEqual(health['checks']['obs']['state'],'OPTIONAL_NOT_INSTALLED')
   runtime=bundle/'Contents/Frameworks/Python/bin/python3';runtime.parent.mkdir(parents=True);runtime.write_text('');self.assertTrue(startup_health(bundle,p)['healthy'])
 def test_update_handoff_and_capability_acceptance_are_scoped(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);current=root/'N0TE.app';staged=root/'Staged.app';backup=root/'Backup.app';(staged/'Contents').mkdir(parents=True);(staged/'Contents/file').write_bytes(b'x');handoff=prepare_macos_handoff(root/'handoff.json',current,staged,backup,123)
   self.assertTrue(handoff['creative_state_untouched']);self.assertIn('Contents/file',handoff['bundle_hashes'])
   store=CapabilityAcceptanceStore(root/'acceptance.json');store.record(host='Ableton Live',host_version='12',adapter_version='1',platform='macOS',architecture='arm64',capability='transport_read',operation_risk='READ',result='PASS',compatibility_state='VERIFIED',evidence_source='real-host observation');self.assertEqual(store.load()[0]['capability'],'transport_read')
if __name__=='__main__':unittest.main()
