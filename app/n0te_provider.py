from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from n0te_state import atomic_write_json

STATE = Path.home() / ".n0te-ableton-ai"
CONFIG_PATH = STATE / "config.json"
SECRET_PATH = STATE / "secrets.json"
HERE = Path(__file__).resolve().parent
SWITCHBOARD_HTML = HERE / "static" / "provider_switchboard.html"
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 8767
SWITCHBOARD_URL = f"http://{CONTROL_HOST}:{CONTROL_PORT}/"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
KEYCHAIN_SERVICE = "N0TE_Ableton_AI_OpenAI"

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "default_model": "gpt-5.6"},
    "gemini": {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-3.6-flash"},
    "ollama": {"label": "Ollama Local", "base_url": "http://127.0.0.1:11434/v1", "default_model": ""},
    "custom": {"label": "Custom OpenAI-compatible", "base_url": "", "default_model": ""},
}

_ORIGINAL_URLOPEN = urllib.request.urlopen
_INSTALL_LOCK = threading.Lock()
_INSTALLED = False
_CONTROL_SERVER: ThreadingHTTPServer | None = None
_STATE_LOCK = threading.RLock()


class ProviderUnavailableError(OSError):
    pass


class _MemoryResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200):
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status = status
        self.code = status
        self.headers = {"Content-Type": "application/json"}

    def read(self, amt: int = -1) -> bytes:
        return self._body if amt is None or amt < 0 else self._body[:amt]

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_secret(name: str, value: str) -> None:
    value = str(value or "").strip()
    if not value:
        return
    with _STATE_LOCK:
        STATE.mkdir(parents=True, exist_ok=True)
        secrets = _load_json(SECRET_PATH)
        secrets[name] = value
        atomic_write_json(SECRET_PATH, secrets, mode=0o600)
        try:
            SECRET_PATH.chmod(0o600)
        except OSError:
            pass


