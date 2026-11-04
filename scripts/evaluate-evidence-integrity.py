#!/usr/bin/env python3
"""Licensed-corpus regression. --live scores frozen gold via an isolated API image.

No business writes, approvals, mail, global auth files, or execution of model code.
The selected local app's existing key is borrowed in memory, never printed/saved.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.api.publishing.domain.document_candidates import (  # noqa: E402
    AuthorCandidate,
    MetadataCandidate,
    Quoted,
    merge_candidate,
)
from evals.public_documents.corpus import corpus, support_cases  # noqa: E402
from packages.text_evidence import raw_whitespace_span  # noqa: E402


def raw_field(text, value):
    span = raw_whitespace_span(text, value)
    if span is None:
        positions = [i for i, c in enumerate(text) if not c.isspace()]
        compact = "".join(value.split())
        start = "".join(text[i] for i in positions).find(compact)
        if start < 0:
            raise RuntimeError("Author gold not present in raw text")
        span = positions[start], positions[start + len(compact) - 1] + 1
    raw = text[span[0] : span[1]]
    return Quoted(value=raw, quote=raw)


def authors(all_files):
    results = []
    for paper, item, extraction in corpus(all_files):
        text = extraction["text"]
        proposed = [
            AuthorCandidate(
                name=raw_field(text, a["name"]),
                email=raw_field(text, a["email"]) if a["email"] else None,
                affiliations=[raw_field(text, v) for v in a["affiliations"]],
            )
            for a in paper["review_data"]["authors"]
        ]
        issues = []
        data, sources = merge_candidate(
            MetadataCandidate(authors=proposed),
            extraction,
            {
                "source_kind": "public_authorized",
                "source_note": "Licensed public gold proposal, not automatic extraction.",
            },
            uncertainties=issues,
        )
        gold = paper["review_data"]["authors"]
        checks = []
        for actual, expected in zip(data["authors"], gold, strict=True):
            checks.append(
                "".join(actual["name"].split()) == "".join(expected["name"].split())
                and {"".join(v.split()) for v in actual["affiliations"]}
                == {"".join(v.split()) for v in expected["affiliations"]}
                and actual["email"] == expected["email"]
            )
        exact = all(text[s["start"] : s["end"]] == s["quote"] for s in sources)
        results.append(
            {
                "case": item["case"],
                "passed": all(checks) and exact,
                "author_positions": len(checks),
                "affiliation_links": sum(len(a["affiliations"]) for a in data["authors"]),
                "email_links": sum(bool(a["email"]) for a in data["authors"]),
                "uncertainties": len(issues),
                "scope": "validator replay of independent gold proposals, not model extraction accuracy",
            }
        )
    return results


WORKER = r"""
import json,sys,time
from packages.model_gateway.editorial import get_editorial_provider,SAFE_ERROR_CODES
from packages.model_gateway.gateway import GatewayError
from apps.api.publishing.domain.claim_support import assess_support
cases=json.load(sys.stdin)
for case in cases:
    metrics=[];started=time.monotonic();deadline=started+60
    def validate():
        if time.monotonic()>=deadline:raise GatewayError("editorial_provider_deadline")
    try:
        provider=get_editorial_provider()
        if provider.name!="deepseek":raise GatewayError("fresh_deepseek_key_required")
        provider.before_attempt=validate;provider.set_deadline(deadline)
        result=assess_support(case["result"],provider,validate,metrics)
        claim=(result["claims"] or result.get("withheld_claims",[]))[0]
        status=claim["support"]["status"]
        row={"id":case["id"],"expected":case["expected"],"status":status,"reason":claim["support"].get("reason"),
             "passed":(status=="supported")== (case["expected"]=="supported"),"telemetry":metrics,
             "duration_ms":round((time.monotonic()-started)*1000)}
    except Exception as error:
        code=error.args[0] if isinstance(error,GatewayError) and error.args else None
        row={"id":case["id"],"expected":case["expected"],"passed":False,"status":"error",
             "error_code":code if code in SAFE_ERROR_CODES|{"dossier_support_invalid","dossier_material_credentials"} else "evaluation_failed",
             "telemetry":metrics,"duration_ms":round((time.monotonic()-started)*1000)}
    print(json.dumps(row,ensure_ascii=False),flush=True)
"""


def live(cases, image, report):
    captured = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "import os; print(os.environ.get('DEEPSEEK_API_KEY','') if os.environ.get('EDITORIAL_MODEL_PROVIDER')=='deepseek' and os.environ.get('EDITORIAL_MODEL_LIVE_ENABLED')=='true' else '')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    key = captured.stdout.strip() if captured.returncode == 0 else ""
    if len(key) < 24:
        raise RuntimeError("Fresh scoped live app configuration required; no key is printed")
    child_env = {**os.environ, "DEEPSEEK_API_KEY": key}
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=256m",
        "--cpus=0.8",
        "--pids-limit=64",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=32m",
        "--entrypoint=python",
        "-e",
        "DEEPSEEK_API_KEY",
        "-e",
        "EDITORIAL_MODEL_PROVIDER=deepseek",
        "-e",
        "EDITORIAL_MODEL_LIVE_ENABLED=true",
        image,
        "-c",
        WORKER,
    ]
    # Child gets the key through environment, never command-line values or files.
    result = subprocess.run(
        command,
        input=json.dumps(cases, ensure_ascii=False),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=65 * len(cases) + 30,
    )
    if result.returncode:
        raise RuntimeError("Isolated evaluation container failed; raw output suppressed")
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if {r["id"] for r in rows} != {c["id"] for c in cases} or len(rows) != len(cases):
        raise RuntimeError("Incomplete live evaluation")
    metrics = [m for r in rows for m in r["telemetry"]]
    report.update(
        mode="live_deepseek_support",
        support=rows,
        support_passed=all(r["passed"] for r in rows),
        evaluation_errors=sum(r["status"] == "error" for r in rows),
        false_acceptances=sum(
            r["status"] == "supported" and r["expected"] == "withheld" for r in rows
        ),
        false_rejections=sum(
            r["status"] != "supported" and r["expected"] == "supported" for r in rows
        ),
        provider_attempts=len(metrics),
        input_tokens=sum(m.get("input_tokens") or 0 for m in metrics),
        output_tokens=sum(m.get("output_tokens") or 0 for m in metrics),
        cost_usd=None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--all-files", action="store_true")
    parser.add_argument("--image", default="publishing-os-verification-api")
    parser.add_argument(
        "--report", type=Path, default=ROOT / "artifacts/spec020/evidence-regression.json"
    )
    args = parser.parse_args()
    cases = list(support_cases(args.all_files))
    report = {
        "schema": "evidence-regression.v1",
        "mode": "offline_sources_and_author_links",
        "authors": authors(args.all_files),
        "quote_cases": len(cases),
        "quotes_exact": all(c["quote_exact"] for c in cases),
        "semantic_quality_measured": args.live,
        "confirmations": 0,
        "mail_or_decision_requests": 0,
        "business_writes": 0,
        "source_hashes": {c["file_case"]: c["original_sha256"] for c in cases},
    }
    if args.live:
        live(cases, args.image, report)
    report["passed"] = (
        all(c["passed"] for c in report["authors"])
        and report["quotes_exact"]
        and report.get("support_passed", True)
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"authors", "support", "source_hashes"}},
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
