"""Small, explicit model boundary. The backend must recheck policy and arguments."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

TOOL_NAME = "create_test_manuscript_and_assign_screening"
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Create one synthetic test manuscript and assign editorial screening. No email or decision.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    }
]


class GatewayError(RuntimeError):
    """Safe error that never contains a secret, prompt, or provider response body."""


@dataclass(frozen=True)
class Proposal:
    tool: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    provider: str = "mock"


@dataclass(frozen=True)
class Telemetry:
    provider: str
    model: str
    success: bool
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cost_basis: str = "unknown; reconcile provider invoice"
    rework_count: int = 0
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelProvider(Protocol):
    name: str
    last_telemetry: Telemetry | None

    def propose(self, message: str) -> Proposal: ...


class MockModelProvider:
    name = "mock"
    last_telemetry: Telemetry | None = None

    def propose(self, message: str) -> Proposal:
        start = time.monotonic()
        # Intentionally narrow simulator, not a language model. Never infers arbitrary authority.
        normalized = "".join(message.split()).rstrip("。.!！")
        supported = normalized in {
            "创建一篇测试稿件，并交给编辑初筛",
            "创建一篇测试稿件,并交给编辑初筛",
            "创建一篇测试稿件并交给编辑初筛",
            "Createatestmanuscriptandassignittoeditorialscreening",
        }
        self.last_telemetry = Telemetry(
            "mock",
            "deterministic-simulator-v1",
            True,
            int((time.monotonic() - start) * 1000),
            0,
            0,
            0.0,
            "mock; no API charge",
        )
        return Proposal(TOOL_NAME if supported else None, {}, self.name)


def _usage(data: dict[str, Any]) -> tuple[int | None, int | None]:
    usage = data.get("usage") or {}

    def count(key: str) -> int | None:
        value = usage.get(key) if isinstance(usage, dict) else None
        return value if type(value) is int and value >= 0 else None

    return count("prompt_tokens"), count("completion_tokens")


def validate_proposal(data: dict[str, Any], provider: str) -> Proposal:
    """Reject extra tools/arguments rather than quietly trusting generated capabilities."""
    try:
        calls = data["choices"][0]["message"].get("tool_calls", [])
        if not calls:
            return Proposal(None, {}, provider)
        if len(calls) != 1 or calls[0]["type"] != "function":
            raise ValueError("unexpected calls")
        function = calls[0]["function"]
        arguments = json.loads(function["arguments"])
        if function["name"] != TOOL_NAME or arguments != {}:
            raise ValueError("untrusted capability or arguments")
        return Proposal(TOOL_NAME, {}, provider)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise GatewayError("invalid_model_proposal") from exc


class ChatCompletionProvider:
    """OpenAI-shaped transport only; compatibility is verified per adapter, not assumed."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        endpoint: str,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.name = name
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self.last_telemetry: Telemetry | None = None

    def completion(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            with httpx.Client(
                timeout=45, follow_redirects=False, transport=self._transport
            ) as client:
                response = client.post(
                    f"{self.endpoint}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "max_tokens": 2048,
                        "thinking": {"type": "disabled"},
                    },
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("invalid response")
            input_tokens, output_tokens = _usage(data)
            self.last_telemetry = Telemetry(
                self.name,
                self.model,
                True,
                int((time.monotonic() - started) * 1000),
                input_tokens,
                output_tokens,
            )
            return data
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            self.last_telemetry = Telemetry(
                self.name,
                self.model,
                False,
                int((time.monotonic() - started) * 1000),
                error_code="provider_request_failed",
            )
            raise GatewayError("provider_request_failed") from exc

    def propose(self, message: str) -> Proposal:
        data = self.completion(
            [
                {
                    "role": "system",
                    "content": "Propose the sole tool only for explicit synthetic manuscript creation and screening. Refuse all other tasks. Never decide permissions, send email, or publish.",
                },
                {"role": "user", "content": message},
            ],
            TOOLS,
        )
        try:
            return validate_proposal(data, self.name)
        except GatewayError:
            if self.last_telemetry:
                self.last_telemetry = Telemetry(
                    **{
                        **self.last_telemetry.as_dict(),
                        "success": False,
                        "error_code": "invalid_model_proposal",
                    }
                )
            raise


class DeepSeekProvider(ChatCompletionProvider):
    """An explicitly opted-in, fresh environment key; official endpoint only."""

    def __init__(self, *, live_enabled: bool = False, transport: httpx.BaseTransport | None = None):
        if not live_enabled:
            raise GatewayError("live_model_access_requires_explicit_opt_in")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key or key.lower().startswith(("mock", "test", "replace", "your")):
            raise GatewayError("fresh_deepseek_key_required")
        super().__init__(
            name="deepseek",
            model="deepseek-flash",
            endpoint="https://api.deepseek.com",
            api_key=key,
            transport=transport,
        )


class LocalModelProvider(ChatCompletionProvider):
    """Reserved Ollama/vLLM interface; opt-in and loopback only, never remote secrets."""

    def __init__(
        self,
        *,
        adapter: str,
        model: str,
        endpoint: str,
        live_enabled: bool = False,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlparse(endpoint)
        if not live_enabled or adapter not in {"ollama", "vllm"}:
            raise GatewayError("local_model_access_requires_explicit_opt_in")
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise GatewayError("local_endpoint_must_be_loopback_http")
        if not model.strip():
            raise GatewayError("local_model_name_required")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise GatewayError("invalid_local_endpoint")
        super().__init__(name=adapter, model=model, endpoint=endpoint, transport=transport)


def get_provider() -> ModelProvider:
    provider = os.environ.get("MODEL_PROVIDER", "mock")
    if provider == "mock":
        return MockModelProvider()
    enabled = os.environ.get("MODEL_LIVE_ENABLED", "false").lower() == "true"
    if provider == "deepseek":
        return DeepSeekProvider(live_enabled=enabled)
    if provider in {"ollama", "vllm"}:
        return LocalModelProvider(
            adapter=provider,
            model=os.environ.get("LOCAL_MODEL", ""),
            endpoint=os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:11434/v1"),
            live_enabled=enabled,
        )
    raise GatewayError("unknown_model_provider")
