import hashlib,json,tempfile,unittest,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_updates import *
from n0te_network import *
class UpdateTests(unittest.TestCase):
 def fixture(self,root,*,host_close=False,restart=False,channel=UpdateChannel.STABLE,component="ABLETON_ADAPTER"):
  data=b"adapter-1.8.4";v=TestOnlyHMACVerifier(b"TEST-ONLY-KEY");item=UpdateComponent(component,"1.8.4","mac","arm64",hashlib.sha256(data).hexdigest(),v.sign(data),"adapter.bin",host_close_required=host_close,restart_required=restart,capabilities_fixed=["automation_write"],capabilities_unchanged=["transport_read","midi_read"])
  m=ReleaseManifest("r1","2.4.1",channel,"2026-01-01","fix", "2.4.0",True,[item]);m.signature=v.sign(manifest_bytes(m));return data,v,m
 def enabled(self):return UpdateSettings(automatic_checking=True,automatic_safe_install=True)
 def test_update_settings_default_fail_closed(self):
  s=UpdateSettings();self.assertFalse(s.automatic_checking);self.assertFalse(s.automatic_safe_install);self.assertEqual(s.channel,UpdateChannel.STABLE)
 def test_offline_pauses_without_fetch_when_checking_explicitly_enabled(self):
  with tempfile.TemporaryDirectory() as td:
   _,v,_=self.fixture(td);called=[];e=UpdateEngine(Path(td),NetworkPolicy(NetworkMode.OFFLINE),v,"mac","arm64",{},settings=self.enabled())
   out=e.check("https://updates.n0te.test/stable",lambda _:called.append(1));self.assertEqual(out["state"],"PAUSED_BY_NETWORK_POLICY");self.assertFalse(called)
 def test_disabled_checking_never_fetches(self):
  with tempfile.TemporaryDirectory() as td:
   _,v,_=self.fixture(td);called=[];e=UpdateEngine(Path(td),NetworkPolicy(NetworkMode.FULL),v,"mac","arm64",{})
   out=e.check("https://updates.n0te.test/stable",lambda _:called.append(1));self.assertTrue(out["disabled"]);self.assertFalse(called)
 def test_channels_require_opt_in(self):
  s=UpdateSettings()
  for channel in ("BETA","DEVELOPER"):
   with self.assertRaises(PermissionError):s.select_channel(channel)
   s.select_channel(channel,explicit=True);self.assertEqual(s.channel.value,channel)
 def test_component_only_plan_and_pending_host_close(self):
  with tempfile.TemporaryDirectory() as td:
   data,v,m=self.fixture(td,host_close=True);e=UpdateEngine(Path(td),NetworkPolicy(NetworkMode.FULL),v,"mac","arm64",{"CORE":"2.4.0","ABLETON_ADAPTER":"1.8.3"},settings=self.enabled(),song_id="song")
   e.check("https://updates.n0te.test/stable",lambda _:m);self.assertEqual([x.component_id for x in e.plan],["ABLETON_ADAPTER"]);out=e.stage({"adapter.bin":data});self.assertEqual(out["state"],"PENDING_HOST_CLOSE");self.assertEqual(e.song_id,"song")
   self.assertEqual(e.install(hosts_open=True)["state"],"PENDING_HOST_CLOSE");self.assertEqual(e.install(hosts_open=False)["state"],"UPDATED");self.assertEqual(e.policies,{})
 def test_hash_signature_platform_architecture_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   data,v,m=self.fixture(td);e=UpdateEngine(Path(td),NetworkPolicy(),v,"mac","arm64",{"CORE":"2.4.0"},settings=self.enabled())
   bad=ReleaseManifest(**{**m.__dict__,"signature":"bad"})
   with self.assertRaises(PermissionError):e.validate_manifest(bad)
   e.validate_manifest(m);e.manifest=m;e.plan=e.build_plan(m)
   with self.assertRaises(ValueError):e.stage({"adapter.bin":b"bad"})
   for key,value in (("platform","win"),("architecture","x64")):
    old=getattr(m.components[0],key);setattr(m.components[0],key,value);m.signature=v.sign(manifest_bytes(m))
    with self.assertRaises(ValueError):e.validate_manifest(m)
    setattr(m.components[0],key,old);m.signature=v.sign(manifest_bytes(m))
 def test_non_rollback_compatible_release_is_not_eligible_for_transactional_install(self):
  with tempfile.TemporaryDirectory() as td:
   _,v,m=self.fixture(td);m.rollback_compatible=False;m.signature=v.sign(manifest_bytes(m));e=UpdateEngine(Path(td),NetworkPolicy(NetworkMode.FULL),v,"mac","arm64",{"CORE":"2.4.0"},settings=self.enabled())
   with self.assertRaisesRegex(ValueError,"not rollback-compatible"):e.validate_manifest(m)
   self.assertFalse((Path(td)/"rollback.json").exists())
 def test_offline_import_and_rollback_preserve_identity_and_policy(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);data,v,m=self.fixture(td);package=root/"N0TE-Update-2.4.1.n0teupdate"
   raw=asdict(m);raw["channel"]=m.channel.value
   with zipfile.ZipFile(package,"w") as z:z.writestr("release.json",json.dumps(raw));z.writestr("payloads/adapter.bin",data)
   policies={"ai":"OFF","network":"OFFLINE","community":"OFF","privacy":"PRIVATE"};e=UpdateEngine(root/"state",NetworkPolicy(NetworkMode.OFFLINE),v,"mac","arm64",{"CORE":"2.4.0","ABLETON_ADAPTER":"1.8.3"},settings=self.enabled(),policies=policies,song_id="song")
   self.assertEqual(e.import_offline(package)["state"],"READY_TO_INSTALL");e.install();self.assertEqual(e.current["ABLETON_ADAPTER"],"1.8.4");e.rollback();self.assertEqual(e.current["ABLETON_ADAPTER"],"1.8.3");self.assertEqual(e.policies,policies);self.assertEqual(e.song_id,"song")
 def test_migration_and_dependencies_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   _,v,m=self.fixture(td);m.components[0].migration_version="arbitrary-code";m.signature=v.sign(manifest_bytes(m));e=UpdateEngine(Path(td),NetworkPolicy(),v,"mac","arm64",{"CORE":"2.4.0"},settings=self.enabled())
   with self.assertRaises(ValueError):e.validate_manifest(m)
   m.components[0].migration_version="2";m.components[0].dependencies=["CREATOR"];m.signature=v.sign(manifest_bytes(m));e.supported_migrations.add("2");e.validate_manifest(m)
   with self.assertRaises(ValueError):e.build_plan(m)
if __name__=="__main__":unittest.main()
