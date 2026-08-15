import json
import tempfile
import unittest
from pathlib import Path
import sys
import os
import subprocess
import threading
import time
import http.client
import io

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_core import validate_action, capture_inverse, execute_action, make_transaction, save_transaction, latest_transaction, live_object_index, TRACK_TARGETED_KINDS
from n0te_state import atomic_write_json
from n0te_doctor import remote_script_doctor
from n0te_library import LibraryIndex, capability_matches, current_set_devices
from n0te_context import ContextStore
from n0te_project import ProjectStore, compare_snapshots, finish_checklist
from n0te_discovery import current_set_audio, general_web_search_urls, extract_discovery_intent

SNAP = {
    "set": {
        "tempo": 120.0,
        "signature_numerator": 4,
        "tracks": [
            {"index": 0, "id": 10, "name": "Kick", "devices": [{"id": 5, "name": "Utility", "class_name": "Utility"}], "clips": [{"id": 77, "name": "Clip A"}], "arrangement_clips": []},
            {"index": 1, "id": 11, "name": "Bass", "devices": [], "clips": [], "arrangement_clips": []},
        ],
        "return_tracks": [],
        "master_track": {"id": 100, "name": "Master", "devices": []},
        "set_signature": "abc",
    },
    "song": {"properties": {"file_path": "/tmp/Test.als", "appointed_device": None}},
    "view": {"properties": {"selected_track": {"id": 10}}},
}


def action(kind, **kwargs):
    base = {
        "kind": kind,
        "track_index": 0,
        "send_index": 0,
        "target_id": 0,
        "parameter": "",
        "string_value": "",
        "number_value": 0.0,
        "number_value_2": 0.0,
        "bool_value": False,
        "reason": "test",
        "risk": "low",
    }
    base.update(kwargs)
    return base


