"""Opt-in actual HTTP/DeepSeek regression in the isolated verification stack only.

The selected local main API supplies its existing credential via captured memory,
never argv/files/logs. Its configuration and data are not changed. Verification
temporarily enables live inference for read-only comparisons, always restores Mock.
Workflow gates use synthetic demo accounts and explicit test confirmations.
"""

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx

from evals.public_revisions.workflow import ROOT, build_case, cases
from packages.document_ingest import extract_document

COMPOSE = [
    "docker",
    "compose",
    "-p",
    "publishing-os-verification",
    "-f",
    "compose.yaml",
    "-f",
    "infrastructure/compose.verify.yaml",
]
ACCOUNTS = {
    "author": ("author", "Author"),
    "editor": ("editor", "Editor"),
    "reviewer": ("reviewer", "Reviewer"),
    "chief_editor": ("chief", "Chief"),
}
READ_MODEL = """import json,os
print(json.dumps({k:os.environ.get(k,'') for k in ('EDITORIAL_MODEL_PROVIDER','EDITORIAL_MODEL_LIVE_ENABLED','DEEPSEEK_API_KEY')}))
"""
COUNTS = """import json
from sqlalchemy import text
from apps.api.publishing.db import engine
with engine.connect() as d:
 print(json.dumps({t:d.scalar(text('select count(*) from '+t)) for t in ('publishing_action_proposals','publishing_human_confirmations','publishing_editorial_decisions')}))
"""
TELEMETRY = """import json,sys
from sqlalchemy import select
from apps.api.publishing.db import engine
from apps.api.publishing.models import AuditEvent
ids=json.loads(sys.stdin.read())
with engine.connect() as d:
 print(json.dumps([r[0].get('telemetry',[]) for r in d.execute(select(AuditEvent.details).where(AuditEvent.action.in_(['publishing.chat_completed','publishing.chat_failed']),AuditEvent.details['request_id'].as_string().in_(ids)))]))
"""


def run(args, *, env=None, input=None):
    value = subprocess.run(
        args, cwd=ROOT, env=env, input=input, text=True, capture_output=True, timeout=180
    )
    if value.returncode:
        raise RuntimeError("scoped_compose_command_failed")
    return value.stdout


def login(client, role):
    email, prefix = ACCOUNTS[role]
    response = client.post(
        "/api/auth/login",
        json={"email": email + "@publishing.test", "password": prefix + "Demo2026!"},
    )
    if response.status_code != 200:
        raise RuntimeError("synthetic_login_failed")
    data = response.json()
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    return data


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def prepare_cases(client):
    users = {}
    for role in ACCOUNTS:
        login(client, role)
        session = client.get("/api/publishing/session").json()
        users[role] = SimpleNamespace(id=session["user"]["id"])
    world = SimpleNamespace(users=users)
    prepared = []
    for case, formats in zip(
        cases(), [("pdf", "docx"), ("pdf", "pdf"), ("docx", "docx")], strict=True
    ):
        mid = build_case(client, lambda role: login(client, role), world, case, *formats)
        prepared.append(
            {"id": case["id"], "mid": mid, "formats": list(formats), "unchanged_mutation": False}
        )
    mid = build_case(
        client, lambda role: login(client, role), world, cases()[0], "docx", "docx", unchanged=True
    )
    prepared.append(
        {
            "id": "oath-unchanged-adversarial",
            "mid": mid,
            "formats": ["docx", "docx"],
            "unchanged_mutation": True,
        }
    )
    return prepared


def verify_citations(client, comparison, cache):
    count = 0
    for finding in comparison["rows"]:
        assert finding["status"] != "not_addressed"
        for cite in finding["citations"]:
            key = cite["file_id"]
            if key not in cache:
                response = client.get(f"/api/publishing/files/{key}")
                assert response.status_code == 200
                cache[key] = response.content.decode()
            assert cache[key][cite["start"] : cite["end"]] == cite["quote"]
            origin = cite["original"]
            if origin["sha256"] not in cache:
                response = client.get(origin["download_url"])
                assert response.status_code == 200
                assert hashlib.sha256(response.content).hexdigest() == origin["sha256"]
                cache[origin["sha256"]] = extract_document(origin["filename"], response.content)
            parsed = cache[origin["sha256"]]
            start, end = origin["scope_start"] + cite["start"], origin["scope_start"] + cite["end"]
            assert parsed["text"][start:end] == cite["quote"]
            for loc in origin["locations"]:
                segment = parsed["segments"][loc["number"] - 1]
                assert (
                    segment["kind"] == loc["kind"]
                    and segment["start"] <= loc["start"] < loc["end"] <= segment["end"]
                )
                assert parsed["text"][loc["start"] : loc["end"]] == loc["quote"]
            count += 1
    return count


