"""Offline transport failures, deadlines and per-turn recovery budgets."""

import asyncio
import json
import time

import httpx
import pytest

from evals.test_editorial_provider import reply
from packages.model_gateway import editorial
from packages.model_gateway.gateway import GatewayError


@pytest.fixture
def install(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-recovery-only")
    monkeypatch.setattr(editorial, "RETRY_DELAY_SECONDS", 0.001)

    def make(handle):
        return editorial.EditorialDeepSeekProvider(
            live_enabled=True, transport=httpx.MockTransport(handle)
        )

    return make


@pytest.mark.parametrize("failure", [500, 502, 503, 504, httpx.ReadTimeout, httpx.ConnectError])
def test_transient_failure_repeats_identical_inference_only_once(install, failure):
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            if isinstance(failure, int):
                return httpx.Response(failure, text="PRIVATE-SUPPLIER-ERROR")
            raise failure("PRIVATE-NETWORK-ERROR", request=request)
        return httpx.Response(200, json=reply())

    adapter = install(handle)
    value = adapter.completion([{"role": "user", "content": "synthetic"}], [])
    assert value["choices"][0]["message"]["content"]
    assert len(requests) == 2 and requests[0].content == requests[1].content
    assert [m.success for m in adapter.last_attempt_telemetry] == [False, True]
    assert adapter.last_attempt_telemetry[0].input_tokens is None
    assert adapter.last_attempt_telemetry[0].cost_usd is None
    assert adapter.last_telemetry.input_tokens == 12
    assert "PRIVATE-" not in str(adapter.last_attempt_telemetry)


def test_extra_attempt_budget_shared_across_all_rounds(install):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=reply()) if len(calls) == 2 else httpx.Response(503)

    adapter = install(handle)
    adapter.completion([], [])
    assert len(adapter.last_attempt_telemetry) == 2
    with pytest.raises(GatewayError, match="^editorial_provider_unavailable$"):
        adapter.completion([], [])
    assert len(calls) == 3
    assert len(adapter.last_attempt_telemetry) == 1
    assert not adapter.last_telemetry.success


def test_retry_rechecks_original_authority_before_transmission(install):
    calls, checks = [], []

    def handle(request):
        calls.append(request)
        return httpx.Response(503)

    adapter = install(handle)

    def check():
        checks.append(True)
        if len(checks) == 2:
            raise PermissionError("synthetic authority revoked")

    adapter.before_attempt = check
    with pytest.raises(PermissionError):
        adapter.completion([], [])
    assert len(calls) == 1 and len(checks) == 2


class Heartbeats(httpx.AsyncByteStream):
    closed = False

    async def __aiter__(self):
        while True:
            await asyncio.sleep(0.005)
            yield b"\n"

    async def aclose(self):
        self.closed = True


def test_continuous_small_heartbeats_cannot_extend_total_deadline(install, monkeypatch):
    monkeypatch.setattr(editorial, "TURN_TIMEOUT_SECONDS", 0.08)
    stream = Heartbeats()
    adapter = install(lambda request: httpx.Response(200, stream=stream))
    started = time.monotonic()
    with pytest.raises(GatewayError, match="^editorial_provider_deadline$"):
        adapter.completion([], [])
    assert time.monotonic() - started < 0.8
    assert stream.closed
    assert len(adapter.last_attempt_telemetry) == 1
    assert adapter.last_telemetry.error_code == "editorial_provider_deadline"


def test_slow_headers_are_cancelled_without_a_late_background_request(install, monkeypatch):
    monkeypatch.setattr(editorial, "TURN_TIMEOUT_SECONDS", 0.08)
    cancelled = []

    async def handle(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    adapter = install(handle)
    started = time.monotonic()
    with pytest.raises(GatewayError, match="^editorial_provider_deadline$"):
        adapter.completion([], [])
    assert time.monotonic() - started < 0.8
    assert cancelled == [True]


def test_shared_deadline_is_not_restarted_by_next_round(install):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=reply())

    adapter = install(handle)
    adapter.completion([], [])
    original = adapter._deadline
    adapter.set_deadline(time.monotonic() - 1)
    with pytest.raises(GatewayError, match="^editorial_provider_deadline$"):
        adapter.completion([], [])
    assert len(calls) == 1 and adapter._deadline < original


def test_blank_lines_around_a_complete_json_response_are_accepted(install):
    content = b"\n\n" + json.dumps(reply()).encode() + b"\n"
    adapter = install(lambda request: httpx.Response(200, content=content))
    assert adapter.completion([], [])["usage"]["prompt_tokens"] == 12
