"""Safe delegated drafting, not a shell/code executor. Results require lead review.

python -m packages.model_gateway.delegate --kind research --task 'Review an API boundary'
Add --live ONLY after exporting a fresh DEEPSEEK_API_KEY through a trusted environment.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .gateway import DeepSeekProvider, GatewayError, Telemetry

KINDS = ("research", "api", "react", "tests", "documentation")
RESULT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "submit_task_result",
            "description": "Submit a draft for human/lead integration. Never execute it or access publishing tools.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}, "draft": {"type": "string"}},
                "required": ["summary", "draft"],
                "additionalProperties": False,
            },
        },
    }
]


def run_task(
    kind: str,
    task: str,
    *,
    live: bool = False,
    rework_count: int = 0,
    provider: DeepSeekProvider | None = None,
) -> tuple[dict[str, str], Telemetry]:
    if kind not in KINDS or not task.strip() or len(task) > 12000 or rework_count < 0:
        raise GatewayError("invalid_delegation")
    started = time.monotonic()
    if not live:
        return {
            "summary": f"[MOCK] {kind} task draft",
            "draft": "模拟委派结果。未调用 DeepSeek。主 Agent 需独立完成并验证此任务。",
        }, Telemetry(
            "mock",
            "deterministic-delegation-v1",
            True,
            int((time.monotonic() - started) * 1000),
            0,
            0,
            0.0,
            "mock; no API charge",
            rework_count,
        )
    client = provider or DeepSeekProvider(live_enabled=True)
    data = client.completion(
        [
            {
                "role": "system",
                "content": f"Draft a {kind} task result using submit_task_result. Use only supplied synthetic/public context. Do not execute code, contact people, access secrets, or make publishing decisions. Output is an untrusted draft reviewed by the lead.",
            },
            {"role": "user", "content": task},
        ],
        RESULT_TOOL,
    )
    try:
        calls = data["choices"][0]["message"]["tool_calls"]
        if len(calls) != 1 or calls[0]["function"]["name"] != "submit_task_result":
            raise ValueError("unexpected result tool")
        result: Any = json.loads(calls[0]["function"]["arguments"])
        if set(result) != {"summary", "draft"} or not all(
            isinstance(x, str) for x in result.values()
        ):
            raise ValueError("unexpected result shape")
        if len(result["summary"]) > 2000 or len(result["draft"]) > 50000:
            raise ValueError("oversized result")
        assert client.last_telemetry is not None
        return result, replace(client.last_telemetry, rework_count=rework_count)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise GatewayError("invalid_delegated_result") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=KINDS, required=True)
    task_source = parser.add_mutually_exclusive_group(required=True)
    task_source.add_argument("--task", help="Public/synthetic instructions; never credentials")
    task_source.add_argument(
        "--task-file", type=Path, help="UTF-8 public/synthetic task brief; never a credentials file"
    )
    parser.add_argument(
        "--live", action="store_true", help="Opt in to fresh-key DeepSeek API usage"
    )
    parser.add_argument("--rework-count", type=int, default=0)
    parser.add_argument(
        "--output-root", type=Path, default=Path(tempfile.gettempdir()) / "publishing-delegations"
    )
    args = parser.parse_args()
    task = args.task
    if args.task_file is not None:
        try:
            if args.task_file.stat().st_size > 12000:
                parser.error("task_file_too_large")
            task = args.task_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            parser.error("task_file_unreadable")
    task_id = str(uuid.uuid4())
    output = args.output_root.resolve() / task_id
    output.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    provider = None
    try:
        if args.live:
            provider = DeepSeekProvider(live_enabled=True)
        result, telemetry = run_task(
            args.kind, task, live=args.live, rework_count=args.rework_count, provider=provider
        )
        (output / "result.json").write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "kind": args.kind,
                    "requires_lead_review": True,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    except GatewayError as exc:
        if provider and provider.last_telemetry:
            telemetry = replace(
                provider.last_telemetry,
                success=False,
                rework_count=args.rework_count,
                error_code=str(exc),
            )
        else:
            telemetry = Telemetry(
                "deepseek" if args.live else "mock",
                "deepseek-flash" if args.live else "mock",
                False,
                int((time.monotonic() - started) * 1000),
                rework_count=args.rework_count,
                error_code=str(exc),
            )
    (output / "telemetry.json").write_text(json.dumps(telemetry.as_dict(), indent=2) + "\n")
    # No task text, key, provider body, or generated code goes to logs.
    print(
        json.dumps(
            {
                "task_id": task_id,
                "artifact_directory": str(output),
                "telemetry": telemetry.as_dict(),
            }
        )
    )
    if not telemetry.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
