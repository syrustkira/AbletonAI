from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


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


def _native_payload(chat_payload: dict[str, Any], schema_info: dict[str, Any] | None) -> dict[str, Any]:
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
        generation["maxOutputTokens"] = max_tokens
    if schema_info and isinstance(schema_info.get("schema"), dict):
        generation["responseMimeType"] = "application/json"
        generation["responseJsonSchema"] = schema_info["schema"]

    payload: dict[str, Any] = {"contents": contents, "generationConfig": generation}
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


def _response_text(raw: dict[str, Any]) -> str:
    candidates = raw.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates. Prompt feedback: {raw.get('promptFeedback') or {}}")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text = "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise RuntimeError("Gemini returned no text content.")
    json.loads(text)
    return text


def gemini_native_chat(provider_module: Any, key: str, chat_payload: dict[str, Any], schema_info: dict[str, Any] | None, timeout: float = 90) -> dict[str, Any]:
    model = _model_name(str(chat_payload.get("model") or ""))
    url = f"{GEMINI_API_ROOT}/models/{urllib.parse.quote(model, safe='-._')}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(_native_payload(chat_payload, schema_info), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with provider_module._ORIGINAL_URLOPEN(req, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = provider_module._read_http_error(exc)
        raise provider_module.ProviderUnavailableError(
            f"Google Gemini API error {exc.code}: {detail}. Switch provider at {provider_module.SWITCHBOARD_URL}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise provider_module.ProviderUnavailableError(
            f"Google Gemini is unavailable or returned an invalid transport response: {exc}. Switch provider at {provider_module.SWITCHBOARD_URL}"
        ) from exc

    try:
        text = _response_text(raw)
    except (RuntimeError, json.JSONDecodeError) as exc:
        raise provider_module.ProviderUnavailableError(
            "Google Gemini did not return valid structured JSON. N0TE refused to guess-repair a safety-critical response. "
            f"Retry or switch provider at {provider_module.SWITCHBOARD_URL}. Detail: {exc}"
        ) from exc
    return {"choices": [{"message": {"content": text}}], "provider_bridge": "gemini-native"}


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
