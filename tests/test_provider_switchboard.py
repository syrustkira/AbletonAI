import json
import tempfile
import unittest
import urllib.request
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import n0te_provider as provider


class FakeResponse:
    def __init__(self, obj):
        self.body = json.dumps(obj).encode("utf-8")
        self.status = 200

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ProviderSwitchboardTests(unittest.TestCase):
    def test_gemini_openai_compatibility_endpoint(self):
        self.assertEqual(
            provider._provider_endpoint("gemini", ""),
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )

    def test_ollama_local_openai_compatibility_endpoint(self):
        self.assertEqual(
            provider._provider_endpoint("ollama", ""),
            "http://127.0.0.1:11434/v1",
        )

    def test_custom_plain_http_remote_endpoint_is_rejected(self):
        with self.assertRaises(ValueError):
            provider.normalize_base_url("http://example.com/v1")

    def test_responses_request_translates_to_chat_and_preserves_json_schema(self):
        source = {
            "model": "example",
            "instructions": "system rule",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "answer",
                    "schema": {"type": "object"},
                    "strict": True,
                }
            },
            "max_output_tokens": 123,
        }
        chat, schema = provider.responses_to_chat_payload(source)
        self.assertEqual(chat["messages"][0], {"role": "system", "content": "system rule"})
        self.assertEqual(chat["messages"][1], {"role": "user", "content": "hello"})
        self.assertEqual(chat["response_format"]["json_schema"]["name"], "answer")
        self.assertEqual(chat["max_tokens"], 123)
        self.assertEqual(schema["schema"], {"type": "object"})

    def test_chat_completion_converts_back_to_responses_shape(self):
        converted = provider.chat_to_responses_payload({
            "choices": [{"message": {"content": "```json\n{\"ok\":true}\n```"}}]
        })
        text = converted["output"][0]["content"][0]["text"]
        self.assertEqual(json.loads(text), {"ok": True})
        self.assertTrue(converted["provider_bridge"])

    def test_router_uses_gemini_key_instead_of_openai_bearer(self):
        with tempfile.TemporaryDirectory() as td:
            old_state = provider.STATE
            old_config = provider.CONFIG_PATH
            old_secret = provider.SECRET_PATH
            old_urlopen = provider._ORIGINAL_URLOPEN
            provider.STATE = Path(td)
            provider.CONFIG_PATH = provider.STATE / "config.json"
            provider.SECRET_PATH = provider.STATE / "secrets.json"
            provider.CONFIG_PATH.write_text(json.dumps({"ai_provider": "gemini", "model": "gemini-test"}), encoding="utf-8")
            provider.SECRET_PATH.write_text(json.dumps({"gemini_api_key": "gemini-secret"}), encoding="utf-8")
            seen = {}

            def fake_urlopen(req, timeout=None, **kwargs):
                seen["url"] = req.full_url
                seen["authorization"] = req.headers.get("Authorization")
                seen["body"] = json.loads(req.data.decode("utf-8"))
                return FakeResponse({"choices": [{"message": {"content": "{\"ok\":true}"}}]})

            provider._ORIGINAL_URLOPEN = fake_urlopen
            try:
                req = urllib.request.Request(
                    provider.OPENAI_RESPONSES_URL,
                    data=json.dumps({
                        "model": "gpt-test",
                        "input": "hello",
                        "text": {"format": {"type": "json_schema", "name": "x", "schema": {"type": "object"}, "strict": True}},
                    }).encode("utf-8"),
                    headers={"Authorization": "Bearer openai-secret"},
                )
                response = provider.routed_urlopen(req)
                self.assertIn("generativelanguage.googleapis.com", seen["url"])
                self.assertEqual(seen["authorization"], "Bearer gemini-secret")
                self.assertNotIn("openai-secret", json.dumps(seen))
                self.assertTrue(json.loads(response.read())["provider_bridge"])
            finally:
                provider._ORIGINAL_URLOPEN = old_urlopen
                provider.STATE = old_state
                provider.CONFIG_PATH = old_config
                provider.SECRET_PATH = old_secret


if __name__ == "__main__":
    unittest.main()
