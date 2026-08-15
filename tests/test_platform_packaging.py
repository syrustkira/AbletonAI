import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"app"))
from n0te_platform import *
from n0te_packaging import *
class Adapter:
 tier=IntegrationTier.DEEP
 def validate_action(self,a):return True,""
 def execute_action(self,a,auth):return {"ok":True}
class PlatformPackagingTests(unittest.TestCase):
 def test_audio_graph_enforces_format_direction_and_realtime_contract(self):
  g=AudioGraph();f=AudioFormat(48000,2);g.add_node(AudioNode("a",AudioKind.DAW_TAP,"SOURCE",f,"daw"));g.add_node(AudioNode("b",AudioKind.LOCAL_RECORDER,"SINK",f,"daw"));g.add_route(AudioRoute("r","a","b"));self.assertTrue(all(g.realtime_contract("r").values()))
  with self.assertRaises(ValueError):g.add_route(AudioRoute("bad","a","missing"))
 def test_plugin_negotiation_preserves_song_and_rejects_major(self):
  s=PluginSession(ProtocolVersion(1,2),{"tap","transport"});self.assertEqual(s.negotiate(PluginHandshake(ProtocolVersion(1,0),{"tap"},"song","ws")),{"tap"})
  with self.assertRaises(PermissionError):s.reconnect(PluginHandshake(ProtocolVersion(1,1),{"tap"},"other","ws"))
  self.assertEqual(PluginSession(ProtocolVersion(1,0),set()).negotiate(PluginHandshake(ProtocolVersion(2,0),set(),"s","w")),set())
 def test_daw_mutation_contract_requires_gate1(self):
  with self.assertRaises(PermissionError):execute_authorized(Adapter(),{},None)
  self.assertTrue(execute_authorized(Adapter(),{}, {"approved":True,"revalidated":True})["ok"])
 def test_every_supported_host_targets_deep_without_fake_current_support(self):
  fixtures=[HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,available_capabilities={"clips_read"},host_extensions={"SessionClip"}),HostAdapterDescriptor("Logic",IntegrationTier.DETECTED_UNSUPPORTED),HostAdapterDescriptor("FL Studio",IntegrationTier.DETECTED_UNSUPPORTED),HostAdapterDescriptor("Pro Tools",IntegrationTier.DETECTED_UNSUPPORTED)]
  self.assertTrue(all(x.target_tier is IntegrationTier.DEEP for x in fixtures));self.assertEqual(fixtures[1].tier,IntegrationTier.DETECTED_UNSUPPORTED);self.assertIn("SessionClip",fixtures[0].status()["host_extensions"])
 def test_deep_failure_degrades_capability_not_song_identity(self):
  x=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,available_capabilities={"transport_read"},healthy=False)
  self.assertEqual(x.effective_tier(),IntegrationTier.ENHANCED);self.assertEqual(x.target_tier,IntegrationTier.DEEP)
 def test_packaging_dependencies_in_use_and_rollback(self):
  core=ComponentManifest(Component.CORE,"1",{"mac"},{"arm64"},rollback_source="old")
  plugin=ComponentManifest(Component.VST3,"1",{"mac"},{"arm64"},{Component.CORE},rollback_source="old")
  p=PackagingPlanner([core,plugin]);self.assertEqual(p.install([Component.VST3],"mac","arm64")["components"],["CORE","VST3"]);self.assertTrue(p.uninstall([Component.CORE])["preserve_user_data"])
  plugin.in_use=True
  with self.assertRaises(RuntimeError):p.update([Component.VST3])
if __name__=="__main__":unittest.main()
