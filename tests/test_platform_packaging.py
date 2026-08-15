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
  verified=HostCapabilityDescriptor("midi_modify",True,IntegrationTier.DEEP,ComponentState.READY,"ableton")
  with self.assertRaises(PermissionError):execute_authorized(Adapter(),{},None,verified)
  with self.assertRaises(PermissionError):execute_authorized(Adapter(),{}, {"approved":True,"revalidated":True})
  self.assertTrue(execute_authorized(Adapter(),{}, {"approved":True,"revalidated":True},verified)["ok"])
 def test_assumed_reads_are_eligible_but_mutations_are_not(self):
  assumed=HostCapabilityDescriptor("cap",True,IntegrationTier.DEEP,ComponentState.READY,"ableton",compatibility=CompatibilityState.ASSUMED_COMPATIBLE)
  adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities={"cap":assumed})
  self.assertIsNotNone(adapter.resolve("cap",OperationRisk.READ));self.assertIsNotNone(adapter.resolve("cap",OperationRisk.OBSERVE));self.assertIsNone(adapter.resolve("cap",OperationRisk.MUTATE))
  self.assertEqual(resolve_job_capabilities([adapter],[CapabilityRequirement("cap",OperationRisk.MUTATE)])[0]["method"],"GUIDED_MANUAL")
 def test_mutation_prefers_verified_fallback_over_assumed_deep(self):
  assumed=HostCapabilityDescriptor("automation_write",True,IntegrationTier.DEEP,ComponentState.READY,"ableton",compatibility=CompatibilityState.ASSUMED_COMPATIBLE)
  verified=HostCapabilityDescriptor("automation_write",True,IntegrationTier.GENERIC,ComponentState.READY,"bridge",compatibility=CompatibilityState.VERIFIED)
  plan=resolve_job_capabilities([HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities={"automation_write":assumed}),HostAdapterDescriptor("Bridge",IntegrationTier.GENERIC,capabilities={"automation_write":verified})],[CapabilityRequirement("automation_write",OperationRisk.MUTATE)])
  self.assertEqual(plan[0]["implementation"],"bridge");self.assertTrue(plan[0]["requires_gate1"])
 def test_only_explicit_nonmutating_probe_can_verify_mutation(self):
  assumed=HostCapabilityDescriptor("automation_write",True,IntegrationTier.DEEP,ComponentState.READY,"ableton",compatibility=CompatibilityState.ASSUMED_COMPATIBLE)
  adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities={"automation_write":assumed})
  def unsafe(_):return True,"bad",1
  with self.assertRaises(PermissionError):resolve_job_capabilities([adapter],[CapabilityRequirement("automation_write",OperationRisk.MUTATE)],{"automation_write":unsafe})
  def safe(_):return True,"read-only protocol probe",2
  safe.non_mutating=True
  plan=resolve_job_capabilities([adapter],[CapabilityRequirement("automation_write",OperationRisk.MUTATE)],{"automation_write":safe})
  self.assertEqual(plan[0]["method"],"AUTOMATIC");self.assertEqual(assumed.compatibility,CompatibilityState.VERIFIED)
 def test_every_supported_host_targets_deep_without_fake_current_support(self):
  fixtures=[HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,host_extensions={"SessionClip"}),HostAdapterDescriptor("Logic",IntegrationTier.DETECTED_UNSUPPORTED),HostAdapterDescriptor("FL Studio",IntegrationTier.DETECTED_UNSUPPORTED),HostAdapterDescriptor("Pro Tools",IntegrationTier.DETECTED_UNSUPPORTED)]
  self.assertTrue(all(x.target_maturity is IntegrationTier.DEEP for x in fixtures));self.assertEqual(fixtures[1].implementation_maturity,IntegrationTier.DETECTED_UNSUPPORTED);self.assertIn("SessionClip",fixtures[0].status()["host_extensions"])
 def test_deep_capability_failure_does_not_downgrade_siblings_or_maturity(self):
  caps={x:HostCapabilityDescriptor(x,True,IntegrationTier.DEEP,ComponentState.READY,"ableton") for x in ("transport_read","automation_read","automation_write","midi_read","midi_modify","routing_read","routing_set")}
  x=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=caps,song_id="song",workspace_id="ws")
  x.mark_state("automation_write",ComponentState.DEGRADED,"endpoint fault")
  self.assertEqual(x.implementation_maturity,IntegrationTier.DEEP);self.assertEqual(x.overall_health,ComponentState.DEGRADED)
  self.assertIsNotNone(x.resolve("automation_read"));self.assertIsNotNone(x.resolve("midi_read"));self.assertIsNotNone(x.resolve("routing_read"));self.assertIsNone(x.resolve("automation_write"))
  self.assertEqual((x.song_id,x.workspace_id),("song","ws"))
  x.mark_state("automation_write",ComponentState.READY);self.assertIsNotNone(x.resolve("automation_write"));self.assertEqual(x.overall_health,ComponentState.READY)
 def test_job_combines_healthy_automatic_and_failed_guided_manual(self):
  caps={"track_read":HostCapabilityDescriptor("track_read",True,IntegrationTier.DEEP,ComponentState.READY,"ableton"),"device_read":HostCapabilityDescriptor("device_read",True,IntegrationTier.DEEP,ComponentState.READY,"ableton"),"automation_write":HostCapabilityDescriptor("automation_write",True,IntegrationTier.DEEP,ComponentState.DEGRADED,"ableton",reason="write unavailable",fallback_candidates=["plugin_bridge"])}
  plan=plan_job_capabilities(HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=caps),list(caps))
  self.assertEqual([x["method"] for x in plan],["AUTOMATIC","AUTOMATIC","GUIDED_MANUAL"]);self.assertEqual(plan[2]["fallback_candidates"],["plugin_bridge"])
 def test_subcapability_failures_and_recovery_are_isolated(self):
  names=("automation_read","automation_create","midi_read","midi_modify","routing_read_input","routing_set_input")
  adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities={name:HostCapabilityDescriptor(name,True,IntegrationTier.DEEP,ComponentState.READY,"ableton") for name in names},song_id="song-1")
  for failed,healthy in (("automation_create","automation_read"),("midi_modify","midi_read"),("routing_set_input","routing_read_input")):
   adapter.mark_state(failed,ComponentState.UNAVAILABLE,"function circuit open")
   self.assertIsNone(adapter.resolve(failed));self.assertIsNotNone(adapter.resolve(healthy));self.assertEqual(adapter.implementation_maturity,IntegrationTier.DEEP);self.assertEqual(adapter.song_id,"song-1")
  adapter.mark_state("midi_modify",ComponentState.RECOVERING);self.assertIsNone(adapter.resolve("midi_modify"));self.assertIsNotNone(adapter.resolve("midi_read"))
  adapter.mark_state("midi_modify",ComponentState.READY);self.assertIsNotNone(adapter.resolve("midi_modify"));self.assertEqual(adapter.capabilities["automation_create"].runtime_state,ComponentState.UNAVAILABLE)
 def test_resolution_replaces_only_failed_capability(self):
  deep={name:HostCapabilityDescriptor(name,True,IntegrationTier.DEEP,ComponentState.READY,"ableton") for name in ("track_read","automation_write")}
  deep["automation_write"].runtime_state=ComponentState.DEGRADED
  bridge={"automation_write":HostCapabilityDescriptor("automation_write",True,IntegrationTier.GENERIC,ComponentState.READY,"plugin_bridge")}
  plan=resolve_job_capabilities([HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=deep),HostAdapterDescriptor("Bridge",IntegrationTier.GENERIC,capabilities=bridge)],["track_read","automation_write"])
  self.assertEqual([(x["capability"],x["implementation"]) for x in plan],[("track_read","ableton"),("automation_write","plugin_bridge")])
 def test_host_update_changes_only_named_compatibility(self):
  caps={name:HostCapabilityDescriptor(name,True,IntegrationTier.DEEP,ComponentState.READY,"ableton",host_version="12.3") for name in ("transport_read","midi_read","automation_write","routing_set_output")}
  adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=caps,song_id="song")
  HostCompatibilityEngine().host_updated(adapter,"12.4",{"automation_write":CompatibilityState.NEEDS_REVALIDATION,"routing_set_output":CompatibilityState.KNOWN_INCOMPATIBLE})
  self.assertIsNotNone(adapter.resolve("transport_read"));self.assertIsNotNone(adapter.resolve("midi_read"));self.assertIsNone(adapter.resolve("automation_write"));self.assertIsNone(adapter.resolve("routing_set_output"))
  self.assertEqual(adapter.song_id,"song");self.assertEqual(adapter.implementation_maturity,IntegrationTier.DEEP);self.assertIn("2 degraded capabilities",adapter.status()["summary"])
 def test_adapter_update_revalidates_only_affected_capabilities(self):
  caps={name:HostCapabilityDescriptor(name,True,IntegrationTier.DEEP,ComponentState.READY,"ableton",adapter_version="1.8.3") for name in ("transport_read","midi_read","automation_write","clip_envelope_modify")}
  adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=caps,song_id="song")
  engine=HostCompatibilityEngine();detail=engine.stage_adapter_update(adapter,CapabilityUpdate("1.8.4",{"automation_write","clip_envelope_modify"},unchanged={"transport_read","midi_read"}))
  self.assertEqual(detail["affected"],["automation_write","clip_envelope_modify"]);self.assertIsNotNone(adapter.resolve("transport_read"));self.assertIsNotNone(adapter.resolve("midi_read"))
  engine.verify(adapter,"automation_write",True,"probe passed",10);self.assertIsNotNone(adapter.resolve("automation_write"));self.assertEqual(adapter.song_id,"song")
 def test_capability_circuit_breaker_does_not_quarantine_adapter(self):
  caps={name:HostCapabilityDescriptor(name,True,IntegrationTier.DEEP,ComponentState.READY,"ableton") for name in ("transport_read","automation_write")};adapter=HostAdapterDescriptor("Ableton",IntegrationTier.DEEP,capabilities=caps)
  breaker=CapabilityCircuitBreaker(2);self.assertFalse(breaker.failure(adapter,"automation_write","fault"));self.assertTrue(breaker.failure(adapter,"automation_write","fault"))
  self.assertIsNone(adapter.resolve("automation_write"));self.assertIsNotNone(adapter.resolve("transport_read"));self.assertEqual(adapter.adapter_state,ComponentState.READY)
  breaker.recover(adapter,"automation_write");self.assertEqual(adapter.capabilities["automation_write"].runtime_state,ComponentState.RECOVERING)
 def test_packaging_dependencies_in_use_and_rollback(self):
  core=ComponentManifest(Component.CORE,"1",{"mac"},{"arm64"},rollback_source="old")
  plugin=ComponentManifest(Component.VST3,"1",{"mac"},{"arm64"},{Component.CORE},rollback_source="old")
  p=PackagingPlanner([core,plugin]);self.assertEqual(p.install([Component.VST3],"mac","arm64")["components"],["CORE","VST3"]);self.assertTrue(p.uninstall([Component.CORE])["preserve_user_data"])
  plugin.in_use=True
  with self.assertRaises(RuntimeError):p.update([Component.VST3])
 def test_update_plan_advertises_capability_specific_changes(self):
  adapter=ComponentManifest(Component.ABLETON_ADAPTER,"1.8.4",{"mac"},{"arm64"},rollback_source="1.8.3",capability_fixes={"automation_write"},capabilities_unchanged={"transport_read","midi_read"})
  detail=PackagingPlanner([adapter]).update([Component.ABLETON_ADAPTER])["capability_changes"]["ABLETON_ADAPTER"]
  self.assertEqual(detail["fixes"],["automation_write"]);self.assertEqual(detail["unchanged"],["midi_read","transport_read"])
if __name__=="__main__":unittest.main()
