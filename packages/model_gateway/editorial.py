"""Opt-in editorial model transport; policy and tool execution stay in the backend.

No backend imports, environment-provided endpoint, logging, or automatic fallback.
Official DeepSeek compatibility is tested independently from the intake adapter.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
from typing import Any

import httpx

from .gateway import GatewayError, Telemetry, _usage

ENDPOINT = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 524_288
MAX_TOOL_CALLS = 4


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError("nonfinite_json_value")


def validate_completion(data: Any) -> dict[str, Any]:
    """Normalize protocol data; the caller must still allowlist and validate tools."""
    try:
        if not isinstance(data, dict):
            raise ValueError
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError
        choice = choices[0]
        finish = choice["finish_reason"]
        if finish not in {"stop", "tool_calls"}:
            raise ValueError
        message = choice["message"]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError
        if content and len(content) > 32_000:
            raise ValueError
        raw_calls = message.get("tool_calls")
        if raw_calls is None:
            raw_calls = []
        if not isinstance(raw_calls, list) or len(raw_calls) > MAX_TOOL_CALLS:
            raise ValueError
        if bool(raw_calls) != (finish == "tool_calls"):
            raise ValueError
        calls = []
        ids = set()
        for call in raw_calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise ValueError
            call_id = call["id"]
            if (
                not isinstance(call_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id)
                or call_id in ids
            ):
                raise ValueError
            ids.add(call_id)
            function = call["function"]
            name = function["name"]
            arguments = function["arguments"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
                raise ValueError
            if not isinstance(arguments, str) or len(arguments) > 24_000:
                raise ValueError
            parsed = json.loads(
                arguments, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
            )
            if not isinstance(parsed, dict):
                raise ValueError
            calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
        if not calls and not (content and content.strip()):
            raise ValueError
        normalized_message: dict[str, Any] = {"role": "assistant", "content": content}
        if calls:
            normalized_message["tool_calls"] = calls
        input_tokens, output_tokens = _usage(data)
        return {
            "choices": [{"message": normalized_message, "finish_reason": finish}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
        }
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        raise GatewayError("invalid_editorial_model_response") from None


def _tls_context() -> ssl.SSLContext:
    # create_default_context() honors SSLKEYLOGFILE; a dedicated context does not.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    return context


class EditorialMockProvider:
    """Marker; deterministic local replies remain in the publishing application."""

    name = "mock"
    model = "contextual-simulator-v1"
    last_telemetry: Telemetry | None = None

    def completion(self, messages: list[dict], tools: list[dict]) -> dict:
        raise GatewayError("editorial_mock_runtime_required")


class EditorialDeepSeekProvider:
    name = "deepseek"
    model = MODEL

    def __init__(self, *, live_enabled: bool = False, transport: httpx.BaseTransport | None = None):
        if not live_enabled:
            raise GatewayError("editorial_live_access_requires_opt_in")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if (
            not key
            or key != key.strip()
            or "\n" in key
            or "\r" in key
            or key.lower().startswith(("mock", "test", "replace", "your"))
        ):
            raise GatewayError("fresh_deepseek_key_required")
        self._key = key
        self._transport = transport
        self.last_telemetry: Telemetry | None = None

    def completion(self, messages: list[dict], tools: list[dict]) -> dict:
        started = time.monotonic()
        raw_usage: dict = {}
        try:
            payload = json.dumps(
                {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "required" if tools else "none",
                    "stream": False,
                    "max_tokens": 2048,
                    "thinking": {"type": "disabled"},
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
            if len(payload) > MAX_REQUEST_BYTES:
                raise GatewayError("editorial_model_request_too_large")
            with httpx.Client(
                timeout=httpx.Timeout(15, connect=5, pool=5),
                verify=_tls_context(),
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                with client.stream(
                    "POST",
                    ENDPOINT,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._key}",
                    },
                    content=payload,
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise GatewayError("editorial_model_response_too_large")
                        body.extend(chunk)
            data = json.loads(body)
            raw_usage = data if isinstance(data, dict) else {}
            result = validate_completion(data)
            input_tokens, output_tokens = _usage(result)
            self.last_telemetry = Telemetry(
                self.name,
                self.model,
                True,
                int((time.monotonic() - started) * 1000),
                input_tokens,
                output_tokens,
            )
            return result
        except (httpx.HTTPError, ValueError, TypeError, RecursionError, GatewayError) as exc:
            code = (
                str(exc) if isinstance(exc, GatewayError) else "editorial_provider_request_failed"
            )
            if isinstance(exc, httpx.HTTPStatusError):
                code = {
                    401: "editorial_provider_authentication_failed",
                    402: "editorial_provider_insufficient_balance",
                    429: "editorial_provider_rate_limited",
                    500: "editorial_provider_unavailable",
                    503: "editorial_provider_unavailable",
                }.get(exc.response.status_code, "editorial_provider_request_failed")
            input_tokens, output_tokens = _usage(raw_usage)
            self.last_telemetry = Telemetry(
                self.name,
                self.model,
                False,
                int((time.monotonic() - started) * 1000),
                input_tokens,
                output_tokens,
                error_code=code,
            )
            raise GatewayError(code) from None


def get_editorial_provider() -> EditorialMockProvider | EditorialDeepSeekProvider:
    selected = os.environ.get("EDITORIAL_MODEL_PROVIDER", "mock")
    if selected == "mock":
        return EditorialMockProvider()
    if selected == "deepseek":
        return EditorialDeepSeekProvider(
            live_enabled=os.environ.get("EDITORIAL_MODEL_LIVE_ENABLED", "false").lower() == "true"
        )
    raise GatewayError("unknown_editorial_model_provider")


def editorial_model_status() -> dict[str, Any]:
    """Configuration readiness only; never makes a provider call or exposes keys."""
    selected = os.environ.get("EDITORIAL_MODEL_PROVIDER", "mock")
    provider_name = selected if selected in {"mock", "deepseek"} else "unavailable"
    model = (
        MODEL
        if selected == "deepseek"
        else "contextual-simulator-v1"
        if selected == "mock"
        else None
    )
    try:
        provider = get_editorial_provider()
        return {"provider": provider.name, "model": provider.model, "available": True}
    except GatewayError as exc:
        return {
            "provider": provider_name,
            "model": model,
            "available": False,
            "error_code": str(exc),
        }
