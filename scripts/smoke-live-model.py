#!/usr/bin/env python3
"""Read-only synthetic question via actual local API; no exposed keys or mail."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    started = time.monotonic()
    report = {
        "provider": "deepseek",
        "live_verified": False,
        "synthetic_only": True,
        "email_send_requested": False,
    }
    try:
        with httpx.Client(base_url="http://127.0.0.1:8100", timeout=80, trust_env=False) as client:
            login = client.post(
                "/api/auth/login",
                json={"email": "chief@publishing.test", "password": "ChiefDemo2026!"},
            )
            if login.status_code != 200:
                raise ValueError("local_login_failed")
            client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            status = client.get("/api/editorial-demo/chat/model").json()
            if status.get("provider") != "deepseek" or not status.get("available"):
                raise ValueError("fresh_live_model_configuration_required")
            result = client.post(
                "/api/editorial-demo/chat",
                json={
                    "request_id": str(uuid4()),
                    "message": "请调用工具读取当前稿件的状态和下一步任务，并引用依据。只查询，不准备草稿。",
                    "context": {
                        "scope": "case",
                        "case_id": "demo-001",
                        "version": "v3",
                        "view": "read",
                        "stage": "all",
                        "query": "",
                        "today_only": False,
                    },
                },
            )
            if result.status_code != 200:
                raise ValueError("live_chat_request_failed")
            data = result.json()
            reply = data["messages"][1]
            receipts = reply.get("tool_receipts", [])
            if (
                data["provider"] != "deepseek"
                or data["state_changed"]
                or not any(
                    r["tool"] == "inspect_manuscript" and r["status"] == "read" for r in receipts
                )
            ):
                raise ValueError("live_tool_roundtrip_not_verified")
            report.update(
                live_verified=True,
                tool_receipts=receipts,
                request_id=data["request_id"],
                citation_count=len(reply["references"]),
            )
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as error:
        safe_codes = {
            "local_login_failed",
            "fresh_live_model_configuration_required",
            "live_chat_request_failed",
            "live_tool_roundtrip_not_verified",
        }
        report["error_code"] = (
            str(error)
            if isinstance(error, ValueError) and str(error) in safe_codes
            else "live_validation_unavailable_or_failed"
        )
    report["duration_ms"] = int((time.monotonic() - started) * 1000)
    root = Path(__file__).resolve().parent.parent
    path = root / "artifacts" / "live-model-smoke.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["live_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
