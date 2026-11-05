#!/usr/bin/env python3
"""Synthetic, read-only revision protocol experiment, with explicit --live opt-in.

Use inside this project's selected API environment. No auth files, database,
mail, manuscript records or approvals are read or changed. Never prints secrets
or supplier response bodies. A live result is not formal-workflow E2E acceptance.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apps.api.publishing.domain.revision_compare import compare  # noqa: E402
from packages.model_gateway.editorial import (  # noqa: E402
    EditorialMockProvider,
    get_editorial_provider,
    safe_error_code,
)


def source():
    files = {}
    for kind, text in {
        "base": "样本量为40，分组方法未说明。\n未提供数据链接。",
        "revised": "样本量更正为80，按预先规定规则分成两组。\n未提供数据链接。",
        "response": "已更正样本量和分组说明。\n数据链接将在后续提供，本次未补充。",
    }.items():
        files[kind] = {
            "kind": kind,
            "file_id": str(uuid4()),
            "version_id": "old" if kind == "base" else "new",
            "version_no": 1 if kind == "base" else 2,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text": text,
        }
    return {
        "manuscript_id": str(uuid4()),
        "request_id": str(uuid4()),
        "revision": 4,
        "base_version_id": "old",
        "revised_version_id": "new",
        "rereview_required": True,
        "source_fingerprint": "a" * 64,
        "files": files,
        "points": [
            {"id": f"P{i + 1:02d}", "text": text, "label": "合成要求", "complete": True}
            for i, text in enumerate(["请更正样本量并说明分组。", "请提供公开数据链接。"])
        ],
        "point_count": 2,
        "all_points_included": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    telemetry = []
    result = {"scope": "synthetic_revision_protocol_only", "database_writes": 0}
    try:
        provider = get_editorial_provider() if args.live else EditorialMockProvider()
        if args.live and provider.name != "deepseek":
            raise ValueError("live_provider_not_configured")
        if getattr(provider, "set_deadline", None):
            provider.set_deadline(time.monotonic() + 60)
        original = source()
        report = compare(original, provider, lambda: None, telemetry)
        states = {r["point_id"]: r["status"] for r in report["rows"]}
        assert len(report["rows"]) == 2 and states["P02"] in {"partial", "explained", "uncertain"}
        for row in report["rows"]:
            for citation in row["citations"]:
                text = original["files"][citation["kind"]]["text"]
                assert text[citation["start"] : citation["end"]] == citation["quote"]
        result.update(
            success=True,
            provider=provider.name,
            states=states,
            human_confirmation_required=report["human_confirmation_required"],
        )
    except Exception as error:
        result.update(success=False, error_code=safe_error_code(error))
    result.update(duration_ms=round((time.monotonic() - started) * 1000), telemetry=telemetry)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
