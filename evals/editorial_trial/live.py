"""Bounded real API evaluation. Fixed isolated local services, public/synthetic data only."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
API = "http://127.0.0.1:18101"
DB = "postgresql+psycopg://publishing:publishing_local@127.0.0.1:55434/publishing"
TABLES = (
    "email_drafts",
    "email_approvals",
    "publishing_editorial_decisions",
    "publishing_human_confirmations",
    "publishing_dossier_checks",
    "publishing_document_approvals",
)
CASES = {"clinical-word", "reproducible-pdf"}


def selected_manifest(manifest):
    papers = [
        {**p, "files": [f for f in p["files"] if f["case"] in CASES]} for p in manifest["papers"]
    ]
    papers = [p for p in papers if p["files"]]
    if {f["case"] for p in papers for f in p["files"]} != CASES:
        raise ValueError("public_cases_missing")
    return {**manifest, "papers": papers}


def load_evaluator():
    spec = importlib.util.spec_from_file_location(
        "public_evaluator", ROOT / "scripts/evaluate-public-papers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def counts(engine):
    with engine.connect() as connection:
        return {name: connection.scalar(text(f"SELECT count(*) FROM {name}")) for name in TABLES}


def mail_count():
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.get("http://127.0.0.1:18026/api/v1/messages")
        response.raise_for_status()
        return response.json()["total"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    out = (
        ROOT
        / "artifacts/editorial-trial-live"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    )
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "editorial-trial-live.v1",
        "passed": False,
        "real_model_verified": False,
        "human_evaluations": 0,
        "complete_response_letters": 0,
        "model": "deepseek-flash",
        "steps": [],
        "started_at": datetime.now(UTC).isoformat(),
    }
    started = time.monotonic()
    engine = create_engine(DB, connect_args={"connect_timeout": 5})
    before = None
    mail_before = None
    report["phase"] = "preflight"
    try:
        report["source"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        report["working_tree_dirty"] = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
        )
        with httpx.Client(timeout=10, trust_env=False) as client:
            health = client.get(API + "/api/health").json()
        if (
            health.get("email_send_enabled") is not False
            or health.get("editorial_model", {}).get("provider") != "deepseek"
        ):
            raise ValueError("live_provider_and_disabled_mail_required")
        before, mail_before = counts(engine), mail_count()
        evaluator = load_evaluator()
        manifest = selected_manifest(evaluator.load(evaluator.MANIFEST))
        # Validate exact bytes before any provider invocation; no fetch in this runner.
        for _, file in evaluator.files(manifest):
            evaluator.check_file(file)
        report["material_manifest_sha256"] = hashlib.sha256(
            evaluator.MANIFEST.read_bytes()
        ).hexdigest()
        report["steps"].append({"name": "licensed_originals_present", "passed": True})
        synthetic_report = out / "synthetic.json"
        report["phase"] = "synthetic_version_and_tool_acceptance"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/accept-dossier-model.py",
                "--live",
                "--isolated-trial",
                "--base-url",
                API,
                "--report",
                str(synthetic_report),
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=500,
        )
        report["steps"].append(
            {
                "name": "version_author_tools_and_human_boundary",
                "passed": result.returncode == 0,
                "report": "synthetic.json",
            }
        )
        if result.returncode:
            raise ValueError("synthetic_acceptance_failed")
        report["phase"] = "public_pdf_docx_import"
        with contextlib.redirect_stdout(io.StringIO()):
            evaluator.stage(manifest, out / "public-staging.json", API)
            report["phase"] = "public_author_and_source_audit"
            evaluator.audit(manifest, out / "public-staging.json", out / "public-audit.json")
        if evaluator.load(out / "public-audit.json").get("passed") is not True:
            raise ValueError("public_audit_not_passed")
        report["steps"].append(
            {
                "name": "public_pdf_docx_candidates_and_author_alignment",
                "passed": True,
                "report": "public-audit.json",
            }
        )
        report["real_model_verified"] = True
        report["passed"] = True
        report["phase"] = "completed"
    except Exception as exc:
        # Fixed diagnostics only. Provider bodies, auth headers and credentials never printed.
        report["error"] = "acceptance_incomplete_see_step_reports_no_automatic_retry"
        report["failure_kind"] = (
            type(exc).__name__
            if type(exc).__name__
            in {
                "ValueError",
                "RuntimeError",
                "ReadTimeout",
                "ConnectError",
                "TimeoutExpired",
                "OperationalError",
                "FileNotFoundError",
            }
            else "acceptance_error"
        )
    finally:
        if before is not None:
            try:
                safe = counts(engine) == before and mail_count() == mail_before
                report["protected_records_and_mail_unchanged"] = safe
                report["passed"] = report["passed"] and safe
            except Exception:
                report["passed"] = False
                report["protected_records_and_mail_unchanged"] = None
        engine.dispose()
        report["seconds"] = round(time.monotonic() - started, 3)
        report["semantic_editor_assessment"] = (
            "not_executed; quote equality is not semantic entailment"
        )
        (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"passed": report["passed"], "report": str(out / "result.json")}, ensure_ascii=False
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