def _store_openai_key(key: str) -> None:
    key = str(key or "").strip()
    if not key:
        return
    if sys.platform == "darwin":
        try:
            cp = subprocess.run(
                ["security", "add-generic-password", "-U", "-a", os.environ.get("USER", ""), "-s", KEYCHAIN_SERVICE, "-w", key],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if cp.returncode == 0:
                return
        except Exception:
            pass
    STATE.mkdir(parents=True, exist_ok=True)
    key_file = STATE / "api_key"
    key_file.write_text(key, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass


def _openai_key() -> str:
    env = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if env:
        return env
    if sys.platform == "darwin":
        try:
            cp = subprocess.run(
                ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if cp.returncode == 0 and cp.stdout.strip():
                return cp.stdout.strip()
        except Exception:
            pass
    key_file = STATE / "api_key"
    try:
        return key_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _secret(name: str, env_name: str = "") -> str:
    if env_name and os.environ.get(env_name):
        return str(os.environ.get(env_name) or "").strip()
    return str(_load_json(SECRET_PATH).get(name) or "").strip()


def provider_config() -> dict[str, Any]:
    config = _load_json(CONFIG_PATH)
    provider = str(config.get("ai_provider") or "openai").strip().lower()
    if provider not in PROVIDER_PRESETS:
        provider = "openai"
    preset = PROVIDER_PRESETS[provider]
    model = str(config.get("model") or preset["default_model"]).strip()
    raw_base = str(config.get("ai_base_url") or preset["base_url"]).strip()
    base_url = normalize_base_url(raw_base) if raw_base else ""
    return {
        "provider": provider,
        "label": preset["label"],
        "model": model,
        "base_url": base_url,
        "switchboard_url": SWITCHBOARD_URL,
    }


def provider_key(provider: str) -> str:
    provider = str(provider or "").lower()
    if provider == "openai":
        return _openai_key()
    if provider == "gemini":
        return _secret("gemini_api_key", "GEMINI_API_KEY")
    if provider == "ollama":
        return ""
    if provider == "custom":
        return _secret("custom_api_key", "N0TE_CUSTOM_API_KEY")
    return ""


def provider_status() -> dict[str, Any]:
    cfg = provider_config()
    key_required = cfg["provider"] not in {"ollama"}
    key_ready = bool(provider_key(cfg["provider"])) if key_required else True
    return {
        **cfg,
        "key_required": key_required,
        "key_configured": key_ready,
        "presets": PROVIDER_PRESETS,
        "paid_fallback_enabled": False,
        "note": "Provider switching is explicit. N0TE never falls back to a paid provider automatically.",
    }


def normalize_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL must not contain credentials, query parameters, or fragments.")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Plain HTTP is allowed only for local providers. Use HTTPS for remote providers.")
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Base URL must be an http(s) URL.")
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def _provider_endpoint(provider: str, base_url: str = "") -> str:
    provider = str(provider or "").lower()
    if provider not in PROVIDER_PRESETS:
        raise ValueError(f"Unsupported provider: {provider}")
    raw = base_url or PROVIDER_PRESETS[provider]["base_url"]
    endpoint = normalize_base_url(raw)
    if not endpoint:
        raise ValueError("A base URL is required for a custom provider.")
    return endpoint


def _request_url(req_or_url: Any) -> str:
    return str(getattr(req_or_url, "full_url", req_or_url) or "")


def _request_body(req_or_url: Any, data: Any) -> bytes | None:
    if data is not None:
        return data if isinstance(data, (bytes, bytearray)) else bytes(data)
    body = getattr(req_or_url, "data", None)
    return body if isinstance(body, (bytes, bytearray)) else None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for part in content or []:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def responses_to_chat_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    messages: list[dict[str, str]] = []
    instructions = str(payload.get("instructions") or "").strip()
    if instructions:
        messages.append({"role": "system", "content": instructions})
    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")
            if role in {"developer", "system"}:
                role = "system"
            elif role not in {"user", "assistant"}:
                role = "user"
            text = _content_text(item.get("content"))
            if text:
                messages.append({"role": role, "content": text})
    if not messages:
        messages.append({"role": "user", "content": ""})

    fmt = ((payload.get("text") or {}).get("format") or {}) if isinstance(payload.get("text"), dict) else {}
    schema_info: dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    if isinstance(fmt, dict) and fmt.get("type") == "json_schema" and isinstance(fmt.get("schema"), dict):
        schema_info = {
            "name": str(fmt.get("name") or "n0te_response"),
            "schema": fmt["schema"],
            "strict": bool(fmt.get("strict", True)),
        }
        response_format = {"type": "json_schema", "json_schema": schema_info}

    chat: dict[str, Any] = {
        "model": str(payload.get("model") or "").strip(),
        "messages": messages,
        "temperature": 0.2,
    }
    max_tokens = payload.get("max_output_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        chat["max_tokens"] = max_tokens
    if response_format:
        chat["response_format"] = response_format
    return chat, schema_info


def _fallback_json_payload(chat_payload: dict[str, Any], schema_info: dict[str, Any]) -> dict[str, Any]:
    fallback = json.loads(json.dumps(chat_payload))
    fallback["response_format"] = {"type": "json_object"}
    schema_text = json.dumps(schema_info.get("schema") or {}, ensure_ascii=False, separators=(",", ":"))
    fallback["messages"] = list(fallback.get("messages") or []) + [{
        "role": "system",
        "content": "Return exactly one JSON object matching this JSON Schema. Do not wrap it in Markdown. Schema: " + schema_text,
    }]
    return fallback


def _authorization_headers(provider: str, key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider != "ollama" and key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:1400]
    except Exception:
        return str(exc)


def _chat_request(provider: str, base_url: str, key: str, chat_payload: dict[str, Any], schema_info: dict[str, Any] | None, timeout: float = 90) -> dict[str, Any]:
    endpoint = _provider_endpoint(provider, base_url)
    url = endpoint + "/chat/completions"

    def send(body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=_authorization_headers(provider, key),
            method="POST",
        )
        with _ORIGINAL_URLOPEN(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        return send(chat_payload)
    except urllib.error.HTTPError as exc:
        detail = _read_http_error(exc)
        if schema_info and exc.code in {400, 404, 422}:
            try:
                return send(_fallback_json_payload(chat_payload, schema_info))
            except urllib.error.HTTPError as fallback_exc:
                detail = _read_http_error(fallback_exc)
                raise ProviderUnavailableError(
                    f"{PROVIDER_PRESETS[provider]['label']} API error {fallback_exc.code}: {detail}. Switch provider at {SWITCHBOARD_URL}"
                ) from fallback_exc
        raise ProviderUnavailableError(
            f"{PROVIDER_PRESETS[provider]['label']} API error {exc.code}: {detail}. Switch provider at {SWITCHBOARD_URL}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, ProviderUnavailableError):
            raise
        raise ProviderUnavailableError(
            f"{PROVIDER_PRESETS[provider]['label']} is unavailable: {exc}. Switch provider at {SWITCHBOARD_URL}"
        ) from exc


def _message_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ProviderUnavailableError("Provider returned no choices.")
    content = ((choices[0] or {}).get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return ""


def _clean_json_text(text: str) -> str:
    value = str(text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    json.loads(value)
    return value


def chat_to_responses_payload(chat_response: dict[str, Any]) -> dict[str, Any]:
    text = _clean_json_text(_message_content(chat_response))
    return {
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "provider_bridge": True,
    }


def routed_urlopen(req_or_url: Any, data: Any = None, timeout: Any = socket._GLOBAL_DEFAULT_TIMEOUT, *args: Any, **kwargs: Any):
    if _request_url(req_or_url).rstrip("/") != OPENAI_RESPONSES_URL:
        return _ORIGINAL_URLOPEN(req_or_url, data=data, timeout=timeout, *args, **kwargs)
    cfg = provider_config()
    if cfg["provider"] == "openai":
        return _ORIGINAL_URLOPEN(req_or_url, data=data, timeout=timeout, *args, **kwargs)
    body = _request_body(req_or_url, data)
    if not body:
        raise ProviderUnavailableError("N0TE provider router received an empty model request.")
    payload = json.loads(body.decode("utf-8"))
    payload["model"] = cfg["model"] or payload.get("model")
    key = provider_key(cfg["provider"])
    if cfg["provider"] != "ollama" and not key:
        raise ProviderUnavailableError(
            f"{cfg['label']} API key is not configured. Open {SWITCHBOARD_URL} to configure or switch providers."
        )
    chat_payload, schema_info = responses_to_chat_payload(payload)
    request_timeout = 90 if timeout is socket._GLOBAL_DEFAULT_TIMEOUT else timeout
    chat_response = _chat_request(cfg["provider"], cfg["base_url"], key, chat_payload, schema_info, timeout=request_timeout)
    return _MemoryResponse(chat_to_responses_payload(chat_response))


def _models_for(provider: str, base_url: str, key: str, timeout: float = 15) -> list[str]:
    endpoint = _provider_endpoint(provider, base_url)
    req = urllib.request.Request(endpoint + "/models", headers=_authorization_headers(provider, key), method="GET")
    try:
        with _ORIGINAL_URLOPEN(req, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderUnavailableError(f"Model listing failed ({exc.code}): {_read_http_error(exc)}") from exc
    rows = raw.get("data") if isinstance(raw, dict) else None
    result = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("id"):
            result.append(str(row["id"]))
    return sorted(dict.fromkeys(result))


def _test_provider(provider: str, model: str, base_url: str, key: str) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "provider": {"type": "string"}},
        "required": ["ok", "provider"],
        "additionalProperties": False,
    }
    chat = {
        "model": model,
        "messages": [{"role": "user", "content": "Return JSON confirming the provider connection works."}],
        "temperature": 0,
        "max_tokens": 80,
        "response_format": {"type": "json_schema", "json_schema": {"name": "n0te_provider_test", "schema": schema, "strict": True}},
    }
    raw = _chat_request(provider, base_url, key, chat, {"name": "n0te_provider_test", "schema": schema, "strict": True}, timeout=30)
    parsed = json.loads(_clean_json_text(_message_content(raw)))
    return {"ok": bool(parsed.get("ok")), "provider": provider, "model": model}


def _update_provider_settings(payload: dict[str, Any]) -> dict[str, Any]:
    provider = str(payload.get("provider") or "openai").strip().lower()
    if provider not in PROVIDER_PRESETS:
        raise ValueError("Unknown provider.")
    model = str(payload.get("model") or PROVIDER_PRESETS[provider]["default_model"]).strip()
    base_url = str(payload.get("base_url") or PROVIDER_PRESETS[provider]["base_url"]).strip()
    if provider == "custom" and not base_url:
        raise ValueError("Custom provider requires a base URL.")
    normalized = _provider_endpoint(provider, base_url)
    key = str(payload.get("api_key") or "").strip()
    if key:
        if provider == "openai":
            _store_openai_key(key)
        elif provider == "gemini":
            _save_secret("gemini_api_key", key)
        elif provider == "custom":
            _save_secret("custom_api_key", key)
    with _STATE_LOCK:
        STATE.mkdir(parents=True, exist_ok=True)
        config = _load_json(CONFIG_PATH)
        config["ai_provider"] = provider
        config["ai_base_url"] = normalized if provider == "custom" else ""
        if model:
            config["model"] = model
        atomic_write_json(CONFIG_PATH, config)
    return provider_status()


class ProviderControlHandler(BaseHTTPRequestHandler):
    server_version = "N0TEProvider/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, value: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            raise ValueError("Invalid Content-Length")
        if size < 0 or size > 128 * 1024:
            raise ValueError("Request too large")
        value = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
        return value if isinstance(value, dict) else {}

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            try:
                body = SWITCHBOARD_HTML.read_bytes()
            except OSError:
                body = b"N0TE provider switchboard file is missing."
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/status":
            return self._json({"ok": True, "status": provider_status()})
        self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self) -> None:
        try:
            data = self._body()
            if self.path == "/save":
                return self._json({"ok": True, "status": _update_provider_settings(data)})
            if self.path in {"/models", "/test"}:
                provider = str(data.get("provider") or provider_config()["provider"]).lower()
                base_url = str(data.get("base_url") or PROVIDER_PRESETS.get(provider, {}).get("base_url") or "")
                model = str(data.get("model") or PROVIDER_PRESETS.get(provider, {}).get("default_model") or "")
                key = str(data.get("api_key") or provider_key(provider)).strip()
                if provider != "ollama" and not key:
                    raise ValueError("API key is required for this provider.")
                if self.path == "/models":
                    return self._json({"ok": True, "models": _models_for(provider, base_url, key)})
                if not model:
                    raise ValueError("Choose a model before testing.")
                return self._json({"ok": True, "result": _test_provider(provider, model, base_url, key)})
            return self._json({"ok": False, "error": "Not found"}, 404)
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)


def _start_control_server() -> None:
    global _CONTROL_SERVER
    try:
        server = ThreadingHTTPServer((CONTROL_HOST, CONTROL_PORT), ProviderControlHandler)
    except OSError as exc:
        print(f"N0TE AI provider switchboard unavailable on {SWITCHBOARD_URL}: {exc}", file=sys.stderr)
        return
    _CONTROL_SERVER = server
    thread = threading.Thread(target=server.serve_forever, name="n0te-provider-switchboard", daemon=True)
    thread.start()
    print(f"N0TE AI provider switchboard: {SWITCHBOARD_URL}", flush=True)


def install_provider_router(start_switchboard: bool = True) -> None:
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        urllib.request.urlopen = routed_urlopen
        _INSTALLED = True
        if start_switchboard:
            _start_control_server()
