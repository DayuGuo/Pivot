#!/usr/bin/env python3
"""Exercise the actual offline bundle on a fresh isolated project, never the VPS.

Uses synthetic documents and test-driver human actions. --live borrows only the
selected local app's scoped model environment in memory, never writes its key.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--port", default=13210, type=int)
    parser.add_argument("--report", default="artifacts/vps-preview-acceptance.json")
    args = parser.parse_args()
    bundle = args.bundle.absolute()
    spec = importlib.util.spec_from_file_location("preview_accept_manage", bundle / "manage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    os.umask(0o077)
    suffix = uuid4().hex[:8]
    state = ROOT / "artifacts" / ("preview-state-" + suffix)
    config = module.configure(
        state,
        email=f"preview-{suffix}@example.test",
        password=secrets.token_urlsafe(24),
        key="",
        access="tunnel",
        port=args.port,
        project="pivot-check-" + suffix,
    )
    if args.live:
        # Precisely scoped existing application environment; never print/copy a key
        # into arguments, files, reports, subprocess errors or a provider log.
        captured = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import os; print(os.environ.get('DEEPSEEK_API_KEY','') if os.environ.get('EDITORIAL_MODEL_PROVIDER')=='deepseek' else '')",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        require(
            captured.returncode == 0 and len(captured.stdout.strip()) >= 24,
            "Fresh scoped local model configuration required",
        )
        config["key"] = captured.stdout.strip()
        captured = None
    expected = "deepseek" if args.live else "mock"
    manifest = module.release()
    deployment = module.Deployment(state, config, manifest)
    report = {
        "passed": False,
        "platform": manifest["platform"],
        "source": manifest["source"],
        "provider": expected,
        "state": str(state),
        "project": config["project"],
        "cases": [],
        "human_confirmation_simulated_by_test_driver": True,
    }
    original_projects = subprocess.run(
        ["docker", "ps", "--format", "{{.ID}} {{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    original_projects = [
        line for line in original_projects if "publishing-os-verification-" not in line
    ]
    deployment.up()
    saved = []
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", timeout=85, trust_env=False
    ) as client:

        def request(method, path, data=None):
            response = client.request(method, path, json=data)
            require(
                response.status_code == 200,
                f"HTTP {response.status_code} at {path}; body not logged",
            )
            return response.json()

        # Published demo passwords must not authenticate in the packaged database.
        denied = client.post(
            "/api/auth/login",
            json={"email": "editor@publishing.test", "password": "EditorDemo2026!"},
        )
        require(denied.status_code == 401, "Published credentials must be disabled")
        auth = request(
            "POST", "/api/auth/login", {"email": config["email"], "password": config["password"]}
        )
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        for ext in ("pdf", "docx"):
            started = time.monotonic()
            raw = (bundle / f"synthetic-manuscript.{ext}").read_bytes()
            dossier = request(
                "POST",
                "/api/dossiers",
                {
                    "request_id": str(uuid4()),
                    "title": "部署包合成导入 " + ext,
                    "source_kind": "synthetic",
                    "source_note": "完全合成、允许发送模型；测试驱动模拟负责人核对，不代表专家签收。",
                    "authorized_material": True,
                },
            )
            did = dossier["dossier_id"]
            base = request("GET", f"/api/dossiers/{did}")
            staged = request(
                "POST",
                f"/api/dossiers/{did}/imports",
                {
                    "request_id": str(uuid4()),
                    "expected_revision": base["revision"],
                    "version_id": base["version_id"],
                    "file": {
                        "filename": f"synthetic-manuscript.{ext}",
                        "content_base64": base64.b64encode(raw).decode(),
                    },
                    "authorized_material": True,
                },
            )
            draft = request("GET", f"/api/dossiers/{did}/imports/{staged['import_id']}")
            before = request("GET", f"/api/dossiers/{did}")
            require(
                before["version_id"] == base["version_id"] and not before["verified"],
                "Model must not confirm or advance a version",
            )
            require(draft["metadata_provider"] == expected, "Wrong extraction provider")
            require(
                draft["sha256"] == hashlib.sha256(raw).hexdigest()
                and "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026" in draft["text"],
                "Missing original or document tail",
            )
            data = draft["proposed_data"]
            # Explicit independent test-driver review, not model approval.
            require(len(data["authors"]) == 2, "Expected two synthetic authors")
            data["source_note"] = "全部合成，测试脚本逐项核对，模型没有确认工具。"
            request(
                "POST",
                f"/api/dossiers/{did}/imports/{draft['id']}/confirm",
                {
                    "request_id": str(uuid4()),
                    "expected_revision": base["revision"],
                    "digest": draft["digest"],
                    "data": data,
                    "acknowledged": True,
                },
            )
            current = request("GET", f"/api/dossiers/{did}")
            require(
                current["verified"] and current["version_no"] == 2,
                "Independent review did not persist",
            )
            answer = request(
                "POST",
                f"/api/dossiers/{did}/chat",
                {
                    "request_id": str(uuid4()),
                    "expected_revision": current["revision"],
                    "version_id": current["version_id"],
                    "message": "仅回答这一题，请逐字引用原件全文末尾标记 END-OF-SYNTHETIC-DOCUMENT-TRACE-2026，给出一个标记存在的短结论。",
                },
            )
            require(answer["provider"] == expected and answer["claims"], "Grounded answer missing")
            citations = [citation for claim in answer["claims"] for citation in claim["citations"]]
            require(bool(citations), "No citations")
            for citation in citations:
                require(citation["kind"] == "text", "Expected original-text citation")
                require(
                    current["file"]["text"][citation["start"] : citation["end"]]
                    == citation["quote"],
                    "Original quote span mismatch",
                )
                require(
                    citation["document"]["sha256"] == draft["sha256"]
                    and citation["document"]["locations"],
                    "Missing original page/paragraph binding",
                )
            original = client.get(draft["original_download_url"]).content
            require(original == raw, "Downloaded original differs")
            saved.append(
                (did, request("GET", f"/api/dossiers/{did}"), draft["original_download_url"], raw)
            )
            report["cases"].append(
                {
                    "format": ext,
                    "dossier_id": did,
                    "citations": len(citations),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "original_sha": draft["sha256"],
                }
            )
        # No model is asked to perform a final decision or send mail.
        counters = "import json; from sqlalchemy import text; from apps.api.publishing.db import engine; names=['email_drafts','email_approvals','publishing_editorial_decisions','publishing_human_confirmations']; c=engine.connect(); print(json.dumps({n:c.scalar(text('SELECT count(*) FROM '+n)) for n in names}))"
        counts = json.loads(
            deployment.dc(
                "exec", "-T", "api", "python", "-c", counters, stdout=subprocess.PIPE, text=True
            ).stdout
        )
        require(
            all(value == 0 for value in counts.values()),
            "Mail or formal decisions unexpectedly created",
        )
        memory = {}
        for service in ("db", "api", "web"):
            cid = deployment.dc(
                "ps", "-q", service, stdout=subprocess.PIPE, text=True
            ).stdout.strip()
            metrics = deployment.raw(
                "inspect",
                cid,
                "--format",
                "{{.HostConfig.Memory}} {{.State.OOMKilled}}",
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.split()
            peak = deployment.dc(
                "exec",
                "-T",
                service,
                "sh",
                "-c",
                "cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes",
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            require(metrics[1] == "false", "Service was OOM killed")
            memory[service] = {
                "limit_bytes": int(metrics[0]),
                "observed_peak_bytes": int(peak),
                "oom_killed": False,
            }
        report["memory"] = memory
        deployment.dc("restart", "api", "web")
        for _attempt in range(60):
            try:
                if client.get("/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        for did, snapshot, path, raw in saved:
            require(
                request("GET", f"/api/dossiers/{did}") == snapshot,
                "Restart lost metadata/messages/session",
            )
            require(client.get(path).content == raw, "Restart lost original bytes")
        backup = deployment.backup()
        restore_state = ROOT / "artifacts" / ("preview-restore-" + suffix)
        restored_config = module.configure(
            restore_state,
            email=config["email"],
            password=config["password"],
            key="",
            access="tunnel",
            port=args.port + 1,
            project="pivot-restore-" + suffix,
        )
        restored_config["key"] = config["key"]
        restored = module.Deployment(restore_state, restored_config, manifest)
        restored.restore(backup)
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port + 1}",
            timeout=20,
            trust_env=False,
            cookies=client.cookies,
        ) as clone:
            for did, snapshot, path, raw in saved:
                r = clone.get(f"/api/dossiers/{did}")
                require(
                    r.status_code == 200 and r.json() == snapshot,
                    "Isolated restore lost complete snapshot/session",
                )
                require(clone.get(path).content == raw, "Isolated restore lost original bytes")
        report["restore_project"] = restored_config["project"]
        report["restore_state"] = str(restore_state)
        restored.dc("stop")
    remaining = subprocess.run(
        ["docker", "ps", "--format", "{{.ID}} {{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    require(set(original_projects).issubset(set(remaining)), "Existing service containers changed")
    report.update(
        passed=True,
        restart_full_snapshot_equal=True,
        isolated_restore_full_snapshot_equal=True,
        existing_service_ids_unchanged=True,
        mail_and_decisions=counts,
    )
    # Keep the test service for a separately executed real browser check. Do not
    # delete its data or any other project's volumes/containers.
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {"passed": True, "provider": expected, "report": args.report, "cases": len(saved)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
