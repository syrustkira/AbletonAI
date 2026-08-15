from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import n0te_gemini_native as gemini


class MemoryResponse:
    def __init__(self, payload):
        self.payload = payload
    def read(self):
        return json.dumps(self.payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class GeminiNativeTests(unittest.TestCase):
    def provider(self, response_payload):
        seen = {}
        def urlopen(req, timeout=0):
            seen["url"] = req.full_url
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            seen["body"] = json.loads(req.data.decode("utf-8"))
            seen["timeout"] = timeout
            return MemoryResponse(response_payload)
        module = SimpleNamespace(
            _ORIGINAL_URLOPEN=urlopen,
            _read_http_error=lambda exc: "http error",
            ProviderUnavailableError=RuntimeError,
            SWITCHBOARD_URL="http://127.0.0.1:8767/",
        )
        return module, seen

    def test_native_gemini_uses_json_schema_and_google_key_header(self):
        provider, seen = self.provider({
            "candidates": [{"content": {"parts": [{"text": '{"decision":"keep","actions":[]}'}]}}]
        })
        schema = {
            "type": "object",
            "properties": {"decision": {"type": "string"}, "actions": {"type": "array", "items": {"type": "object"}}},
            "required": ["decision", "actions"],
            "additionalProperties": False,
        }
        chat = {
            "model": "gemini-3.5-flash",
            "messages": [
                {"role": "system", "content": "Return a N0TE decision."},
                {"role": "user", "content": "Inspect the selected track."},
            ],
            "temperature": 0.2,
            "max_tokens": 700,
        }
        result = gemini.gemini_native_chat(provider, "google-secret", chat, {"name": "reply", "schema": schema, "strict": True}, 12)
        self.assertEqual(result["provider_bridge"], "gemini-native")
        self.assertIn("models/gemini-3.5-flash:generateContent", seen["url"])
        self.assertEqual(seen["headers"].get("x-goog-api-key"), "google-secret")
        self.assertNotIn("authorization", seen["headers"])
        self.assertEqual(seen["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(seen["body"]["generationConfig"]["responseJsonSchema"], schema)
        self.assertEqual(seen["body"]["generationConfig"]["temperature"], 0.0)
        self.assertEqual(seen["body"]["generationConfig"]["maxOutputTokens"], 700)
        self.assertEqual(seen["body"]["systemInstruction"]["parts"][0]["text"], "Return a N0TE decision.")

    def test_malformed_native_gemini_json_fails_closed(self):
        provider, _ = self.provider({
            "candidates": [{"content": {"parts": [{"text": '{"decision":"keep" "actions":[]}'}]}}]
        })
        with self.assertRaisesRegex(RuntimeError, "did not return valid structured JSON"):
            gemini.gemini_native_chat(
                provider,
                "google-secret",
                {"model": "gemini-3.5-flash", "messages": [{"role": "user", "content": "test"}]},
                {"name": "reply", "schema": {"type": "object"}, "strict": True},
                12,
            )

    def test_install_only_intercepts_gemini(self):
        original = Mock(return_value={"choices": [{"message": {"content": "{}"}}]})
        module = SimpleNamespace(_chat_request=original, _GEMINI_NATIVE_INSTALLED=False)
        old_native = gemini.gemini_native_chat
        try:
            gemini.gemini_native_chat = Mock(return_value={"choices": [{"message": {"content": '{"ok":true}'}}]})
            gemini.install(module)
            module._chat_request("ollama", "http://127.0.0.1:11434/v1", "", {"model": "qwen", "messages": []}, None, 3)
            original.assert_called_once()
            module._chat_request("gemini", "ignored", "g-key", {"model": "gemini-3.5-flash", "messages": []}, {"schema": {"type": "object"}}, 3)
            gemini.gemini_native_chat.assert_called_once()
        finally:
            gemini.gemini_native_chat = old_native


if __name__ == "__main__":
    unittest.main()
