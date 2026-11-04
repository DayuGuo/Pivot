"""Admission is non-queueing, before bodies; light reads and human gates stay free."""

import asyncio
from threading import BoundedSemaphore

import pytest
from sqlalchemy import func, select

from apps.api.publishing import work_limits
from apps.api.publishing.domain.models import ActionReceipt
from tests.api.test_dossiers import create


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
