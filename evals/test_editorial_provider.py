"""Network-free editorial provider compatibility and transport safety checks."""

import json
import ssl
from copy import deepcopy

import httpx
import pytest

from packages.model_gateway import GatewayError
from packages.model_gateway.editorial import (
    ENDPOINT,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    EditorialDeepSeekProvider,
    EditorialMockProvider,
    _tls_context,
    editorial_model_status,
    get_editorial_provider,
    validate_completion,
)


@pytest.fixture(autouse=True)
def clean_provider_env(monkeypatch):
    for name in ("EDITORIAL_MODEL_PROVIDER", "EDITORIAL_MODEL_LIVE_ENABLED", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def reply(*, calls=None, text="当前稿件处于修回核验阶段。", finish=None):
    message = {"role": "assistant", "content": text}
    if calls is not None:
        message["tool_calls"] = calls
    return {
        "choices": [
            {"message": message, "finish_reason": finish or ("tool_calls" if calls else "stop")}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }


def call(name="get_manuscript", arguments='{"case_id":"demo-001"}', call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def provider(monkeypatch, handle):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-editorial-credential")
    return EditorialDeepSeekProvider(live_enabled=True, transport=httpx.MockTransport(handle))


def test_defaults_and_status_are_local_without_silent_live_fallback(monkeypatch):
    assert isinstance(get_editorial_provider(), EditorialMockProvider)
    assert editorial_model_status() == {
        "provider": "mock",
        "model": "contextual-simulator-v1",
        "available": True,
    }
    with pytest.raises(GatewayError, match="^editorial_mock_runtime_required$"):
        get_editorial_provider().completion([], [])
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "deepseek")
    with pytest.raises(GatewayError, match="^editorial_live_access_requires_opt_in$"):
        get_editorial_provider()
    assert not editorial_model_status()["available"]
    monkeypatch.setenv("EDITORIAL_MODEL_LIVE_ENABLED", "true")
    assert editorial_model_status()["error_code"] == "fresh_deepseek_key_required"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-editorial-credential")
    assert editorial_model_status() == {
        "provider": "deepseek",
        "model": "deepseek-flash",
        "available": True,
    }


@pytest.mark.parametrize(
    "key", ["", "mock-token", "test-key", "replace-me", "your-secret", " x ", "x\ny"]
)
def test_missing_placeholder_or_unsafe_key_fails_closed(monkeypatch, key):
    monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    with pytest.raises(GatewayError, match="^fresh_deepseek_key_required$"):
        EditorialDeepSeekProvider(live_enabled=True)


def test_unknown_provider_status_does_not_reflect_arbitrary_configuration(monkeypatch):
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "sensitive-configuration-value")
    state = editorial_model_status()
    assert state["provider"] == "unavailable"
    assert state["error_code"] == "unknown_editorial_model_provider"
    assert "sensitive-configuration-value" not in str(state)


def test_two_request_tool_result_protocol_and_telemetry(monkeypatch):
    requests = []
    tools = [
        {
            "type": "function",
            "function": {"name": "get_manuscript", "parameters": {"type": "object"}},
        }
    ]

    def handle(request):
        assert str(request.url) == ENDPOINT
        assert request.headers["Authorization"] == "Bearer synthetic-editorial-credential"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-flash"
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["stream"] is False
        assert payload["max_tokens"] == 2048
        assert payload["tools"] == tools
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(200, json=reply(calls=[call()], text=None))
        assert payload["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"stage":"修回核验"}',
        }
        return httpx.Response(200, json=reply())

    adapter = provider(monkeypatch, handle)
    messages = [{"role": "user", "content": "目前这篇稿件在哪一步？"}]
    first = adapter.completion(messages, tools)
    messages += [
        first["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "call_1", "content": '{"stage":"修回核验"}'},
    ]
    second = adapter.completion(messages, tools)
    assert "修回核验" in second["choices"][0]["message"]["content"]
    assert len(requests) == 2
    assert all(request["tool_choice"] == "required" for request in requests)
    metrics = adapter.last_telemetry
    assert metrics.success
    assert metrics.input_tokens == 12 and metrics.output_tokens == 7
    assert metrics.cost_usd is None
    assert "synthetic-editorial-credential" not in str(metrics)
    assert "目前这篇稿件" not in str(metrics)


@pytest.mark.parametrize("status", [301, 307, 401, 402, 429, 500, 503])
def test_http_errors_and_redirects_are_sanitized_not_followed(monkeypatch, status):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(
            status, headers={"Location": "https://untrusted.example"}, text="secret-body"
        )

    adapter = provider(monkeypatch, handle)
    expected = {
        401: "editorial_provider_authentication_failed",
        402: "editorial_provider_insufficient_balance",
        429: "editorial_provider_rate_limited",
        500: "editorial_provider_unavailable",
        503: "editorial_provider_unavailable",
    }.get(status, "editorial_provider_request_failed")
    with pytest.raises(GatewayError, match=f"^{expected}$") as error:
        adapter.completion([{"role": "user", "content": "private-prompt"}], [])
    assert calls == [ENDPOINT] * (2 if status in {500, 503} else 1)
    assert error.value.__cause__ is None
    assert not adapter.last_telemetry.success
    assert "secret-body" not in str(error.value)
    assert "private-prompt" not in str(adapter.last_telemetry)


@pytest.mark.parametrize(
    "timeout", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout]
)
def test_timeout_is_sanitized(monkeypatch, timeout):
    def handle(request):
        raise timeout("sensitive timeout details", request=request)

    adapter = provider(monkeypatch, handle)
    with pytest.raises(GatewayError, match="^editorial_provider_timeout$") as error:
        adapter.completion([], [])
    assert adapter.last_telemetry.error_code == "editorial_provider_timeout"
    assert "sensitive timeout details" not in str(error.value)
    assert "sensitive timeout details" not in str(adapter.last_telemetry)


def test_unknown_gateway_failure_cannot_persist_or_return_sensitive_error(monkeypatch):
    from packages.model_gateway import editorial

    secret = "private-provider-body synthetic-credential cookie=session-value"

    def reject(data):
        raise GatewayError(secret)

    monkeypatch.setattr(editorial, "validate_completion", reject)
    adapter = provider(monkeypatch, lambda request: httpx.Response(200, json=reply()))
    with pytest.raises(GatewayError, match="^editorial_provider_request_failed$") as error:
        adapter.completion([], [])
    assert adapter.last_telemetry.error_code == "editorial_provider_request_failed"
    assert secret not in str(error.value) and secret not in str(adapter.last_telemetry)


def test_outbound_request_bound_prevents_network(monkeypatch):
    def handle(request):
        pytest.fail("oversize request should not reach transport")

    adapter = provider(monkeypatch, handle)
    with pytest.raises(GatewayError, match="^editorial_model_request_too_large$"):
        adapter.completion([{"role": "user", "content": "x" * MAX_REQUEST_BYTES}], [])


class ChunkedBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        for _ in range((MAX_RESPONSE_BYTES // 8192) + 2):
            yield b" " * 8192


def test_streaming_response_bound(monkeypatch):
    adapter = provider(monkeypatch, lambda request: httpx.Response(200, stream=ChunkedBody()))
    with pytest.raises(GatewayError, match="^editorial_model_response_too_large$"):
        adapter.completion([], [])
    assert adapter.last_telemetry.error_code == "editorial_model_response_too_large"


def test_invalid_json_and_protocol_are_safe(monkeypatch):
    for data in [b"not-json-private-response", json.dumps(reply(finish="length")).encode()]:
        adapter = provider(
            monkeypatch, lambda request, data=data: httpx.Response(200, content=data)
        )
        with pytest.raises(GatewayError):
            adapter.completion([], [])
        assert not adapter.last_telemetry.success


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"choices": []},
        {"choices": [None]},
        reply(finish="length"),
        reply(finish="content_filter"),
        reply(finish="insufficient_system_resource"),
        reply(text=None),
        reply(text="   "),
        reply(text=[{"text": "unsafe format"}]),
        reply(calls=[call()], finish="stop"),
        reply(calls=[], finish="tool_calls"),
        reply(calls=[call(arguments="[]")]),
        reply(calls=[call(arguments="not-json")]),
        reply(calls=[call(), call()]),
        reply(calls=[call(call_id="contains spaces")]),
        reply(calls=[call(name="../../bad")]),
        reply(calls=[call(call_id=f"call_{i}") for i in range(5)]),
    ],
)
def test_malformed_or_truncated_completion_is_rejected(data):
    with pytest.raises(GatewayError, match="^invalid_editorial_model_response$"):
        validate_completion(data)


