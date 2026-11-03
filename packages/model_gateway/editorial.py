"""Opt-in editorial model transport; policy and tool execution stay in the backend.

No backend imports, environment-provided endpoint, logging, or automatic fallback.
Official DeepSeek compatibility is tested independently from the intake adapter.
"""

from __future__ import annotations

import asyncio
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
TURN_TIMEOUT_SECONDS = 60
READ_TIMEOUT_SECONDS = 30
MAX_TRANSIENT_RETRIES = 1
RETRY_DELAY_SECONDS = 0.5
SAFE_ERROR_CODES = frozenset(
    {
        "invalid_editorial_model_response",
        "editorial_mock_runtime_required",
        "editorial_live_access_requires_opt_in",
        "fresh_deepseek_key_required",
        "unknown_editorial_model_provider",
        "editorial_model_request_too_large",
        "editorial_model_response_too_large",
        "editorial_provider_request_failed",
        "editorial_provider_timeout",
        "editorial_provider_deadline",
        "editorial_provider_authentication_failed",
        "editorial_provider_insufficient_balance",
        "editorial_provider_rate_limited",
        "editorial_provider_unavailable",
    }
)


def safe_error_code(value: object) -> str:
    """Only exact internal codes may cross into persisted diagnostics or status."""
    if isinstance(value, GatewayError):
        value = value.args[0] if len(value.args) == 1 else None
    return (
        value
        if type(value) is str and value in SAFE_ERROR_CODES
        else "editorial_provider_request_failed"
    )


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

    def __init__(
        self, *, live_enabled: bool = False, transport: httpx.AsyncBaseTransport | None = None
    ):
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
        self.last_attempt_telemetry: list[Telemetry] = []
        self._deadline: float | None = None
        self._retries = 0
        self.before_attempt = None

    def check_deadline(self):
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise GatewayError("editorial_provider_deadline")

    def set_deadline(self, deadline: float):
        self._deadline = min(self._deadline or deadline, deadline)

    def _metric(self, started, success, usage, code=None):
        input_tokens, output_tokens = _usage(usage)
        self.last_telemetry = Telemetry(
            self.name,
            self.model,
            success,
            int((time.monotonic() - started) * 1000),
            input_tokens,
            output_tokens,
            error_code=code,
        )
        self.last_attempt_telemetry.append(self.last_telemetry)

    async def _attempt(self, payload: bytes) -> dict:
        self.check_deadline()
        remaining = self._deadline - time.monotonic()
        # Read timeout alone can be kept alive indefinitely by blank heartbeat
        # chunks. Cancellation bounds the complete network attempt, including
        # connection setup, headers and body, by the shared turn deadline.
        async with asyncio.timeout(remaining):
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    min(READ_TIMEOUT_SECONDS, remaining), connect=5, write=5, pool=5
                ),
                verify=_tls_context(),
                trust_env=False,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                async with client.stream(
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
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise GatewayError("editorial_model_response_too_large")
                        body.extend(chunk)
        return json.loads(body)

    async def _completion(self, payload: bytes) -> dict:
        while True:
            # Business authorization errors stay business errors, rather than
            # being translated into a retryable provider transport failure.
            if self.before_attempt is not None:
                self.before_attempt()
            started = time.monotonic()
            usage = {}
            try:
                data = await self._attempt(payload)
                usage = data if isinstance(data, dict) else {}
                result = validate_completion(data)
                self.check_deadline()
                self._metric(started, True, usage)
                return result
            except (
                httpx.HTTPError,
                TimeoutError,
                ValueError,
                TypeError,
                RecursionError,
                GatewayError,
            ) as error:
                code = safe_error_code(error)
                retryable = isinstance(
                    error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
                )
                if isinstance(error, TimeoutError):
                    code = "editorial_provider_deadline"
                elif isinstance(error, httpx.TimeoutException):
                    code = "editorial_provider_timeout"
                elif isinstance(error, httpx.HTTPStatusError):
                    status = error.response.status_code
                    retryable = status in {500, 502, 503, 504}
                    code = {
                        401: "editorial_provider_authentication_failed",
                        402: "editorial_provider_insufficient_balance",
                        429: "editorial_provider_rate_limited",
                        500: "editorial_provider_unavailable",
                        502: "editorial_provider_unavailable",
                        503: "editorial_provider_unavailable",
                        504: "editorial_provider_unavailable",
                    }.get(status, "editorial_provider_request_failed")
                self._metric(started, False, usage, code)
                if (
                    retryable
                    and self._retries < MAX_TRANSIENT_RETRIES
                    and self._deadline - time.monotonic() > RETRY_DELAY_SECONDS + 1
                ):
                    # Only inference is repeated, with byte-identical input.
                    # No backend tool has executed for this failed attempt.
                    self._retries += 1
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
                raise GatewayError(code) from None

    def completion(self, messages: list[dict], tools: list[dict]) -> dict:
        """Sync worker entry point; one instance and one recovery retry per turn."""
        self.last_telemetry = None
        self.last_attempt_telemetry = []
        if self._deadline is None:
            self._deadline = time.monotonic() + TURN_TIMEOUT_SECONDS
        started = time.monotonic()
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
        except (ValueError, TypeError, RecursionError, GatewayError) as error:
            code = safe_error_code(error)
            self._metric(started, False, {}, code)
            raise GatewayError(code) from None
        return asyncio.run(self._completion(payload))


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
            "error_code": safe_error_code(exc),
        }
