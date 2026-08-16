from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_audio import AudioBuffer
from n0te_audio_workflow import Encoding, RenderSpecification
from n0te_dsp import Gain
from n0te_product import (
    Evidence, EvidenceKind, MonitoringContext, Privacy, ProductStore, SongTwins,
    archive_manifest, assess_portability, audition_candidates, authority_view, capability_health, deliver,
    mix_relationship, plan_job, signal_view, what_if,
)
from n0te_project_graph import GraphNode, ProjectGraph


def tone(value=.1, frames=4800):
    return AudioBuffer(48000, (tuple([value] * frames), tuple([value] * frames)), "fixture")


class ProductExperienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ProductStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def evidence(self, kind, claim, **kwargs):
        return Evidence(kind, claim, "test", "song", "workspace", **kwargs)

    def test_session_goal_guardrails_and_evidence_only_debrief_persist(self):
        session = self.store.start_session(
            "song", "workspace", "ARRANGE", "Finish verse", "Structure committed",
            ["mastering", "plugin shopping"], deliverable="verse structure",
        )
        done = self.store.complete_session(
            session["id"],
            [
                self.evidence(EvidenceKind.DAW_FACT, "Verse marker created"),
                self.evidence(EvidenceKind.USER_DECISION, "Kept short pre-chorus"),
                self.evidence(EvidenceKind.EAR_DECISION_REQUIRED, "Choose chorus density"),
            ],
            "Audition chorus density",
        )
        self.assertEqual(done["not_now"], ["mastering", "plugin shopping"])
        self.assertEqual(done["debrief"]["what_changed"], ["Verse marker created"])
        self.assertFalse(done["debrief"]["completed"])
        self.assertEqual(done["debrief"]["exit_condition_status"], "UNVERIFIED")
        self.assertEqual(ProductStore(self.root).load()["sessions"][0]["status"], "COMPLETED")

    def test_session_exit_condition_can_be_explicitly_evidence_supported(self):
        session = self.store.start_session("song", "workspace", "ARRANGE", "Finish verse", "Structure committed")
        done = self.store.complete_session(
            session["id"],
            [self.evidence(EvidenceKind.DAW_FACT, "Verse structure committed")],
            exit_condition_status="EVIDENCE_SUPPORTED",
        )
        self.assertTrue(done["debrief"]["completed"])

    def test_evidence_provenance_privacy_and_context_certainty_are_distinct(self):
        evidence = [
            self.evidence(EvidenceKind.DAW_FACT, "Track contains EQ"),
            self.evidence(EvidenceKind.INFERENCE, "Vocal may feel buried"),
            self.evidence(EvidenceKind.EAR_DECISION_REQUIRED, "Should vocal be louder?"),
        ]
        context = self.store.context("song", "workspace", evidence)
        self.assertEqual([x["claim"] for x in context["known"]], ["Track contains EQ"])
        self.assertEqual([x["claim"] for x in context["thought"]], ["Vocal may feel buried"])
        for outward in (
            Privacy.AVAILABLE_TO_AI,
            Privacy.SYNC_ELIGIBLE,
            Privacy.PUBLICATION_ELIGIBLE,
            Privacy.COMMUNITY_VISIBLE,
        ):
            with self.assertRaises(ValueError):
                Evidence(
                    EvidenceKind.USER_DECLARED_INTENT,
                    "secret",
                    "user",
                    "song",
                    privacy=(Privacy.VAULT, outward),
                )

    def test_creative_twin_blocks_only_relevant_automatic_technical_fix(self):
        twins = SongTwins(
            "song",
            creative=[self.evidence(EvidenceKind.USER_DECLARED_INTENT, "Preserve intentional clipping texture")],
        )
        clipping = twins.recommend("Clipping measured")
        self.assertFalse(clipping["automatic_correction"])
        self.assertEqual(clipping["decision"], "EAR_DECISION_REQUIRED")
        unrelated = twins.recommend("Kick bass masking measured")
        self.assertTrue(unrelated["automatic_correction"])

    def test_creative_twin_respects_section_scope(self):
        twins = SongTwins(
            "song",
            creative=[self.evidence(
                EvidenceKind.USER_DECLARED_INTENT,
                "Preserve intentional clipping texture in chorus",
                section="chorus",
            )],
        )
        self.assertTrue(twins.recommend("Clipping measured", section="verse")["automatic_correction"])
        self.assertFalse(twins.recommend("Clipping measured", section="chorus")["automatic_correction"])

    def test_corrupt_product_state_is_preserved_and_mutation_fails_closed(self):
        self.store.path.write_text("{broken", encoding="utf-8")
        loaded = self.store.load()
        self.assertTrue(loaded["recovery_required"])
        self.assertTrue(Path(loaded["recovery_copy"]).is_file())
        with self.assertRaises(RuntimeError):
            self.store.start_session("song", "workspace", "MIX", "Balance vocal", "Vocal approved")

    def test_ear_decisions_support_cant_tell_defer_and_restart(self):
        row = self.store.create_ear_decision("song", "workspace", "Which vocal level?", ["A", "B"])
        result = self.store.resolve_ear_decision(row["id"], "CANT_TELL")
        self.assertEqual(result["status"], "DEFERRED")
        self.assertEqual(ProductStore(self.root).load()["ear_decisions"][0]["choice"], "CANT_TELL")

    def test_taste_one_choice_is_observation_and_explicit_is_strong(self):
        self.assertEqual(self.store.record_preference("s1", "vocal", "dark")["level"], "OBSERVATION")
        self.assertEqual(self.store.record_preference("s2", "vocal", "dark", explicit=True)["level"], "STRONG_PREFERENCE")

    def test_plan_explains_selection_authority_and_what_if_labels_model(self):
        plan = plan_job(
            "Fix mud",
            [self.evidence(EvidenceKind.AUDIO_MEASUREMENT, "Energy overlap")],
            "existing EQ",
            "already verified in project",
            "GATE_1",
            ["N0TE EQ"],
        )
        self.assertEqual(plan["authority"], "GATE_1")
        self.assertFalse(plan["applied"])
        self.assertEqual(what_if("Bypass EQ?", "less latency")["evidence_kind"], "MODELED_VALUE")

    def test_lab_loudness_matches_without_overwrite_and_does_not_invent_generic_winner(self):
        original = tone(.1)
        louder = Gain(6).process(original)
        lab = audition_candidates(original, {"A": louder})
        self.assertAlmostEqual(
            lab["candidates"]["A"]["report"]["levels"]["lufs_i"],
            lab["candidates"]["ORIGINAL"]["report"]["levels"]["lufs_i"],
            places=5,
        )
        lab["user_winner"] = "A"
        self.assertFalse(lab["source_overwritten"])
        self.assertIsNone(lab["measurement_winner"])
        self.assertIsNone(lab["measurement_objective"])

    def test_lab_measurement_winner_requires_explicit_job_objective(self):
        original = tone(.1)
        candidate = Gain(-3).process(original)
        lab = audition_candidates(
            original,
            {"A": candidate},
            loudness_match=False,
            evaluation_profile={"metric": "true_dbtp", "target": -6.0},
        )
        self.assertIn(lab["measurement_winner"], lab["candidates"])
        self.assertEqual(lab["measurement_objective"], {"metric": "true_dbtp", "target": -6.0})

    def test_mix_overlap_is_measurement_not_automatic_problem(self):
        result = mix_relationship("kick", tone(.2), "bass", tone(.2))
        self.assertIsNone(result["problem"])
        self.assertEqual(result["action_status"], "EAR_DECISION_REQUIRED")

    def test_signal_latency_distinguishes_modeled_from_measured(self):
        view = signal_view([{"id": "spiff", "semantic_job": "UNKNOWN"}], [], {"frames": 128, "measured": False})
        self.assertEqual(view["latency"]["evidence_kind"], "MODELED_VALUE")
        self.assertEqual(view["diagnostics"][0]["issue"], "UNVERIFIED_SEMANTICS")

    def test_portability_is_evidence_bound_and_never_claims_translation(self):
        graph = ProjectGraph(
            "song",
            "workspace",
            [
                GraphNode("a", "AudioAsset"),
                GraphNode("rack", "Device", host_type="Ableton"),
                GraphNode("route", "Routing"),
            ],
        )
        report = assess_portability(graph, "Logic")
        self.assertEqual(
            [x["status"] for x in report["items"]],
            ["PORTABLE", "HOST_SPECIFIC", "REQUIRES_GUIDED_MANUAL"],
        )
        self.assertFalse(report["translation_performed"])

    def test_portability_checks_cross_host_plugin_identity_before_host_native_device(self):
        graph = ProjectGraph(
            "song",
            "workspace",
            [GraphNode("eq", "Device", host_type="Ableton", data={"plugin_id": "vendor.eq"})],
        )
        missing = assess_portability(graph, "Logic")
        self.assertEqual(missing["items"][0]["status"], "UNKNOWN")
        installed = assess_portability(graph, "Logic", installed_plugins=("vendor.eq",))
        self.assertEqual(installed["items"][0]["status"], "PARTIALLY_PORTABLE")

    def test_version_tree_preserves_rejected_branch(self):
        root = self.store.add_version("song", "workspace", "v1")
        self.store.add_version("song", "workspace", "brighter", root["id"], "REJECTED", ["EQ +2 dB"])
        tree = ProductStore(self.root).version_tree("song")
        self.assertEqual(tree["versions"][1]["status"], "REJECTED")
        self.assertFalse(tree["mutation_supported"])

    def test_delivery_requires_authority_preserves_source_and_writes_receipt(self):
        source = self.root / "source.wav"
        source.write_bytes(b"source")
        output = self.root / "delivery.wav"
        audio = tone()
        with self.assertRaises(PermissionError):
            deliver(
                source, output, audio, "song", "workspace", "v1", [],
                RenderSpecification(48000, Encoding.PCM24), False,
            )
        receipt = deliver(
            source, output, audio, "song", "workspace", "v1", [],
            RenderSpecification(48000, Encoding.PCM24), True,
        )
        self.assertEqual(receipt["render_specification"]["encoding"], "PCM24")
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(receipt["analysis_before"]["status"], "UNAVAILABLE")

    def test_monitoring_health_authority_and_archive_are_truthful(self):
        monitoring = MonitoringContext(output_device="Headphones", sample_rate=48000)
        self.assertEqual(monitoring.evidence_kind, EvidenceKind.USER_DECLARED_INTENT)
        health = capability_health({"core": {"status": "READY"}, "bridge": {"status": "FAILED"}})
        self.assertEqual(health["overall"], "DEGRADED")
        self.assertTrue(health["capability_scoped"])
        recovering = capability_health({"core": {"status": "READY"}, "bridge": {"status": "RECOVERING"}})
        self.assertEqual(recovering["overall"], "DEGRADED")
        policy = authority_view()
        self.assertEqual(policy["daw_project_mutation"], "GATE_1")
        self.assertEqual(policy["view_type"], "POLICY_SUMMARY_NOT_RUNTIME_AUTHORITY")
        self.assertFalse(archive_manifest("song", [], [], [], [], [])["bundles_third_party_software"])


if __name__ == "__main__":
    unittest.main()
