from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


class GeminiStructuredOutputError(ValueError):
    def __init__(self, detail: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(detail)
        self.diagnostics = diagnostics or {}


def _model_name(value: str) -> str:
    model = str(value or "").strip()
    if model.startswith("models/"):
        model = model.split("/", 1)[1]
    if not model:
        raise ValueError("Gemini model is not configured.")
    return model


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts)


def _native_payload(
    chat_payload: dict[str, Any],
    schema_info: dict[str, Any] | None,
    *,
    model: str,
    retry: bool = False,
) -> dict[str, Any]:
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in chat_payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        text = _message_text(message).strip()
        if not text:
            continue
        role = str(message.get("role") or "user")
        if role == "system":
            system_parts.append(text)
            continue
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    generation: dict[str, Any] = {"temperature": 0.0 if schema_info else float(chat_payload.get("temperature", 0.2) or 0.0)}
    max_tokens = chat_payload.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        generation["maxOutputTokens"] = min(8192, max_tokens * 2) if retry else max_tokens
    if schema_info and isinstance(schema_info.get("schema"), dict):
        generation["responseMimeType"] = "application/json"
        generation["responseJsonSchema"] = schema_info["schema"]
        if model.startswith("gemini-3"):
            generation["thinkingConfig"] = {"thinkingLevel": "minimal" if retry else "low"}

    if retry:
        system_parts.append(
            "A previous model candidate for this same request was discarded because it was not valid JSON. "
            "Generate a fresh answer from the original request. Return exactly one JSON object matching the supplied schema. "
            "Do not include Markdown or commentary outside the JSON. Keep strings concise. "
            "For every field whose schema type is string, encode any nested JSON as a valid escaped JSON string."
        )

    payload: dict[str, Any] = {"contents": contents, "generationConfig": generation}
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


def _candidate_diagnostics(raw: dict[str, Any]) -> dict[str, Any]:
    candidates = raw.get("candidates") or []
    candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    parts = (((candidate.get("content") or {}).get("parts") or []) if isinstance(candidate, dict) else [])
    usage = raw.get("usageMetadata") if isinstance(raw.get("usageMetadata"), dict) else {}
    return {
        "finish_reason": str(candidate.get("finishReason") or ""),
        "finish_message": str(candidate.get("finishMessage") or ""),
        "part_count": len(parts),
        "text_part_count": sum(1 for part in parts if isinstance(part, dict) and part.get("text")),
        "thought_text_part_count": sum(1 for part in parts if isinstance(part, dict) and part.get("text") and bool(part.get("thought"))),
        "candidate_tokens": usage.get("candidatesTokenCount"),
        "thought_tokens": usage.get("thoughtsTokenCount"),
        "total_tokens": usage.get("totalTokenCount"),
    }


def _response_text(raw: dict[str, Any]) -> str:
    candidates = raw.get("candidates") or []
    if not candidates:
        raise GeminiStructuredOutputError(
            f"Gemini returned no candidates. Prompt feedback: {raw.get('promptFeedback') or {}}",
            _candidate_diagnostics(raw),
        )
    candidate = candidates[0] or {}
    diagnostics = _candidate_diagnostics(raw)
    finish_reason = str(candidate.get("finishReason") or "").upper()
    if finish_reason and finish_reason != "STOP":
        raise GeminiStructuredOutputError(
            f"Gemini candidate did not finish normally (finishReason={finish_reason}).",
            diagnostics,
        )

    parts = (((candidate.get("content") or {}).get("parts") or []))
    answer_parts = [
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and part.get("text") and not bool(part.get("thought"))
    ]
    if not answer_parts:
        raise GeminiStructuredOutputError("Gemini returned no non-thought text content.", diagnostics)

    for text in answer_parts:
        value = text.strip()
        if not value:
            continue
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            pass

    value = "".join(answer_parts).strip()
    if not value:
        raise GeminiStructuredOutputError("Gemini returned empty structured text.", diagnostics)
    try:
        json.loads(value)
    except json.JSONDecodeError as exc:
        raise GeminiStructuredOutputError(str(exc), diagnostics) from exc
    return value


def _send_native(provider_module: Any, key: str, model: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = f"{GEMINI_API_ROOT}/models/{urllib.parse.quote(model, safe='-._')}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with provider_module._ORIGINAL_URLOPEN(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = provider_module._read_http_error(exc)
        raise provider_module.ProviderUnavailableError(
            f"Google Gemini API error {exc.code}: {detail}. Switch provider at {provider_module.SWITCHBOARD_URL}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise provider_module.ProviderUnavailableError(
            f"Google Gemini is unavailable or returned an invalid transport response: {exc}. Switch provider at {provider_module.SWITCHBOARD_URL}"
        ) from exc


def _diagnostic_text(error: GeminiStructuredOutputError) -> str:
    diag = error.diagnostics or {}
    fields = []
    for key in ("finish_reason", "finish_message", "part_count", "text_part_count", "thought_text_part_count", "candidate_tokens", "thought_tokens", "total_tokens"):
        value = diag.get(key)
        if value not in (None, "", 0):
            fields.append(f"{key}={value}")
    suffix = ", ".join(fields)
    return f"{error}" + (f" [{suffix}]" if suffix else "")


def gemini_native_chat(provider_module: Any, key: str, chat_payload: dict[str, Any], schema_info: dict[str, Any] | None, timeout: float = 90) -> dict[str, Any]:
    model = _model_name(str(chat_payload.get("model") or ""))
    first_raw = _send_native(provider_module, key, model, _native_payload(chat_payload, schema_info, model=model), timeout)
    first_failure: GeminiStructuredOutputError | None = None
    try:
        text = _response_text(first_raw)
        return {"choices": [{"message": {"content": text}}], "provider_bridge": "gemini-native"}
    except GeminiStructuredOutputError as exc:
        first_failure = exc
        if not schema_info:
            raise provider_module.ProviderUnavailableError(
                "Google Gemini returned unusable text output. "
                f"Switch provider at {provider_module.SWITCHBOARD_URL}. Detail: {_diagnostic_text(exc)}"
            ) from exc

    second_raw = _send_native(
        provider_module,
        key,
        model,
        _native_payload(chat_payload, schema_info, model=model, retry=True),
        timeout,
    )
    try:
        text = _response_text(second_raw)
    except GeminiStructuredOutputError as second_error:
        first_detail = _diagnostic_text(first_failure) if first_failure is not None else "unknown first structured-output failure"
        raise provider_module.ProviderUnavailableError(
            "Google Gemini did not return valid structured JSON after one fresh retry. "
            "N0TE discarded both candidates and refused to guess-repair a safety-critical response. "
            f"Retry later or switch provider at {provider_module.SWITCHBOARD_URL}. "
            f"First: {first_detail} | Second: {_diagnostic_text(second_error)}"
        ) from second_error
    return {"choices": [{"message": {"content": text}}], "provider_bridge": "gemini-native-retry"}


def install(provider_module: Any) -> None:
    if getattr(provider_module, "_GEMINI_NATIVE_INSTALLED", False):
        return
    original = provider_module._chat_request

    def routed(provider: str, base_url: str, key: str, chat_payload: dict[str, Any], schema_info: dict[str, Any] | None, timeout: float = 90) -> dict[str, Any]:
        if str(provider or "").lower() == "gemini":
            return gemini_native_chat(provider_module, key, chat_payload, schema_info, timeout)
        return original(provider, base_url, key, chat_payload, schema_info, timeout)

    provider_module._chat_request = routed
    provider_module._GEMINI_NATIVE_INSTALLED = True