def compare_case(client, case, request_ids):
    login(client, "editor")
    before = client.get(f"/api/publishing/manuscripts/{case['mid']}").json()
    assert before["stage"] == "revision_assessment"
    row = {**case, "passed": False, "batches": [], "citations": 0}
    begin = time.monotonic()
    offset = 0
    ids = []
    cache = {}
    for _ in range(8):
        rid = str(uuid4())
        request_ids.append(rid)
        start = time.monotonic()
        result = client.post(
            "/api/publishing/chat",
            json={
                "request_id": rid,
                "message": f"请从第{offset + 1}项开始，逐条对照修回与作者回复，保留不确定性。",
                "context": {"manuscript_id": case["mid"], "scope": "case", "view": "work"},
            },
        )
        batch = {
            "offset": offset,
            "request_id": rid,
            "status_code": result.status_code,
            "duration_ms": round((time.monotonic() - start) * 1000),
        }
        row["batches"].append(batch)
        if result.status_code != 200:
            break
        data = result.json()
        answer = data["messages"][1]
        comparison = answer["revision_comparison"]
        assert answer["provider"] == comparison["provider"] == "deepseek"
        assert (
            data["state_changed"] is False
            and answer["action"] is None
            and comparison["human_confirmation_required"]
        )
        assert comparison["coverage"]["response"]["source_complete"] is False
        assert comparison["point_offset"] == offset
        row["citations"] += verify_citations(client, comparison, cache)
        if case["unchanged_mutation"]:
            assert all(r["status"] != "resolved" for r in comparison["rows"])
        batch["report"] = comparison
        ids.extend(r["point_id"] for r in comparison["rows"])
        assert len(ids) == len(set(ids))
        offset = comparison["next_offset"]
        if offset is None:
            assert len(ids) == comparison["point_count"]
            row.update(passed=True, checked_rows=len(ids), point_count=comparison["point_count"])
            break
    after = client.get(f"/api/publishing/manuscripts/{case['mid']}").json()
    assert digest(before) == digest(after)
    row["duration_ms"] = round((time.monotonic() - begin) * 1000)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument(
        "--resume",
        type=Path,
        help="Reuse sandbox IDs from a prior local report; never recreate workflow gates",
    )
    parser.add_argument("--report", type=Path, default=ROOT / "artifacts/spec025/public-live.json")
    args = parser.parse_args()
    report = {
        "scope": "actual_isolated_http_formal_revision_with_live_readonly_comparison",
        "success": False,
        "cases": [],
        "cost_usd": None,
    }
    output = ROOT / "artifacts/spec025/verification-live.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    # No secret is written: interpolation resolves from this process's private env.
    output.write_text(
        'services:\n  api:\n    environment:\n      EDITORIAL_MODEL_PROVIDER: deepseek\n      EDITORIAL_MODEL_LIVE_ENABLED: "true"\n      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:?fresh scoped environment required}\n      EMAIL_SEND_ENABLED: "false"\n'
    )
    switched = False
    started = time.monotonic()
    safe_env = dict(
        os.environ,
        EDITORIAL_MODEL_PROVIDER="mock",
        EDITORIAL_MODEL_LIVE_ENABLED="false",
        DEEPSEEK_API_KEY="",
        EMAIL_SEND_ENABLED="false",
    )
    try:
        with httpx.Client(base_url="http://127.0.0.1:13100", trust_env=False, timeout=80) as client:
            health = client.get("/api/health").json()
            assert health["editorial_model"]["provider"] == "mock"
            assert health["email_send_enabled"] is False
            model = json.loads(
                run(
                    [
                        "docker",
                        "compose",
                        "-p",
                        "publishing-os",
                        "-f",
                        "compose.yaml",
                        "exec",
                        "-T",
                        "api",
                        "python",
                        "-c",
                        READ_MODEL,
                    ]
                )
            )
            if (
                model["EDITORIAL_MODEL_PROVIDER"] != "deepseek"
                or model["EDITORIAL_MODEL_LIVE_ENABLED"] != "true"
                or not model["DEEPSEEK_API_KEY"]
            ):
                raise RuntimeError("fresh_scoped_live_provider_unavailable")
            if args.resume:
                previous = json.loads(args.resume.read_text())
                prepared = [
                    {k: c[k] for k in ("id", "mid", "formats", "unchanged_mutation")}
                    for c in previous["cases"]
                ]
                assert len(prepared) == 4
            else:
                prepared = prepare_cases(client)
            counts_before = json.loads(
                run(COMPOSE + ["exec", "-T", "api", "python", "-c", COUNTS], env=safe_env)
            )
            mail_before = httpx.get(
                "http://127.0.0.1:18025/api/v1/messages", trust_env=False
            ).json()["total"]
            switched = True  # Even a failed recreation must run the restoration.
            run(
                COMPOSE + ["-f", str(output), "up", "-d", "api", "--wait"],
                env=dict(safe_env, **model),
            )
            assert client.get("/api/health").json()["editorial_model"]["provider"] == "deepseek"
            request_ids = []
            for case in prepared:
                row = compare_case(client, case, request_ids)
                report["cases"].append(row)
            report["telemetry"] = json.loads(
                run(
                    COMPOSE + ["exec", "-T", "api", "python", "-c", TELEMETRY],
                    env=safe_env,
                    input=json.dumps(request_ids),
                )
            )
            report["counts_before"] = counts_before
            report["counts_after"] = json.loads(
                run(COMPOSE + ["exec", "-T", "api", "python", "-c", COUNTS], env=safe_env)
            )
            assert report["counts_after"] == counts_before
            assert (
                mail_before
                == httpx.get("http://127.0.0.1:18025/api/v1/messages", trust_env=False).json()[
                    "total"
                ]
                == 0
            )
            report["success"] = all(c["passed"] for c in report["cases"])
    except Exception as error:
        report["error_code"] = (
            str(error) if isinstance(error, RuntimeError) else type(error).__name__
        )
    finally:
        if switched:
            try:
                run(COMPOSE + ["up", "-d", "api", "--wait"], env=safe_env)
                with httpx.Client(trust_env=False, timeout=10) as client:
                    assert (
                        client.get("http://127.0.0.1:13100/api/health").json()["editorial_model"][
                            "provider"
                        ]
                        == "mock"
                    )
                report["restored_mock"] = True
            except Exception:
                report["restored_mock"] = False
                report["success"] = False
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"cases", "telemetry"}}, ensure_ascii=False
        )
    )
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
