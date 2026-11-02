"""Aggregate sanitized delegation telemetry, retaining unknown cost/token coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(root: Path) -> dict:
    rows = [json.loads(path.read_text()) for path in root.glob("*/telemetry.json")]
    known_costs = [row["cost_usd"] for row in rows if row.get("cost_usd") is not None]
    return {
        "attempts": len(rows),
        "successes": sum(row.get("success") is True for row in rows),
        "success_rate": sum(row.get("success") is True for row in rows) / len(rows)
        if rows
        else None,
        "mock_attempts": sum(row.get("provider") == "mock" for row in rows),
        "input_tokens_known": sum(row.get("input_tokens") or 0 for row in rows),
        "output_tokens_known": sum(row.get("output_tokens") or 0 for row in rows),
        "unknown_usage_attempts": sum(row.get("input_tokens") is None for row in rows),
        "known_cost_usd": sum(known_costs),
        "unknown_cost_attempts": len(rows) - len(known_costs),
        "duration_ms": sum(row.get("duration_ms") or 0 for row in rows),
        "rework_count": sum(row.get("rework_count") or 0 for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2))


if __name__ == "__main__":
    main()
