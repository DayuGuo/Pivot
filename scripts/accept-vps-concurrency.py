#!/usr/bin/env python3
"""Burst only the isolated Mock install produced by accept-vps-preview.py."""

import base64
import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    accepted = json.loads((ROOT / "artifacts/vps-preview-acceptance.json").read_text())
    require(accepted["passed"] and accepted["provider"] == "mock", "Isolated Mock install required")
    state = Path(accepted["state"]).resolve()
    require(state.is_relative_to(ROOT / "artifacts"), "Only local test state is allowed")
    config = json.loads((state / "credentials.json").read_text())
    require(config["project"].startswith("pivot-check-") and not config["key"], "Test project only")
    origin = f"http://127.0.0.1:{config['port']}"
    with httpx.Client(base_url=origin, trust_env=False, timeout=90) as client:
        response = client.post(
            "/api/auth/login", json={"email": config["email"], "password": config["password"]}
        )
        require(response.status_code == 200, "Test login failed")
        csrf = response.json()["csrf_token"]
        dossier = accepted["cases"][0]["dossier_id"]
        before = client.get(f"/api/dossiers/{dossier}").json()
        body = {
            "expected_revision": before["revision"],
            "version_id": before["version_id"],
            "authorized_material": True,
            "file": {
                "filename": "synthetic-burst.docx",
                "content_base64": base64.b64encode(
                    (ROOT / "tests/documents/synthetic-manuscript.docx").read_bytes()
                ).decode(),
            },
        }
        barrier = threading.Barrier(4)
        cookies = dict(client.cookies)

        def submit(_):
            request = {**body, "request_id": str(uuid4())}
            with httpx.Client(
                base_url=origin,
                trust_env=False,
                timeout=90,
                cookies=cookies,
                headers={"X-CSRF-Token": csrf},
            ) as peer:
                barrier.wait(timeout=10)
                response = peer.post(f"/api/dossiers/{dossier}/imports", json=request)
                return request, response.status_code, response.headers.get("retry-after")

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            attempts = list(pool.map(submit, range(4)))
        statuses = [status for _, status, _ in attempts]
        require(
            200 in statuses and 429 in statuses and set(statuses) <= {200, 429},
            "Burst did not exercise admission cleanly",
        )
        for request, status, retry_after in attempts:
            if status != 429:
                continue
            require(retry_after == "2", "Retry-After was not forwarded")
            time.sleep(2)
            response = client.post(
                f"/api/dossiers/{dossier}/imports", json=request, headers={"X-CSRF-Token": csrf}
            )
            require(
                response.status_code == 200, "Rejected request could not recover with same UUID"
            )
            recovered = response.json()
            replay = client.post(
                f"/api/dossiers/{dossier}/imports", json=request, headers={"X-CSRF-Token": csrf}
            )
            require(
                replay.status_code == 200 and replay.json() == recovered,
                "Recovered receipt is not idempotent",
            )
        after = client.get(f"/api/dossiers/{dossier}").json()
        require(before == after, "Import admission changed the approved version or conversation")
        health = client.get("/api/health").json()
        require(health["email_send_enabled"] is False, "Mail must stay disabled")
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={config['project']}",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    require(len(containers) == 3, "Isolated services are not all running")
    memory = {}
    for container in containers:
        inspected = json.loads(
            subprocess.run(
                ["docker", "inspect", container], capture_output=True, text=True, check=True
            ).stdout
        )[0]
        service = inspected["Config"]["Labels"]["com.docker.compose.service"]
        require(not inspected["State"]["OOMKilled"], "A test service was OOM killed")
        peak = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-c",
                "cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        memory[service] = {
            "limit_bytes": inspected["HostConfig"]["Memory"],
            "observed_peak_bytes": int(peak),
            "oom_killed": False,
        }
    report = {
        "passed": True,
        "parallel_requests": 4,
        "memory": memory,
        "statuses": statuses,
        "same_uuid_recovery_and_replay": True,
        "full_dossier_unchanged": True,
        "confirmations": 0,
        "mail_or_decision_requests": 0,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "scope": "isolated Mock preview; single process, not user VPS capacity",
    }
    (ROOT / "artifacts/vps-concurrency.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