class FakeBridge:
    def __init__(self):
        self.track = {"name": "Kick", "mute": False, "solo": False, "arm": False}
        self.tempo = 120.0
        self.pan = 0.0
        self.volume = 0.5
        self.send = 0.2
        self.param = {"id": 99, "name": "Dry/Wet", "value": 0.2}
        self.device_active = True
        self.loop = {"loop": False, "loop_start": 0.0, "loop_length": 16.0}
        self.notes = [
            {"note_id": 1, "pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 90.0, "mute": False, "probability": 1.0, "velocity_deviation": 0.0, "release_velocity": 64.0},
            {"note_id": 2, "pitch": 64, "start_time": 1.0, "duration": 1.0, "velocity": 88.0, "mute": False, "probability": 1.0, "velocity_deviation": 0.0, "release_velocity": 64.0},
        ]

    def request(self, method, params):
        ref = params.get("ref") or {}
        path = ref.get("path", "")
        if method == "get":
            props = {}
            for key in params.get("properties", []):
                if path == "live_set":
                    if key == "tempo": props[key] = self.tempo
                    elif key in self.loop: props[key] = self.loop[key]
                    else: props[key] = None
                elif "mixer_device panning" in path:
                    props[key] = self.pan
                elif "mixer_device volume" in path:
                    props[key] = self.volume
                elif "mixer_device sends 0" in path:
                    props[key] = self.send
                elif "tracks 0" in path:
                    props[key] = self.track[key]
                elif ref.get("id") == 5 and key == "is_active":
                    props[key] = self.device_active
                elif ref.get("id") == 77:
                    props[key] = "Clip A" if key == "name" else False
            return {"properties": props}
        if method == "set":
            if path == "live_set" and params["property"] == "tempo": self.tempo = params["value"]
            elif "tracks 0" in path: self.track[params["property"]] = params["value"]
            elif ref.get("id") == 5 and params["property"] == "is_active": self.device_active = params["value"]
            return {"ok": True}
        if method == "device_parameters":
            return [dict(self.param)]
        if method == "parameter_set":
            if "panning" in path: self.pan = params["value"]
            elif "volume" in path: self.volume = params["value"]
            elif "sends 0" in path: self.send = params["value"]
            elif ref.get("id") == 99: self.param["value"] = params["value"]
            return {"ok": True}
        if method == "batch":
            for op in params["operations"]:
                p = op["params"]
                if p["property"] in self.loop: self.loop[p["property"]] = p["value"]
            return {"ok": True}
        if method == "clip_notes":
            return {"notes": [dict(n) for n in self.notes]}
        if method == "clip_update_notes":
            by_id = {n["note_id"]: n for n in self.notes}
            for update in params.get("updates") or []:
                note = by_id[update["note_id"]]
                for k, v in update.items():
                    if k != "note_id": note[k] = v
            return {"ok": True, "changed": len(params.get("updates") or [])}
        raise AssertionError((method, params))


class CoreTests(unittest.TestCase):
    def test_valid_track_action(self):
        self.assertTrue(validate_action(action("rename_track", string_value="Drums"), SNAP)[0])

    def test_invalid_track_index(self):
        self.assertFalse(validate_action(action("rename_track", track_index=9, string_value="x"), SNAP)[0])

    def test_rejects_hallucinated_device(self):
        self.assertFalse(validate_action(action("set_device_parameter", target_id=999, parameter="Dry/Wet", number_value=0.7), SNAP)[0])

    def test_rejects_hallucinated_clip(self):
        self.assertFalse(validate_action(action("set_clip_name", target_id=999, string_value="X"), SNAP)[0])

    def test_mixer_ranges(self):
        self.assertTrue(validate_action(action("set_track_volume", number_value=0.5), SNAP)[0])
        self.assertFalse(validate_action(action("set_track_volume", number_value=2.0), SNAP)[0])

    def test_inverse_and_execute(self):
        b = FakeBridge()
        a = action("rename_track", string_value="DRUMS")
        inv = capture_inverse(b, a)
        self.assertEqual(inv["string_value"], "Kick")
        execute_action(b, a)
        self.assertEqual(b.track["name"], "DRUMS")
        execute_action(b, inv)
        self.assertEqual(b.track["name"], "Kick")

    def test_parameter_inverse(self):
        b = FakeBridge()
        a = action("set_device_parameter", target_id=5, parameter="Dry/Wet", number_value=0.7)
        inv = capture_inverse(b, a)
        self.assertEqual(inv["number_value"], 0.2)
        execute_action(b, a)
        self.assertEqual(b.param["value"], 0.7)

    def test_device_active_inverse(self):
        b = FakeBridge()
        a = action("set_device_active", target_id=5, bool_value=False)
        inv = capture_inverse(b, a)
        self.assertTrue(inv["bool_value"])
        execute_action(b, a)
        self.assertFalse(b.device_active)

    def test_arrangement_loop_inverse(self):
        b = FakeBridge()
        a = action("set_arrangement_loop", number_value=32, number_value_2=16, bool_value=True)
        inv = capture_inverse(b, a)
        execute_action(b, a)
        self.assertTrue(b.loop["loop"])
        self.assertEqual(b.loop["loop_start"], 32)
        execute_action(b, inv)
        self.assertFalse(b.loop["loop"])

    def test_midi_note_update_is_selected_clip_only_and_reversible(self):
        snap = json.loads(json.dumps(SNAP))
        snap["view"]["properties"]["detail_clip"] = {"id": 77, "name": "Clip A"}
        snap["selected_clip_notes"] = {"notes": [
            {"note_id": 1, "pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 90.0},
            {"note_id": 2, "pitch": 64, "start_time": 1.0, "duration": 1.0, "velocity": 88.0},
        ]}
        a = action("update_midi_clip_notes", target_id=77, string_value=json.dumps([{"note_id": 1, "pitch": 62, "velocity": 80.0}]))
        self.assertTrue(validate_action(a, snap)[0])
        b = FakeBridge()
        inv = capture_inverse(b, a)
        execute_action(b, a)
        self.assertEqual(b.notes[0]["pitch"], 62)
        execute_action(b, inv)
        self.assertEqual(b.notes[0]["pitch"], 60)
        bad = action("update_midi_clip_notes", target_id=999, string_value=json.dumps([{"note_id": 1, "pitch": 62}]))
        self.assertFalse(validate_action(bad, snap)[0])

    def test_transaction_journal(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            tx = make_transaction([], [], "abc", [])
            save_transaction(p, tx)
            _, loaded = latest_transaction(p)
            self.assertEqual(loaded["id"], tx["id"])


class HealthcheckInstallerStateTests(unittest.TestCase):
    def test_healthcheck_reuses_manifest_user_library(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            home = td / "home"
            state = home / ".n0te-ableton-ai"
            userlib = td / "Custom User Library"
            remote = userlib / "Remote Scripts" / "Ableton_Live_MCP"
            remote.mkdir(parents=True)
            state.mkdir(parents=True)
            (state / "install_manifest.json").write_text(json.dumps({"ableton_user_library": str(userlib)}), encoding="utf-8")
            env = os.environ.copy()
            env["HOME"] = str(home)
            cp = subprocess.run([sys.executable, str(ROOT / "app" / "healthcheck.py")], env=env, capture_output=True, text=True, check=True)
            data = json.loads(cp.stdout)
            self.assertEqual(data["user_library"], str(userlib))
            self.assertTrue(data["remote_script"])


class LibraryTests(unittest.TestCase):
    def test_capability_match(self):
        rows = capability_matches("make my vocal wider", {"Utility"})
        self.assertTrue(any(row["id"] == "stereo_width" for row in rows))
        width = next(row for row in rows if row["id"] == "stereo_width")
        self.assertIn("Utility", width["native_available"])

    def test_current_set_devices(self):
        rows = current_set_devices(SNAP)
        self.assertEqual(rows[0]["name"], "Utility")
        self.assertEqual(rows[0]["track_name"], "Kick")

    def test_library_search_cache(self):
        with tempfile.TemporaryDirectory() as td:
            lib = LibraryIndex(Path(td))
            lib.path.parent.mkdir(parents=True, exist_ok=True)
            lib.path.write_text(json.dumps({"version": 1, "scanned_at": 1, "items": [{"name": "Utility", "path": "Audio Effects > Utility", "kind": "native_audio_effect", "format": ""}], "errors": []}))
            self.assertEqual(lib.search("utility")[0]["name"], "Utility")


class ProjectTests(unittest.TestCase):
    def test_song_state_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            state = store.save_song(SNAP, {"stage": "ARRANGE", "session_goal": "Fix chorus"})
            self.assertEqual(state["stage"], "ARRANGE")
            cp = store.checkpoint(SNAP, state, {}, {}, "Before chorus")
            self.assertTrue(Path(cp["path"]).exists())

    def test_compare_tracks(self):
        newer = json.loads(json.dumps(SNAP))
        newer["set"]["tempo"] = 130
        newer["set"]["tracks"][0]["name"] = "KICK"
        changes = compare_snapshots(SNAP, newer)
        self.assertTrue(any(x["type"] == "tempo" for x in changes))
        self.assertTrue(any(x["type"] == "track_name" for x in changes))

    def test_discovery_memory(self):
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            row = store.record_discovery(SNAP, {"title": "Metal Hit", "source": "openverse", "license": "cc0"}, status="rejected", note="too cinematic")
            self.assertTrue(Path(row["path"]).exists())
            hist = store.list_discovery(SNAP)
            self.assertEqual(hist[0]["status"], "rejected")
            self.assertEqual(hist[0]["note"], "too cinematic")

    def test_discovery_helpers(self):
        snap = json.loads(json.dumps(SNAP))
        snap["set"]["tracks"][0]["arrangement_clips"] = [{"id": 88, "name": "Dark Metal Hit", "file_path": "/tmp/metal.wav"}]
        rows = current_set_audio(snap, "metal hit")
        self.assertEqual(rows[0]["source"], "current_set")
        self.assertIn("google.com/search", general_web_search_urls("dark impact")[0]["landing_url"] )

    def test_finish_stage_guard(self):
        f = finish_checklist(SNAP, {"stage": "CREATE", "song_intent": "", "session_goal": "", "next_action": ""})
        self.assertIn("final loudness", f["leave_alone"])


class HardeningTests(unittest.TestCase):
    def test_unsaved_song_identity_survives_signature_changes_and_migrates_on_save(self):
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            a = json.loads(json.dumps(SNAP))
            a["song"] = {"id": 501, "properties": {"file_path": "", "appointed_device": None}}
            a["set"]["set_signature"] = "sig-a"
            key_a = store.song_key(a)
            store.save_song(a, {"stage": "ARRANGE", "session_goal": "Finish chorus"})
            store.append_conversation(a, "user", "why is chorus weak?")
            store.record_discovery(a, {"title": "Metal Hit"}, status="rejected", note="too cinematic")

            b = json.loads(json.dumps(a))
            b["set"]["set_signature"] = "sig-b"  # normal edit must not fork song identity
            self.assertEqual(store.song_key(b), key_a)

            saved = json.loads(json.dumps(b))
            saved["song"]["properties"]["file_path"] = "/tmp/N0TE Saved Test.als"
            saved_key = store.song_key(saved)
            self.assertNotEqual(saved_key, key_a)
            self.assertEqual(store.load_song(saved)["session_goal"], "Finish chorus")
            self.assertEqual(store.list_conversation(saved)[0]["text"], "why is chorus weak?")
            self.assertEqual(store.list_discovery(saved)[0]["note"], "too cinematic")
            self.assertFalse((Path(td) / "songs" / f"{key_a}.json").exists())

    def test_stale_unsaved_identity_is_not_migrated_into_unrelated_saved_set(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            first = ProjectStore(state)
            unsaved = json.loads(json.dumps(SNAP))
            unsaved["song"] = {"id": 111, "properties": {"file_path": ""}}
            unsaved["set"]["set_signature"] = "old-unsaved"
            old_key = first.song_key(unsaved)
            first.save_song(unsaved, {"session_goal": "Old project"})

            second = ProjectStore(state)  # new N0TE process/runtime token
            other = json.loads(json.dumps(SNAP))
            other["song"] = {"id": 999, "properties": {"file_path": "/tmp/Unrelated.als"}}
            other["set"]["set_signature"] = "totally-different"
            second.song_key(other)
            self.assertTrue((state / "songs" / f"{old_key}.json").exists())
            self.assertNotEqual(second.load_song(other)["session_goal"], "Old project")

    def test_context_base_upgrades_without_losing_override_layer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundled = root / "bundled.json"
            bundled.write_text(json.dumps({"schema_version": 2, "context_version": "1.0", "generated_for": "N0TE Ableton AI 1.0", "identity": {"artist": "TellMeN0TE"}, "new": "old"}))
            store = ContextStore(bundled, root / "state")
            self.assertEqual(store.load()["context_version"], "1.0")
            store.replace({"identity": {"custom": "keep-me"}})

            bundled.write_text(json.dumps({"schema_version": 3, "context_version": "1.2.1", "generated_for": "N0TE Ableton AI v1.2.1", "identity": {"artist": "TellMeN0TE"}, "new": "fresh"}))
            loaded = store.load()
            self.assertEqual(loaded["context_version"], "1.2.1")
            self.assertEqual(loaded["new"], "fresh")
            self.assertEqual(loaded["identity"]["custom"], "keep-me")
            self.assertTrue(store.status()["overrides_active"])

    def test_discovery_intent_strips_command_filler_and_extracts_negative(self):
        intent = extract_discovery_intent("Find me a dark metallic impact that isn't too cinematic, search the web too")
        self.assertNotIn("find me", intent["query"].lower())
        self.assertIn("dark metallic impact", intent["query"].lower())
        # The directive can appear after the negative phrase, so web detection is independent of query cleanup.
        self.assertTrue(intent["include_web_hint"])

    def test_recursive_rack_device_inventory(self):
        snap = json.loads(json.dumps(SNAP))
        snap["set"]["tracks"][0]["devices"] = [{"id": 6, "name": "Audio Effect Rack", "class_name": "AudioEffectGroupDevice"}]

        class RackBridge:
            def request(self, method, params):
                rid = (params.get("ref") or {}).get("id")
                if method == "get" and rid == 6:
                    return {"properties": {"can_have_chains": True}, "children": {"chains": [{"id": 60, "name": "Parallel"}]}}
                if method == "get" and rid == 60:
                    return {"children": {"devices": [{"id": 61, "name": "Nested Pro-Q", "class_name": "PluginDevice"}]}}
                if method == "get" and rid == 61:
                    return {"properties": {"can_have_chains": False}, "children": {"chains": []}}
                raise AssertionError((method, params))

        rows = current_set_devices(snap, bridge=RackBridge())
        nested = next(row for row in rows if row["device_id"] == 61)
        self.assertEqual(nested["depth"], 1)
        self.assertEqual(nested["kind"], "third_party_plugin")
        self.assertIn("Parallel", nested["device_path"])

    def test_finish_never_claims_bounce_ready_without_audio_preflight(self):
        f = finish_checklist(SNAP, {"stage": "FINISH", "song_intent": "x", "session_goal": "x", "next_action": "bounce"}, preflight={"structural_preflight_complete": True, "audio_preflight_complete": False, "missing_assets": []})
        self.assertTrue(f["scope_ready"])
        self.assertFalse(f["ready_for_bounce"])
        self.assertFalse(f["audio_preflight_complete"])

    def test_return_and_master_selected_context_are_resolvable(self):
        import n0te_server as server
        snap = json.loads(json.dumps(SNAP))
        snap["set"]["return_tracks"] = [{"id": 20, "index": 0, "name": "A-Reverb", "devices": []}]
        snap["view"]["properties"]["selected_track"] = {"id": 20}
        selected = server.selected_context(snap)
        self.assertEqual(selected["_track_group"], "return")
        self.assertEqual(server.selected_track_ref(snap)[0], "live_set return_tracks 0")
        snap["view"]["properties"]["selected_track"] = {"id": 100}
        self.assertEqual(server.selected_track_ref(snap)[0], "live_set master_track")

    def test_partial_n0te_undo_does_not_call_native_live_undo(self):
        import n0te_server as server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            tx_path = Path(td) / "tx.json"
            store = ProjectStore(Path(td))
            tx = {"id": "t1", "song_key": store.song_key(SNAP), "actions": [], "inverse_actions": [action("rename_track", string_value="A"), action("rename_track", string_value="B")], "undone": False}
            tx_path.write_text(json.dumps(tx))
            calls = []
            class NoUndoBridge:
                def request(self, method, params):
                    calls.append((method, params))
                    return {}
            count = {"n": 0}
            def fake_execute(_bridge, _action, _sig):
                count["n"] += 1
                if count["n"] == 2:
                    raise RuntimeError("rollback failure")
                return {"ok": True}
            with patch.object(server, "latest_transaction", return_value=(tx_path, tx)), patch.object(server, "execute_action", side_effect=fake_execute), patch.object(server, "bridge", NoUndoBridge()), patch.object(server, "projects", store), patch.object(server, "get_snapshot", return_value=SNAP), patch.object(server, "invalidate_snapshot", return_value=None):
                result = server.undo_last_n0te()
            self.assertFalse(result["ok"])
            self.assertTrue(result["recovery_required"])
            self.assertEqual(calls, [])


class ServerWorkflowTests(unittest.TestCase):
    def test_apply_then_n0te_undo_round_trip(self):
        import n0te_server as server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            b = FakeBridge()
            snap = json.loads(json.dumps(SNAP))
            proposal = {
                "created_at": time.time(),
                "signature": "abc",
                "reply": {
                    "message": "Rename for clarity",
                    "decision_summary": "Rename kick",
                    "actions": [action("rename_track", string_value="KICK")],
                },
            }
            with patch.object(server, "bridge", b), patch.object(server, "STATE", state), patch.object(server, "projects", ProjectStore(state)), patch.object(server, "proposals", {"p1": proposal}), patch.object(server, "get_snapshot", return_value=snap), patch.object(server, "invalidate_snapshot", return_value=None):
                applied = server.apply_proposal("p1")
                self.assertTrue(applied["ok"])
                self.assertEqual(b.track["name"], "KICK")
                undone = server.undo_last_n0te()
                self.assertTrue(undone["ok"])
                self.assertEqual(b.track["name"], "Kick")

    def test_transactions_are_scoped_and_legacy_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_transaction(root, make_transaction([], [], "a", [], song_key="song-a"))
            time.sleep(0.01)
            save_transaction(root, make_transaction([], [], "b", [], song_key="song-b"))
            legacy = make_transaction([], [], "old", [])
            save_transaction(root, legacy)
            self.assertEqual(latest_transaction(root, "song-a")[1]["song_key"], "song-a")
            self.assertEqual(latest_transaction(root, "song-b")[1]["song_key"], "song-b")
            self.assertIsNone(latest_transaction(root, "unknown")[1])

    def test_unsaved_transaction_ownership_migrates_on_save_as(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); store = ProjectStore(root)
            unsaved = json.loads(json.dumps(SNAP)); unsaved["song"]["properties"]["file_path"] = ""; unsaved["song"]["id"] = 900
            old_key = store.song_key(unsaved)
            save_transaction(root, make_transaction([], [], "abc", [], song_key=old_key))
            saved = json.loads(json.dumps(unsaved)); saved["song"]["properties"]["file_path"] = "/tmp/New Song.als"
            new_key = store.song_key(saved)
            tx = latest_transaction(root, new_key)[1]
            self.assertIsNotNone(tx)
            self.assertEqual(tx["ownership_migrated_from"], old_key)

    def test_same_runtime_unrelated_saved_set_does_not_take_unsaved_ownership(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); store = ProjectStore(root)
            unsaved = json.loads(json.dumps(SNAP)); unsaved["song"]["properties"]["file_path"] = ""; unsaved["song"]["id"] = 900
            old_key = store.song_key(unsaved)
            save_transaction(root, make_transaction([], [], "abc", [], song_key=old_key))
            unrelated = json.loads(json.dumps(SNAP)); unrelated["song"]["properties"]["file_path"] = "/tmp/B.als"; unrelated["song"]["id"] = 901
            unrelated_key = store.song_key(unrelated)
            self.assertNotEqual(old_key, unrelated_key)
            self.assertIsNone(latest_transaction(root, unrelated_key)[1])
            self.assertEqual(latest_transaction(root, old_key)[1]["song_key"], old_key)

    def test_latest_transaction_uses_fractional_creation_time(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            older = make_transaction([], [], "a", [], song_key="song"); older.update({"id": "z", "created_at": 1000.1})
            newer = make_transaction([], [], "b", [], song_key="song"); newer.update({"id": "a", "created_at": 1000.9})
            save_transaction(root, older); save_transaction(root, newer)
            self.assertEqual(latest_transaction(root, "song")[1]["id"], "a")

    def test_nested_device_uses_canonical_index_and_validation(self):
        snap = json.loads(json.dumps(SNAP))
        snap["set"]["tracks"][0]["devices"][0]["chains"] = [{"devices": [{"id": 501, "name": "Nested"}]}]
        self.assertIn(501, live_object_index(snap)["devices"])
        self.assertTrue(validate_action(action("set_device_active", target_id=501), snap)[0])

    def test_cross_set_undo_is_refused(self):
        import n0te_server as server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            store = ProjectStore(Path(td))
            current = json.loads(json.dumps(SNAP))
            other = json.loads(json.dumps(SNAP)); other["song"]["properties"]["file_path"] = "/tmp/Other.als"
            save_transaction(Path(td), make_transaction([], [], "abc", [], song_key=store.song_key(other)))
            with patch.object(server, "STATE", Path(td)), patch.object(server, "projects", store), patch.object(server, "get_snapshot", return_value=current):
                result = server.undo_last_n0te()
            self.assertFalse(result["ok"])
            self.assertIn("another", result["message"])

    def test_undo_reresolves_shifted_track_by_stable_id(self):
        import n0te_server as server
        from unittest.mock import patch
        class ShiftBridge:
            def __init__(self): self.names = {0: "Other", 1: "N0TE Name"}
            def request(self, method, params):
                path = (params.get("ref") or {}).get("path", "")
                if "tracks " in path:
                    idx = int(path.split("tracks ", 1)[1].split()[0])
                    if method == "get": return {"properties": {"name": self.names[idx]}}
                    if method == "set": self.names[idx] = params["value"]; return {"ok": True}
                raise AssertionError((method, params))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); store = ProjectStore(root); bridge = ShiftBridge()
            snap = json.loads(json.dumps(SNAP)); snap["set"]["tracks"] = [
                {"index": 0, "id": 99, "name": "Other", "devices": [], "clips": [], "arrangement_clips": []},
                {"index": 1, "id": 10, "name": "N0TE Name", "devices": [], "clips": [], "arrangement_clips": []},
            ]
            forward = action("rename_track", track_index=0, string_value="N0TE Name")
            inverse = action("rename_track", track_index=0, string_value="Kick")
            tx = make_transaction([forward], [inverse], "abc", [], song_key=store.song_key(snap), targets=[{"object_type": "track", "object_id": 10, "track_index": 0}])
            save_transaction(root, tx)
            with patch.object(server, "STATE", root), patch.object(server, "projects", store), patch.object(server, "bridge", bridge), patch.object(server, "get_snapshot", return_value=snap), patch.object(server, "invalidate_snapshot"):
                result = server.undo_last_n0te()
            self.assertTrue(result["ok"])
            self.assertEqual(bridge.names, {0: "Other", 1: "Kick"})

    def test_all_track_index_mutations_have_one_canonical_classification(self):
        self.assertEqual(TRACK_TARGETED_KINDS, {
            "rename_track", "set_track_mute", "set_track_solo", "set_track_arm",
            "set_track_pan", "set_track_volume", "set_send_level",
        })

    def test_send_level_apply_and_undo_reresolve_shifted_track_by_stable_id(self):
        import n0te_server as server
        from unittest.mock import patch
        class SendBridge:
            def __init__(self): self.sends = {0: 0.2}
            def request(self, method, params):
                path = (params.get("ref") or {}).get("path", "")
                if "mixer_device sends 0" in path:
                    idx = int(path.split("tracks ", 1)[1].split()[0])
                    if method == "get": return {"properties": {"value": self.sends[idx]}}
                    if method == "parameter_set": self.sends[idx] = params["value"]; return {"ok": True}
                raise AssertionError((method, params))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); store = ProjectStore(root); bridge = SendBridge()
            before = json.loads(json.dumps(SNAP))
            forward = action("set_send_level", track_index=0, send_index=0, number_value=0.8)
            proposal = {
                "created_at": time.time(), "signature": "abc", "song_key": store.song_key(before),
                "affected_targets": server.affected_target_evidence([forward], before),
                "reply": {"message": "send", "decision_summary": "send", "actions": [forward]},
            }
            shifted = json.loads(json.dumps(before)); shifted["set"]["tracks"] = [
                {"index": 0, "id": 99, "name": "Unrelated", "devices": [], "clips": [], "arrangement_clips": []},
                {"index": 1, "id": 10, "name": "Kick", "devices": [], "clips": [], "arrangement_clips": []},
                {"index": 2, "id": 11, "name": "Bass", "devices": [], "clips": [], "arrangement_clips": []},
            ]
            snapshots = [before, before, shifted]
            with patch.object(server, "STATE", root), patch.object(server, "projects", store), patch.object(server, "bridge", bridge), patch.object(server, "proposals", {"p": proposal}), patch.object(server, "get_snapshot", side_effect=snapshots), patch.object(server, "invalidate_snapshot"):
                applied = server.apply_proposal("p")
                self.assertTrue(applied["ok"]); self.assertEqual(bridge.sends[0], 0.8)
                # Simulate insertion: the unrelated Track inherits index 0 while
                # stable Track id 10 and its current send move to index 1.
                bridge.sends = {0: 0.1, 1: 0.8}
                undone = server.undo_last_n0te()
            self.assertTrue(undone["ok"])
            self.assertEqual(bridge.sends, {0: 0.1, 1: 0.2})

    def test_atomic_json_concurrent_writers_never_corrupt(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            threads = [threading.Thread(target=lambda n=n: [atomic_write_json(path, {"writer": n, "sequence": i}) for i in range(30)]) for n in range(6)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            value = json.loads(path.read_text())
            self.assertIn(value["writer"], range(6))
            self.assertEqual(value["sequence"], 29)

    def test_remote_script_doctor_distinguishes_installed_not_loaded(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td); state = home / ".n0te-ableton-ai"; state.mkdir()
            library = home / "User Library"; remote = library / "Remote Scripts/Ableton_Live_MCP"
            (remote / "Ableton_Live_MCP").mkdir(parents=True)
            for path in (remote / "__init__.py", remote / "Ableton_Live_MCP/__init__.py", remote / "Ableton_Live_MCP/bridge.py"):
                path.write_text("# test")
            (state / "install_manifest.json").write_text(json.dumps({"ableton_user_library": str(library)}))
            report = remote_script_doctor(state, home)
            self.assertTrue(report["files_installed"])
            self.assertTrue(report["installed_but_not_loaded"])
            self.assertFalse(report["openai_credential_configured"])

    def test_get_snapshot_reads_selected_return_device(self):
        import n0te_server as server
        from unittest.mock import patch

        class SnapshotBridge:
            def request(self, method, params):
                ref = (params.get("ref") or {}).get("path")
                rid = (params.get("ref") or {}).get("id")
                if method == "ping":
                    return {"ok": True, "version": "12.3.5"}
                if method == "set_summary":
                    return {
                        "tempo": 120.0, "signature_numerator": 4, "signature_denominator": 4,
                        "set_signature": "ret-sig", "tracks": [],
                        "return_tracks": [{"id": 20, "index": 0, "name": "A-Reverb", "devices": [{"id": 30, "name": "Hybrid Reverb", "class_name": "HybridReverb"}]}],
                        "master_track": {"id": 100, "name": "Master", "devices": []}, "scene_count": 0,
                    }
                if method == "get" and ref == "live_set":
                    return {"id": 900, "properties": {"file_path": "/tmp/Return.als", "tempo": 120.0, "current_song_time": 0.0, "is_playing": False, "can_undo": False, "can_redo": False, "appointed_device": None, "loop": False, "loop_start": 0.0, "loop_length": 16.0}}
                if method == "get" and ref == "live_set view":
                    return {"properties": {"selected_track": {"id": 20}, "selected_parameter": None, "detail_clip": None}}
                if method == "get" and ref == "live_set return_tracks 0 view":
                    return {"properties": {"selected_device": {"id": 30, "name": "Hybrid Reverb"}}}
                if method == "device_parameters" and rid == 30:
                    return [{"id": 301, "name": "Dry/Wet", "value": 0.5}]
                if method == "get" and rid == 30:
                    return {"properties": {"is_active": True, "latency_in_ms": 0.0, "latency_in_samples": 0, "class_name": "HybridReverb", "class_display_name": "Hybrid Reverb", "type": 1, "can_have_chains": False}}
                raise AssertionError((method, params))

        with patch.object(server, "bridge", SnapshotBridge()):
            server._snapshot_cache["at"] = 0
            server._snapshot_cache["value"] = None
            snap = server.get_snapshot(force=True)
        self.assertEqual(snap["selected_track_summary"]["_track_group"], "return")
        self.assertEqual(snap["selected_device"]["id"], 30)
        self.assertEqual(snap["selected_device_parameters"][0]["name"], "Dry/Wet")

    def test_ask_openai_filters_hallucinated_action_and_preserves_readonly_reply(self):
        import n0te_server as server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            ctxfile = state / "ctx.json"
            ctxfile.write_text(json.dumps({"schema_version": 3, "context_version": "test", "generated_for": "N0TE Ableton AI test"}))
            projects = ProjectStore(state)
            context = ContextStore(ctxfile, state)
            library = LibraryIndex(state)
            fake_reply = {
                "message": "I can explain this without editing.",
                "decision_summary": "Read only",
                "confidence": 0.8,
                "evidence": ["Live state"],
                "evidence_labels": [{"label": "live_state", "text": "Current set"}],
                "actions": [action("rename_track", track_index=99, string_value="Nope")],
                "needs_audio": False,
                "audio_reason": "",
                "tool_answer": "Use the current tools.",
                "stage_warning": "",
            }
            with patch.object(server, "STATE", state), patch.object(server, "projects", projects), patch.object(server, "context_store", context), patch.object(server, "library", library), patch.object(server, "load_config", return_value={"model": "gpt-5.6", "mode": "produce", "context_sync_path": ""}), patch.object(server, "openai_structured", return_value=fake_reply), patch.object(server, "latest_transaction", return_value=(None, None)):
                result = server.ask_openai("what can Ableton do here?", SNAP)
            self.assertEqual(result["actions"], [])
            self.assertEqual(result["rejected_actions"][0]["reason"], "Invalid track index 99")
            self.assertIn("without editing", result["message"])


class InstallerBundleTests(unittest.TestCase):
    def test_recommended_mac_bootstrap_and_management_scripts_parse(self):
        for name in ("INSTALL_N0TE_MAC.command", "START_N0TE_ABLETON_AI.command", "UNINSTALL_N0TE_ABLETON_AI.command"):
            subprocess.run(["bash", "-n", str(ROOT / name)], check=True)

    def test_legacy_python_dependent_shell_installer_is_not_the_public_entrypoint(self):
        self.assertFalse((ROOT / "INSTALL_N0TE_ABLETON_AI.command").exists())
        self.assertTrue((ROOT / "INSTALL_N0TE_MAC.command").exists())


class OfflineStatusTests(unittest.TestCase):
    def test_status_payload_keeps_app_metadata_when_ableton_is_offline(self):
        import n0te_server as server
        original_snapshot = server.get_snapshot
        try:
            server.get_snapshot = lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError("offline"))
            payload = server.status_payload()
        finally:
            server.get_snapshot = original_snapshot
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["version"], "1.2.4")
        self.assertIn("Ableton bridge offline", payload["error"])
        self.assertIn("config", payload)
        self.assertIn("context", payload)
        self.assertIn("library", payload)


class LocalRequestSafetyTests(unittest.TestCase):
    def test_local_post_origin_guard(self):
        import n0te_server as server
        self.assertTrue(server.local_request_allowed("127.0.0.1:8766", "http://127.0.0.1:8766"))
        self.assertTrue(server.local_request_allowed("localhost:8766", ""))
        self.assertFalse(server.local_request_allowed("evil.example", "http://evil.example"))
        self.assertFalse(server.local_request_allowed("127.0.0.1:8766", "https://evil.example"))


class Gate1ReviewServerTests(unittest.TestCase):
    def test_expired_proposal_ttl_cleanup(self):
        import n0te_server as server
        from unittest.mock import patch
        with patch.object(server, "proposals", {"old": {"created_at": 1}, "new": {"created_at": 1000}}), patch.object(server, "simplify_proposals", {"old-s": {"created_at": 2}}):
            server.cleanup_proposals(now=1000)
            self.assertEqual(set(server.proposals), {"new"})
            self.assertEqual(server.simplify_proposals, {})

    def _request(self, path, body=b"{}", headers=None, content_length=None):
        import n0te_server as server
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
            conn.putrequest("POST", path, skip_host=True)
            conn.putheader("Host", "127.0.0.1:8766")
            for key, value in (headers or {}).items(): conn.putheader(key, value)
            conn.putheader("Content-Length", content_length if content_length is not None else len(body))
            conn.endheaders(body if body else None)
            response = conn.getresponse(); payload = response.read(); conn.close()
            return response.status, payload
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()

    def test_malformed_json_is_400(self):
        self.assertEqual(self._request("/api/config", b"{")[0], 400)

    def test_oversized_body_is_413(self):
        import n0te_server as server
        self.assertEqual(self._request("/api/config", b"", content_length=server.MAX_REQUEST_BODY + 1)[0], 413)

    def test_unknown_proposal_and_route_are_404(self):
        import n0te_server as server
        from unittest.mock import patch
        with patch.object(server, "proposals", {}):
            self.assertEqual(self._request("/api/apply", b'{"proposal_id":"missing"}')[0], 404)
        self.assertEqual(self._request("/api/not-a-route")[0], 404)

    def test_stale_conflict_is_409(self):
        import n0te_server as server
        from unittest.mock import patch
        with patch.object(server, "apply_proposal", side_effect=server.ConflictError("stale")):
            self.assertEqual(self._request("/api/apply", b'{"proposal_id":"p"}')[0], 409)

    def test_unavailable_dependency_is_503(self):
        import n0te_server as server
        from unittest.mock import patch
        with patch.object(server, "apply_proposal", side_effect=ConnectionError("bridge offline")):
            self.assertEqual(self._request("/api/apply", b'{"proposal_id":"p"}')[0], 503)

    def test_nonlocal_origin_is_403(self):
        self.assertEqual(self._request("/api/config", headers={"Origin": "https://evil.example"})[0], 403)

    def test_simplification_failure_status_classes(self):
        import n0te_server as server
        self.assertEqual(server.error_status(LookupError("expired")), 404)
        self.assertEqual(server.error_status(server.ConflictError("stale")), 409)
        self.assertEqual(server.error_status(ConnectionError("bridge")), 503)

    def test_ambiguous_simplification_never_calls_native_undo(self):
        import n0te_server as server
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); store = ProjectStore(root)
            before = json.loads(json.dumps(SNAP)); before["view"]["properties"]["selected_track"] = {"id": 10}
            after = json.loads(json.dumps(before)); after["set"]["tracks"] += [
                {"id": 20, "index": 2, "name": "Copy 1", "devices": []},
                {"id": 21, "index": 3, "name": "Copy 2", "devices": []},
            ]
            proposal = {"created_at": time.time(), "signature": "abc", "song_key": store.song_key(before), "track_index": 0, "result": {"plan": {"replacements": [{"recommendation": "replace", "can_build_experiment": True, "replacement_source": "ableton_native"}]}}}
            class DuplicateBridge:
                def request(self, method, params): return {"ok": True}
            with patch.object(server, "STATE", root), patch.object(server, "projects", store), patch.object(server, "bridge", DuplicateBridge()), patch.object(server, "simplify_proposals", {"s": proposal}), patch.object(server, "get_snapshot", side_effect=[before, after]), patch.object(server, "invalidate_snapshot"), patch.object(server, "native_undo") as native:
                with self.assertRaises(server.ConflictError): server.build_simplify_experiment("s")
            native.assert_not_called()
            self.assertEqual(len(list((root / "recovery").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
