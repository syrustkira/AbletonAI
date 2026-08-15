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
    def provider(self, response_payloads):
        payloads = list(response_payloads) if isinstance(response_payloads, list) else [response_payloads]
        seen = {"requests": []}
        def urlopen(req, timeout=0):
            if not payloads:
                raise AssertionError("Unexpected extra Gemini request")
            row = {
                "url": req.full_url,
                "headers": {k.lower(): v for k, v in req.header_items()},
                "body": json.loads(req.data.decode("utf-8")),
                "timeout": timeout,
            }
            seen["requests"].append(row)
            return MemoryResponse(payloads.pop(0))
        module = SimpleNamespace(
            _ORIGINAL_URLOPEN=urlopen,
            _read_http_error=lambda exc: "http error",
            ProviderUnavailableError=RuntimeError,
            SWITCHBOARD_URL="http://127.0.0.1:8767/",
        )
        return module, seen

    def schema(self):
        return {
            "type": "object",
            "properties": {"decision": {"type": "string"}, "actions": {"type": "array", "items": {"type": "object"}}},
            "required": ["decision", "actions"],
            "additionalProperties": False,
        }

    def chat(self, max_tokens=700):
        return {
            "model": "gemini-3.5-flash",
            "messages": [
                {"role": "system", "content": "Return a N0TE decision."},
                {"role": "user", "content": "Inspect the selected track."},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }

    def test_native_gemini_uses_json_schema_and_google_key_header(self):
        provider, seen = self.provider({
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep","actions":[]}'}]}}]
        })
        schema = self.schema()
        result = gemini.gemini_native_chat(provider, "google-secret", self.chat(), {"name": "reply", "schema": schema, "strict": True}, 12)
        self.assertEqual(result["provider_bridge"], "gemini-native")
        request = seen["requests"][0]
        self.assertIn("models/gemini-3.5-flash:generateContent", request["url"])
        self.assertEqual(request["headers"].get("x-goog-api-key"), "google-secret")
        self.assertNotIn("authorization", request["headers"])
        self.assertEqual(request["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(request["body"]["generationConfig"]["responseJsonSchema"], schema)
        self.assertEqual(request["body"]["generationConfig"]["temperature"], 0.0)
        self.assertEqual(request["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(request["body"]["generationConfig"]["maxOutputTokens"], 700)
        self.assertEqual(request["body"]["systemInstruction"]["parts"][0]["text"], "Return a N0TE decision.")

    def test_thought_text_part_is_not_merged_into_structured_answer(self):
        provider, seen = self.provider({
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [
                    {"text": "internal summary that is not JSON", "thought": True},
                    {"text": '{"decision":"keep","actions":[]}', "thoughtSignature": "opaque"},
                ]},
            }]
        })
        result = gemini.gemini_native_chat(provider, "google-secret", self.chat(), {"name": "reply", "schema": self.schema(), "strict": True}, 12)
        self.assertEqual(len(seen["requests"]), 1)
        self.assertEqual(json.loads(result["choices"][0]["message"]["content"])["decision"], "keep")

    def test_invalid_first_candidate_is_discarded_and_fresh_retry_can_succeed(self):
        provider, seen = self.provider([
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep" "actions":[]}'}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep","actions":[]}'}]}}]},
        ])
        result = gemini.gemini_native_chat(provider, "google-secret", self.chat(), {"name": "reply", "schema": self.schema(), "strict": True}, 12)
        self.assertEqual(result["provider_bridge"], "gemini-native-retry")
        self.assertEqual(len(seen["requests"]), 2)
        retry = seen["requests"][1]["body"]
        self.assertEqual(retry["generationConfig"]["thinkingConfig"]["thinkingLevel"], "minimal")
        self.assertIn("previous model candidate", retry["systemInstruction"]["parts"][0]["text"].lower())

    def test_max_tokens_candidate_retries_with_larger_output_budget(self):
        provider, seen = self.provider([
            {
                "candidates": [{"finishReason": "MAX_TOKENS", "finishMessage": "output limit", "content": {"parts": [{"text": '{"decision":"keep"'}]}}],
                "usageMetadata": {"candidatesTokenCount": 700, "totalTokenCount": 1200},
            },
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep","actions":[]}'}]}}]},
        ])
        gemini.gemini_native_chat(provider, "google-secret", self.chat(max_tokens=700), {"name": "reply", "schema": self.schema(), "strict": True}, 12)
        self.assertEqual(seen["requests"][0]["body"]["generationConfig"]["maxOutputTokens"], 700)
        self.assertEqual(seen["requests"][1]["body"]["generationConfig"]["maxOutputTokens"], 1400)

    def test_malformed_native_gemini_json_fails_closed_after_fresh_retry(self):
        provider, _ = self.provider([
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep" "actions":[]}'}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"decision":"keep", actions:[]}'}]}}]},
        ])
        with self.assertRaisesRegex(RuntimeError, "after one fresh retry"):
            gemini.gemini_native_chat(
                provider,
                "google-secret",
                self.chat(),
                {"name": "reply", "schema": self.schema(), "strict": True},
                12,
            )

    def test_malformed_failure_reports_finish_diagnostics_without_response_body(self):
        provider, _ = self.provider([
            {
                "candidates": [{"finishReason": "MAX_TOKENS", "finishMessage": "limit", "content": {"parts": [{"text": "{"}]}}],
                "usageMetadata": {"candidatesTokenCount": 700, "thoughtsTokenCount": 20, "totalTokenCount": 900},
            },
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not-json"}]}}]},
        ])
        with self.assertRaises(RuntimeError) as ctx:
            gemini.gemini_native_chat(
                provider,
                "google-secret",
                self.chat(),
                {"name": "reply", "schema": self.schema(), "strict": True},
                12,
            )
        text = str(ctx.exception)
        self.assertIn("finish_reason=MAX_TOKENS", text)
        self.assertIn("candidate_tokens=700", text)
        self.assertNotIn("google-secret", text)

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
