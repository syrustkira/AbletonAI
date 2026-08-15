import http.client
import json
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import n0te_server as server


SNAPSHOT = {
    "ping": {"ok": True},
    "set": {
        "set_signature": "set-signature",
        "tracks": [{"id": 10, "index": 0, "name": "Track", "devices": []}],
        "return_tracks": [],
        "master_track": {"id": 100, "name": "Master", "devices": []},
    },
    "song": {"id": 900, "properties": {"file_path": "/tmp/Song.als"}},
    "view": {"properties": {"selected_track": {"id": 10}}},
    "selected_track_summary": {"id": 10, "index": 0, "name": "Track"},
}


class ServerRouteCharacterizationTests(unittest.TestCase):
    """Lock observable companion HTTP contracts before server decomposition."""

    def _request(self, method, path, body=b"", headers=None, content_length=None):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
            conn.putrequest(method, path, skip_host=True)
            request_headers = dict(headers or {})
            conn.putheader("Host", request_headers.pop("Host", "127.0.0.1:8766"))
            for key, value in request_headers.items():
                conn.putheader(key, value)
            if method == "POST":
                conn.putheader("Content-Length", len(body) if content_length is None else content_length)
            conn.endheaders(body or None)
            response = conn.getresponse()
            payload = response.read()
            result = response.status, dict(response.getheaders()), payload
            conn.close()
            return result
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()

    def test_online_status_get_preserves_app_and_live_context_contract(self):
        with patch.object(server, "get_snapshot", return_value=SNAPSHOT), \
                patch.object(server.projects, "load_song", return_value={"stage": "idea"}), \
                patch.object(server.projects, "list_conversation", return_value=[{"role": "user"}]):
            status, headers, body = self._request("GET", "/api/status")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["snapshot"]["set"]["set_signature"], "set-signature")
        self.assertEqual(payload["selected_track"]["id"], 10)
        self.assertEqual(payload["song_state"], {"stage": "idea"})
        self.assertEqual(payload["conversation"], [{"role": "user"}])

    def test_history_get_aggregates_existing_persistent_ledgers(self):
        with patch.object(server, "get_snapshot", return_value=SNAPSHOT), \
                patch.object(server, "list_transactions", return_value=[{"id": "tx"}]), \
                patch.object(server.projects, "list_checkpoints", return_value=[{"id": "cp"}]), \
                patch.object(server.projects, "list_decisions", return_value=[{"id": "decision"}]), \
                patch.object(server.projects, "list_discovery", return_value=[{"id": "discovery"}]), \
                patch.object(server.projects, "list_conversation", return_value=[{"id": "message"}]):
            status, _, body = self._request("GET", "/api/history")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(
            {key: payload[key][0]["id"] for key in ("transactions", "checkpoints", "decisions", "discovery", "conversation")},
            {"transactions": "tx", "checkpoints": "cp", "decisions": "decision", "discovery": "discovery", "conversation": "message"},
        )

    def test_get_rejects_nonlocal_host_and_origin_before_route_dispatch(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}):
            status, _, body = self._request("GET", "/api/status", headers=headers)
            self.assertEqual(status, 403)
            self.assertIn("Rejected non-local", json.loads(body)["error"])

    def test_negative_and_non_numeric_content_lengths_are_typed_bad_requests(self):
        for value, expected in ((-1, 413), ("not-a-number", 400)):
            status, _, body = self._request("POST", "/api/config", content_length=value)
            self.assertEqual(status, expected)
            self.assertFalse(json.loads(body)["ok"])

    def test_non_object_json_body_is_currently_treated_as_empty_object(self):
        with patch.object(server, "apply_proposal", return_value={"ok": True, "empty_id": True}) as apply:
            status, _, body = self._request("POST", "/api/apply", b"[]")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["empty_id"])
        apply.assert_called_once_with("")

    def test_chat_provider_transport_failure_is_visible_as_service_unavailable(self):
        with patch.object(server, "get_snapshot", return_value=SNAPSHOT), \
                patch.object(server, "ask_openai", side_effect=urllib.error.URLError("provider offline")):
            status, _, body = self._request("POST", "/api/chat", b'{"message":"What should I do?"}')
        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertFalse(payload["ok"])
        self.assertIn("provider offline", payload["error"])

    def test_chat_registers_proposal_ownership_targets_and_conversation(self):
        reply = {"message": "Leave it alone.", "decision_summary": "No change", "actions": []}
        registry = {}
        projects = Mock()
        projects.song_key.return_value = "song-key"
        with patch.object(server, "get_snapshot", return_value=SNAPSHOT), \
                patch.object(server, "ask_openai", return_value=reply), \
                patch.object(server, "projects", projects), \
                patch.object(server, "proposals", registry):
            status, _, body = self._request("POST", "/api/chat", b'{"message":"Should I change it?"}')
        payload = json.loads(body)
        self.assertEqual(status, 200)
        proposal = registry[payload["proposal_id"]]
        self.assertEqual(proposal["signature"], "set-signature")
        self.assertEqual(proposal["song_key"], "song-key")
        self.assertEqual(proposal["affected_targets"], [])
        self.assertEqual(projects.append_conversation.call_count, 2)

    def test_selected_midi_route_returns_live_detail_and_read_error_verbatim(self):
        snap = json.loads(json.dumps(SNAPSHOT))
        snap["view"]["properties"]["detail_clip"] = {"id": 77, "name": "MIDI"}
        snap["selected_clip_notes"] = {"notes": [{"pitch": 60}]}
        snap["selected_clip_notes_error"] = ""
        with patch.object(server, "get_snapshot", return_value=snap):
            status, _, body = self._request("POST", "/api/create/midi", b"{}")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["clip"]["id"], 77)
        self.assertEqual(payload["notes"]["notes"][0]["pitch"], 60)
        self.assertEqual(payload["error"], "")


if __name__ == "__main__":
    unittest.main()
