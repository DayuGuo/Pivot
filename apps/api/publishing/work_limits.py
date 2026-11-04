"""Single-worker admission before request bodies, DB connections or model work."""

import os
import re
from threading import BoundedSemaphore

from starlette.responses import JSONResponse

# The private VPS profile deliberately runs exactly one worker. This semaphore is
# per process; multi-worker deployments need a shared admission service first.
HEAVY_LIMIT = int(os.getenv("PIVOT_HEAVY_WORK_LIMIT", "1"))
if not 1 <= HEAVY_LIMIT <= 2:
    raise RuntimeError("PIVOT_HEAVY_WORK_LIMIT must be 1 or 2")
heavy_slots = BoundedSemaphore(HEAVY_LIMIT)


def heavy_path(path):
    return path in {"/api/publishing/chat", "/api/editorial-demo/chat"} or bool(
        re.fullmatch(r"/api/dossiers/[^/]+/(chat|imports)", path)
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