def test_only_assistant_protocol_fields_returned_and_usage_validated():
    source = reply()
    source["secret_debug"] = "private-provider-field"
    source["choices"][0]["message"]["reasoning_content"] = "unrequested reasoning"
    source["usage"] = {"prompt_tokens": True, "completion_tokens": -7}
    result = validate_completion(source)
    assert "private-provider-field" not in str(result)
    assert "unrequested reasoning" not in str(result)
    assert result["usage"] == {"prompt_tokens": None, "completion_tokens": None}
    two = deepcopy(source)
    two["choices"].append(deepcopy(source["choices"][0]))
    with pytest.raises(GatewayError):
        validate_completion(two)


def test_client_disables_proxy_environment_and_tls_key_logging(monkeypatch):
    captured = {}
    original = httpx.AsyncClient

    def client(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setenv("SSLKEYLOGFILE", "/tmp/editorial-must-not-create-tls-keylog")
    adapter = provider(monkeypatch, lambda request: httpx.Response(200, json=reply()))
    adapter.completion([], [])
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert captured["timeout"].read <= 30
    assert captured["timeout"].connect <= 5
    assert captured["timeout"].write <= 5
    assert captured["timeout"].pool <= 5
    tls = captured["verify"]
    assert tls.check_hostname
    assert tls.verify_mode == ssl.CERT_REQUIRED
    assert tls.keylog_filename is None
    assert _tls_context().keylog_filename is None


@pytest.mark.parametrize("calls", [False, 0, {}, ""])
def test_wrong_falsy_tool_call_shapes_are_rejected(calls):
    data = reply()
    data["choices"][0]["message"]["tool_calls"] = calls
    with pytest.raises(GatewayError):
        validate_completion(data)


@pytest.mark.parametrize(
    "arguments", ['{"case_id":"a","case_id":"b"}', '{"value":NaN}', '{"value":Infinity}']
)
def test_ambiguous_or_nonfinite_tool_arguments_are_rejected(arguments):
    with pytest.raises(GatewayError):
        validate_completion(reply(calls=[call(arguments=arguments)]))
