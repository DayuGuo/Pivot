"""Single-worker admission before request bodies, DB connections or model work."""

import asyncio
import os
import re
import time
from threading import BoundedSemaphore

from starlette.responses import JSONResponse

# The private VPS profile deliberately runs exactly one worker. This semaphore is
# per process; multi-worker deployments need a shared admission service first.
HEAVY_LIMIT = int(os.getenv("PIVOT_HEAVY_WORK_LIMIT", "1"))
if not 1 <= HEAVY_LIMIT <= 2:
    raise RuntimeError("PIVOT_HEAVY_WORK_LIMIT must be 1 or 2")
heavy_slots = BoundedSemaphore(HEAVY_LIMIT)


class RequestAdmission:
    """Bound API dependencies below the 15-connection pool, without blocking threads.

    Sync authentication and endpoints use separate thread-pool turns while a
    session holds its connection. Unbounded fan-out can occupy all threads in
    pool checkout before earlier requests finish. Waiting here uses no DB/body
    or worker thread; the queue, wait and concurrent requests are all bounded.
    """

    def __init__(self, app, limit=8, queue=16, wait_seconds=2):
        self.app = app
        self.active = BoundedSemaphore(limit)
        self.total = BoundedSemaphore(limit + queue)
        self.wait_seconds = wait_seconds

    async def busy(self, scope, receive, send):
        await JSONResponse(
            {"detail": "服务繁忙，请稍后重试；本次请求尚未执行。"},
            status_code=429,
            headers={"Retry-After": "1", "Cache-Control": "no-store"},
        )(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        if not self.total.acquire(blocking=False):
            return await self.busy(scope, receive, send)
        admitted = False
        try:
            deadline = time.monotonic() + self.wait_seconds
            while not (admitted := self.active.acquire(blocking=False)):
                if time.monotonic() >= deadline:
                    return await self.busy(scope, receive, send)
                await asyncio.sleep(0.005)
            await self.app(scope, receive, send)
        finally:
            if admitted:
                self.active.release()
            self.total.release()


def heavy_path(path):
    return path in {"/api/publishing/chat", "/api/editorial-demo/chat"} or bool(
        re.fullmatch(r"/api/dossiers/[^/]+/(chat|imports|revision-checks)", path)
        or re.fullmatch(r"/api/publishing/manuscripts/[^/]+/document-imports", path)
    )


class HeavyWorkAdmission:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not heavy_path(scope["path"]):
            return await self.app(scope, receive, send)
        if not heavy_slots.acquire(blocking=False):
            response = JSONResponse(
                {"detail": "正在处理另一份资料，请稍后重试；本次请求尚未执行。"},
                status_code=429,
                headers={"Retry-After": "2", "Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            heavy_slots.release()
