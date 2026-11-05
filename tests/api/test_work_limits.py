"""Admission is non-queueing, before bodies; light reads and human gates stay free."""

import asyncio
from threading import BoundedSemaphore

import pytest
from sqlalchemy import func, select

from apps.api.publishing import work_limits
from apps.api.publishing.domain.models import ActionReceipt
from tests.api.test_dossiers import create


@pytest.mark.parametrize("ending", ["success", "exception", "cancel"])
def test_request_admission_bounds_dependencies_and_releases(ending):
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        bodies, replies = [], []

        async def receive():
            bodies.append(True)
            return {"type": "http.request", "body": b"synthetic"}

        async def send(message):
            replies.append(message)

        async def app(scope, receive, send):
            await receive()
            started.set()
            await finish.wait()
            if scope.get("first") and ending == "exception":
                raise ValueError("synthetic failure")
            await send({"type": "http.response.start", "status": 200, "headers": []})

        wrapper = work_limits.RequestAdmission(app, limit=1, queue=1)
        scope = {"type": "http", "path": "/api/synthetic", "method": "POST"}
        first = asyncio.create_task(wrapper({**scope, "first": True}, receive, send))
        await started.wait()
        second = asyncio.create_task(wrapper(scope, receive, send))
        await asyncio.sleep(0)
        await wrapper(scope, receive, send)
        assert len(bodies) == 1
        assert replies[0]["status"] == 429
        assert (b"retry-after", b"1") in replies[0]["headers"]
        if ending == "cancel":
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        finish.set()
        if ending == "exception":
            with pytest.raises(ValueError):
                await first
        elif ending == "success":
            await first
        await second
        await wrapper(scope, receive, send)
        assert len(bodies) == 3
        assert replies[-1]["status"] == 200

    asyncio.run(run())


def test_request_admission_wait_timeout_never_reads_body_or_enters_handler():
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        bodies, replies = [], []

        async def receive():
            bodies.append(True)
            return {"type": "http.request", "body": b"synthetic"}

        async def send(message):
            replies.append(message)

        async def app(scope, receive, send):
            await receive()
            started.set()
            await finish.wait()

        wrapper = work_limits.RequestAdmission(app, limit=1, queue=1, wait_seconds=0.02)
        scope = {"type": "http", "path": "/api/synthetic", "method": "POST"}
        first = asyncio.create_task(wrapper(scope, receive, send))
        await started.wait()
        await wrapper(scope, receive, send)
        assert len(bodies) == 1 and replies[0]["status"] == 429
        finish.set()
        await first
        await wrapper(scope, receive, send)
        assert len(bodies) == 2

    asyncio.run(run())


def test_cancelled_admission_wait_does_not_consume_future_queue_capacity():
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        count = 0

        async def app(scope, receive, send):
            nonlocal count
            count += 1
            started.set()
            await finish.wait()

        async def unused(*args):
            raise AssertionError("No body or busy response expected")

        wrapper = work_limits.RequestAdmission(app, limit=1, queue=1)
        scope = {"type": "http", "path": "/api/synthetic", "method": "GET"}
        first = asyncio.create_task(wrapper(scope, unused, unused))
        await started.wait()
        waiting = asyncio.create_task(wrapper(scope, unused, unused))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        next_request = asyncio.create_task(wrapper(scope, unused, unused))
        await asyncio.sleep(0)
        finish.set()
        await asyncio.gather(first, next_request)
        assert count == 2

    asyncio.run(run())


@pytest.mark.parametrize("ending", ["success", "exception", "cancel"])
def test_concurrent_admission_rejects_before_body_and_releases(monkeypatch, ending):
    monkeypatch.setattr(work_limits, "heavy_slots", BoundedSemaphore(1))

    async def run():
        started = asyncio.Event()
        finish = asyncio.Event()
        received = []
        sent = []

        async def receive():
            received.append(True)
            return {"type": "http.request", "body": b"synthetic"}

        async def send(message):
            sent.append(message)

        async def app(scope, receive, send):
            if scope["method"] == "GET":
                await send({"type": "light"})
                return
            await receive()
            started.set()
            await finish.wait()
            if ending == "exception":
                raise ValueError("synthetic failure")

        wrapped = work_limits.HeavyWorkAdmission(app)
        scope = {"type": "http", "method": "POST", "path": "/api/dossiers/synthetic/chat"}
        first = asyncio.create_task(wrapped(scope, receive, send))
        await started.wait()
        await wrapped({**scope, "path": "/api/dossiers/synthetic/imports"}, receive, send)
        assert len(received) == 1
        assert sent[0]["status"] == 429
        assert (b"retry-after", b"2") in sent[0]["headers"]
        await wrapped({**scope, "method": "GET"}, receive, send)
        assert sent[-1] == {"type": "light"}
        if ending == "cancel":
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        else:
            finish.set()
            if ending == "exception":
                with pytest.raises(ValueError):
                    await first
            else:
                await first
        assert work_limits.heavy_slots.acquire(blocking=False)
        work_limits.heavy_slots.release()

    asyncio.run(run())


def test_saturated_http_has_no_receipt_and_does_not_block_human_reads(
    client, db, login, monkeypatch
):
    login("editor")
    item = create(client)
    gate = BoundedSemaphore(1)
    monkeypatch.setattr(work_limits, "heavy_slots", gate)
    before = db.scalar(select(func.count()).select_from(ActionReceipt))
    assert gate.acquire(blocking=False)
    try:
        for path in (
            f"/api/dossiers/{item['id']}/chat",
            f"/api/dossiers/{item['id']}/imports",
            "/api/publishing/chat",
            "/api/editorial-demo/chat",
            f"/api/publishing/manuscripts/{item['id']}/document-imports",
        ):
            response = client.post(path, content=b"deliberately not valid JSON")
            assert response.status_code == 429
            assert response.headers["retry-after"] == "2"
        assert client.get("/api/health").status_code == 200
        assert client.get(f"/api/dossiers/{item['id']}").status_code == 200
        assert client.post(f"/api/dossiers/{item['id']}/confirm", json={}).status_code == 422
        assert db.scalar(select(func.count()).select_from(ActionReceipt)) == before
    finally:
        gate.release()
    assert client.post(f"/api/dossiers/{item['id']}/chat", json={}).status_code == 422
