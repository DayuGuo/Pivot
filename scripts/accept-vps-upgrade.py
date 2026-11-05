#!/usr/bin/env python3
"""Verify preview.4 -> candidate upgrade and restore using fresh synthetic Mock projects.

Only bundle directories inside this repository's artifacts are accepted. Never
accept an existing state directory, live key, or user project. Data volumes are
retained; finally stops only the two random projects created by this process.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
PREVIEW4_SOURCE = "d7c90b03f612f8761d167eed866a8b63165acbfa"
BUNDLE_FILES = {
    "manage.py",
    "compose.yaml",
    "README.md",
    "NOTICES.md",
    "images.tar.gz",
    "synthetic-manuscript.pdf",
    "synthetic-manuscript.docx",
}
LIMITS = {"db": 320 * 1024**2, "api": 768 * 1024**2, "web": 384 * 1024**2}


class UpgradeError(Exception):
    """Fixed diagnostic codes only: no credentials, supplier text or file contents."""


def require(value, code):
    if not value:
        raise UpgradeError(code)


def artifact_path(path, *, must_exist=False):
    require(not ARTIFACTS.is_symlink(), "artifact_root_symlink_refused")
    require(ARTIFACTS.resolve().is_relative_to(ROOT.resolve()), "repository_artifacts_required")
    absolute = Path(path).absolute()
    # Do not follow symlinks even when their target would remain within artifacts.
    require(not absolute.is_symlink(), "artifact_symlink_refused")
    resolved = absolute.resolve()
    root = ARTIFACTS.resolve()
    require(resolved != root and resolved.is_relative_to(root), "artifact_path_required")
    for parent in (absolute, *absolute.parents):
        if parent == ARTIFACTS.absolute():
            break
        require(not parent.is_symlink(), "artifact_symlink_refused")
    if must_exist:
        require(resolved.exists(), "artifact_missing")
    return resolved


def safe_run(args, **kwargs):
    # All commands are argv arrays. Capture default output rather than emit raw
    # Compose errors, Docker metadata or any future application's startup logs.
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    result = subprocess.run(args, check=False, **kwargs)
    require(result.returncode == 0, "isolated_command_failed")
    return result


def docker_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "HOME",
            "LANG",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
            "XDG_RUNTIME_DIR",
        }
    }


def native_platform():
    value = safe_run(
        ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
        env=docker_environment(),
        text=True,
    ).stdout.strip()
    require(value in {"linux/amd64", "linux/arm64"}, "native_linux_builder_required")
    return value


def validate_bundle(path, native, *, old=False):
    bundle = artifact_path(path, must_exist=True)
    require(bundle.is_dir(), "bundle_directory_required")
    metadata = bundle / "bundle.json"
    require(metadata.is_file() and not metadata.is_symlink(), "bundle_manifest_required")
    manifest = json.loads(metadata.read_text())
    require(manifest.get("platform") == native, "bundle_platform_mismatch")
    require(
        type(manifest.get("source")) is str
        and re.fullmatch(r"[0-9a-f]{40}(?:-worktree-[0-9a-f]{64})?", manifest["source"]),
        "bundle_source_invalid",
    )
    require(not old or manifest["source"] == PREVIEW4_SOURCE, "preview4_source_required")
    require(set(manifest.get("sha256", {})) == BUNDLE_FILES, "bundle_file_allowlist_mismatch")
    require(set(manifest.get("images", {})) == {"db", "api", "web"}, "bundle_images_invalid")
    for service, name in manifest["images"].items():
        require(
            isinstance(name, str)
            and re.fullmatch(rf"pivot-app-{service}:[a-z0-9][a-z0-9._-]{{0,127}}", name),
            "bundle_images_invalid",
        )
    for name in sorted(BUNDLE_FILES):
        file = bundle / name
        digest = manifest["sha256"][name]
        require(file.is_file() and not file.is_symlink(), "bundle_file_invalid")
        require(
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "bundle_hash_invalid"
        )
        with file.open("rb") as stream:
            require(
                hashlib.file_digest(stream, "sha256").hexdigest() == digest, "bundle_hash_mismatch"
            )
    return bundle, manifest


def load_manager(bundle):
    spec = importlib.util.spec_from_file_location(
        "upgrade_manage_" + uuid4().hex, bundle / "manage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.BUNDLE.resolve() == bundle, "bundle_manager_scope_mismatch")
    # Both managers keep their independent BUNDLE globals and safe subprocess adapter.
    module.checked_run = safe_run
    module.print = lambda *args, **kwargs: None  # Only this manager's health/backup notices.
    return module


def require_test_config(state, config):
    state = artifact_path(state, must_exist=True)
    require(
        re.fullmatch(r"pivot-upgrade-(?:old|restore)-[0-9a-f]{8}", config.get("project", "")),
        "isolated_project_required",
    )
    require(config.get("key") == "" and config.get("access") == "tunnel", "mock_tunnel_required")
    require(config.get("email", "").endswith("@example.test"), "synthetic_operator_required")
    require(state.name == config["project"], "state_project_mismatch")
    require(state.stat().st_mode & 0o077 == 0, "private_state_mode_required")
    credential = state / "credentials.json"
    require(credential.is_file() and not credential.is_symlink(), "fresh_test_credentials_required")
    require(credential.stat().st_mode & 0o077 == 0, "private_credential_mode_required")


def fresh_deployment(module, manifest, suffix, phase, port, *, identity=None):
    project = f"pivot-upgrade-{phase}-{suffix}"
    state = artifact_path(ARTIFACTS / project)
    require(not state.exists(), "fresh_state_required")
    identity = identity or {
        "email": f"upgrade-{suffix}@example.test",
        "password": secrets.token_urlsafe(24),
    }
    config = module.configure(
        state,
        email=identity["email"],
        password=identity["password"],
        key="",
        access="tunnel",
        port=port,
        project=project,
    )
    require_test_config(state, config)
    return module.Deployment(state, config, manifest)


DB_SNAPSHOT = r"""
import hashlib,json
from sqlalchemy import inspect,text
from apps.api.publishing.db import engine
result={"tables":{}}
with engine.connect() as c:
 c.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
 inspection=inspect(c)
 result["schema_head"]=c.scalar(text("SELECT version_num FROM alembic_version"))
 for name in sorted(inspection.get_table_names(schema="public")):
  if name=="alembic_version": continue
  pk=inspection.get_pk_constraint(name,schema="public")["constrained_columns"]
  if not pk: raise RuntimeError("Primary key required for preservation scan")
  quote=lambda v:'"'+v.replace('"','""')+'"'
  sql="SELECT row_to_json(t)::text FROM public."+quote(name)+" t ORDER BY "+','.join('t.'+quote(k) for k in pk)
  digest=hashlib.sha256(); count=0
  for row in c.execution_options(stream_results=True).execute(text(sql)):
   raw=json.dumps(json.loads(row[0]),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
   digest.update(len(raw).to_bytes(8,'big')); digest.update(raw); count+=1
  columns=[(f["name"],str(f["type"]),f["nullable"]) for f in inspection.get_columns(name,schema="public")]
  result["tables"][name]={"rows":count,"sha256":digest.hexdigest(),"columns_sha256":hashlib.sha256(json.dumps(columns).encode()).hexdigest()}
print(json.dumps(result,sort_keys=True))
"""

CAS_SNAPSHOT = r"""
import hashlib,json,os,stat
from pathlib import Path
root=Path(os.environ["PUBLISHING_STORAGE_DIR"])
if root.is_symlink() or not root.is_dir(): raise RuntimeError("CAS directory required")
files={}
for path in sorted(root.rglob('*')):
 if path.is_symlink(): raise RuntimeError("CAS symlink refused")
 if path.is_dir(): continue
 if not stat.S_ISREG(path.stat().st_mode): raise RuntimeError("CAS ordinary file required")
 with path.open('rb') as stream: sha=hashlib.file_digest(stream,'sha256').hexdigest()
 files[str(path.relative_to(root))]={"size":path.stat().st_size,"sha256":sha}
print(json.dumps({"files":files},sort_keys=True))
"""


def capture(deployment):
    require_test_config(deployment.state, deployment.config)
    result = {}
    for key, program in (("database", DB_SNAPSHOT), ("cas", CAS_SNAPSHOT)):
        value = deployment.dc("exec", "-T", "api", "python", "-c", program, text=True).stdout
        result[key] = json.loads(value)
    return result


def compare_snapshots(before, after, *, allow_new_tables=False):
    left, right = before["database"]["tables"], after["database"]["tables"]
    require(set(left) <= set(right), "old_tables_missing")
    require(all(right[name] == item for name, item in left.items()), "old_table_content_changed")
    extra = set(right) - set(left)
    require(allow_new_tables or not extra, "unexpected_new_tables")
    require(all(right[name]["rows"] == 0 for name in extra), "new_tables_not_empty")
    old_files, new_files = before["cas"]["files"], after["cas"]["files"]
    require(set(old_files) <= set(new_files), "old_cas_files_missing")
    require(
        all(new_files[name] == item for name, item in old_files.items()), "old_cas_content_changed"
    )
    require(allow_new_tables or old_files == new_files, "restore_cas_set_changed")
    return {
        "old_tables": len(left),
        "old_rows": sum(v["rows"] for v in left.values()),
        "new_empty_tables": len(extra),
        "old_cas_files": len(old_files),
        "new_cas_files": len(set(new_files) - set(old_files)),
        "schema_before": before["database"]["schema_head"],
        "schema_after": after["database"]["schema_head"],
        "all_old_tables_equal": True,
        "all_old_cas_equal": True,
    }


def forbidden_activity(snapshot):
    tables = snapshot["database"]["tables"]
    names = (
        "email_drafts",
        "email_approvals",
        "publishing_editorial_decisions",
        "publishing_human_confirmations",
    )
    require(all(name in tables for name in names), "safety_tables_missing")
    counts = {name: tables[name]["rows"] for name in names}
    require(all(value == 0 for value in counts.values()), "mail_or_formal_decision_created")
    return counts


def projection_preserved(before, after):
    """Allow additive API fields, but no missing or changed historical value."""
    if isinstance(before, dict):
        return isinstance(after, dict) and all(
            key in after and projection_preserved(value, after[key])
            for key, value in before.items()
        )
    if isinstance(before, list):
        return (
            isinstance(after, list)
            and len(before) == len(after)
            and all(projection_preserved(a, b) for a, b in zip(before, after, strict=True))
        )
    return type(before) is type(after) and before == after


def request(client, method, path, data=None):
    response = client.request(method, path, json=data)
    require(response.status_code == 200, "synthetic_http_request_failed")
    return response.json()


def health(client):
    value = request(client, "GET", "/api/health")
    require(value.get("email_send_enabled") is False, "mail_must_remain_disabled")
    require(value.get("editorial_model", {}).get("provider") == "mock", "mock_provider_required")


def seed_documents(client, bundle, config):
    denied = client.post(
        "/api/auth/login", json={"email": "editor@publishing.test", "password": "EditorDemo2026!"}
    )
    require(denied.status_code == 401, "published_demo_login_must_fail")
    auth = request(
        client,
        "POST",
        "/api/auth/login",
        {"email": config["email"], "password": config["password"]},
    )
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
    saved = []
    for ext in ("pdf", "docx"):
        raw = (bundle / f"synthetic-manuscript.{ext}").read_bytes()
        created = request(
            client,
            "POST",
            "/api/dossiers",
            {
                "request_id": str(uuid4()),
                "title": "合成升级验证 " + ext,
                "source_kind": "synthetic",
                "source_note": "完全合成；自动脚本模拟负责人核对，不是编辑或作者实际签署。",
                "authorized_material": True,
            },
        )
        did = created["dossier_id"]
        base = request(client, "GET", f"/api/dossiers/{did}")
        staged = request(
            client,
            "POST",
            f"/api/dossiers/{did}/imports",
            {
                "request_id": str(uuid4()),
                "expected_revision": base["revision"],
                "version_id": base["version_id"],
                "authorized_material": True,
                "file": {
                    "filename": f"synthetic-manuscript.{ext}",
                    "content_base64": base64.b64encode(raw).decode(),
                },
            },
        )
        draft = request(client, "GET", f"/api/dossiers/{did}/imports/{staged['import_id']}")
        require(draft["metadata_provider"] == "mock", "mock_extraction_required")
        require(
            draft["sha256"] == hashlib.sha256(raw).hexdigest(), "synthetic_original_hash_mismatch"
        )
        require("END-OF-SYNTHETIC-DOCUMENT-TRACE-2026" in draft["text"], "document_tail_missing")
        data = draft["proposed_data"]
        require(len(data["authors"]) == 2, "synthetic_author_extraction_missing")
        request(
            client,
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
        current = request(client, "GET", f"/api/dossiers/{did}")
        require(current["verified"] and current["version_no"] == 2, "simulated_review_not_saved")
        answer = request(
            client,
            "POST",
            f"/api/dossiers/{did}/chat",
            {
                "request_id": str(uuid4()),
                "expected_revision": current["revision"],
                "version_id": current["version_id"],
                "message": "请逐字引用原件全文末尾标记 END-OF-SYNTHETIC-DOCUMENT-TRACE-2026，给出一个简短结论。",
            },
        )
        require(answer["provider"] == "mock" and answer["claims"], "mock_answer_required")
        snapshot = request(client, "GET", f"/api/dossiers/{did}")
        saved.append(
            {
                "id": did,
                "snapshot": snapshot,
                "download_url": draft["original_download_url"],
                "raw": raw,
            }
        )
    verify_documents(client, saved)
    return saved


def verify_documents(client, saved):
    health(client)
    session = request(client, "GET", "/api/publishing/session")
    require(session["user"]["role"] == "editor", "private_editor_session_required")
    for case in saved:
        snapshot = request(client, "GET", f"/api/dossiers/{case['id']}")
        require(
            projection_preserved(case["snapshot"], snapshot), "historical_api_projection_changed"
        )
        raw = client.get(case["download_url"])
        require(
            raw.status_code == 200 and raw.content == case["raw"], "historical_original_changed"
        )
        verify_baseline_version(client, case, snapshot)


def verify_baseline_version(client, case, snapshot):
    version_id = case["snapshot"]["version_id"]
    historical = request(client, "GET", f"/api/dossiers/{case['id']}/versions/{version_id}")
    for field in ("version_id", "version_no", "content_digest", "data", "file", "document"):
        require(historical[field] == case["snapshot"][field], "historical_version_source_changed")
    for message in snapshot["messages"]:
        for claim in message.get("claims", []) + message.get("withheld_claims", []):
            for citation in claim.get("citations", []):
                if citation["kind"] != "text":
                    continue
                require(
                    citation["version_id"] == case["snapshot"]["version_id"],
                    "wrong_version_citation",
                )
                content = case["snapshot"]["file"]["text"]
                require(
                    content[citation["start"] : citation["end"]] == citation["quote"],
                    "historical_quote_changed",
                )
                require(
                    citation.get("document", {}).get("sha256")
                    == hashlib.sha256(case["raw"]).hexdigest()
                    and citation["document"]["locations"],
                    "historical_original_location_missing",
                )


def exercise_candidate(client, saved):
    old = saved[0]["snapshot"]
    did = saved[0]["id"]
    original = old["file"]["text"]
    revised = (
        original + "\nSynthetic update: an explicit revision package is preserved by backup.\n"
    )
    new = request(
        client,
        "POST",
        f"/api/dossiers/{did}/versions",
        {
            "request_id": str(uuid4()),
            "expected_revision": old["revision"],
            "data": old["data"],
            "file": {
                "filename": "synthetic-revised.txt",
                "content_base64": base64.b64encode(revised.encode()).decode(),
            },
        },
    )
    current = request(client, "GET", f"/api/dossiers/{did}")
    check = request(
        client,
        "POST",
        f"/api/dossiers/{did}/revision-checks",
        {
            "request_id": str(uuid4()),
            "expected_revision": current["revision"],
            "base_version_id": old["version_id"],
            "revised_version_id": new["version_id"],
            "base_complete": True,
            "revised_complete": True,
            "requirements": [
                {
                    "text": "请补充明确的修回说明。",
                    "original_context": "合成编辑建议：请补充明确的修回说明，用于演示材料绑定和人工核对。",
                }
            ],
            "requirements_complete": True,
            "response_text": "作者合成回复：已经补充修回说明，仍需核对实际正文。",
            "response_complete": True,
            "source_note": "完全合成；测试驱动模拟独立人审，不是作者或专家实际意见。",
            "authorized_material": True,
        },
    )
    path = f"/api/dossiers/{did}/revision-checks/{check['check_id']}"
    packet = request(client, "GET", path)
    require(packet["report"]["provider"] == "mock", "candidate_must_not_call_live_model")
    request(
        client,
        "POST",
        path + "/points/P01/reviews",
        {
            "request_id": str(uuid4()),
            "check_digest": packet["digest"],
            "expected_review_id": None,
            "response_verdict": "addressed",
            "implementation_verdict": "changed",
            "editor_verdict": "needs_judgment",
            "reason": "测试脚本核对了合成新旧材料，仅验证三层人判记录可恢复，不是专家评价。",
            "acknowledged": True,
        },
    )
    packet = request(client, "GET", path)
    require(
        packet["reviews"]["P01"]["editor_verdict"] == "needs_judgment",
        "candidate_human_record_missing",
    )
    require(
        request(client, "GET", path + "/export")["digest"] == packet["digest"],
        "candidate_export_mismatch",
    )
    return path, packet


def metrics(deployment):
    require_test_config(deployment.state, deployment.config)
    result = {}
    for service in ("db", "api", "web"):
        cid = deployment.dc("ps", "-q", service, text=True).stdout.strip()
        require(re.fullmatch(r"[0-9a-f]{12,64}", cid), "isolated_service_missing")
        raw = deployment.raw(
            "inspect",
            cid,
            "--format",
            '{"limit_bytes":{{.HostConfig.Memory}},"oom_killed":{{.State.OOMKilled}},"running":{{.State.Running}},"restarts":{{.RestartCount}},"image_id":"{{.Image}}"}',
            text=True,
        ).stdout
        state = json.loads(raw)
        require(state["limit_bytes"] == LIMITS[service], "private_container_limit_changed")
        require(
            state["running"] and not state["oom_killed"] and state["restarts"] == 0,
            "service_oom_or_restart",
        )
        peak = None
        for file in (
            "/sys/fs/cgroup/memory.peak",
            "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
        ):
            try:
                value = deployment.dc("exec", "-T", service, "cat", file, text=True).stdout.strip()
                if value.isdigit():
                    peak = int(value)
                    break
            except UpgradeError:
                pass
        result[service] = {**state, "observed_peak_bytes": peak}
    return result


def running_ids():
    value = safe_run(
        ["docker", "ps", "--format", "{{.ID}}"], env=docker_environment(), text=True
    ).stdout
    return set(value.split())


def report_location(path):
    path = artifact_path(path)
    require(
        re.fullmatch(r"vps-upgrade(?:-[a-z0-9._-]+)?\.json", path.name),
        "upgrade_report_name_required",
    )
    return path


def write_report(path, report):
    path = report_location(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(
        os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "w"
    ) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run(old_path, candidate_path, *, port, report_path):
    started = time.monotonic()
    os.umask(0o077)
    require(type(port) is int and 1024 <= port <= 65534, "loopback_port_invalid")
    report_path = report_location(report_path)
    native = native_platform()
    old_bundle, old_manifest = validate_bundle(old_path, native, old=True)
    candidate_bundle, candidate_manifest = validate_bundle(candidate_path, native)
    require(
        old_bundle != candidate_bundle and old_manifest["source"] != candidate_manifest["source"],
        "different_candidate_required",
    )
    old_module, module = load_manager(old_bundle), load_manager(candidate_bundle)
    suffix = uuid4().hex[:8]
    old = fresh_deployment(old_module, old_manifest, suffix, "old", port)
    deployment = module.Deployment(old.state, old.config, candidate_manifest)
    require_test_config(deployment.state, deployment.config)
    restored = None
    before_containers = running_ids()
    report = {
        "passed": False,
        "platform": native,
        "provider": "mock",
        "email_send_enabled": False,
        "old_source": old_manifest["source"],
        "candidate_source": candidate_manifest["source"],
        "old_project": old.config["project"],
        "old_state": str(old.state),
        "human_confirmation_simulated_by_test_driver": True,
        "scope": "native isolated synthetic upgrade/restore; not the user VPS or an editorial evaluation",
    }
    try:
        report["stage"] = "old_start"
        old.up()
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=90
        ) as client:
            report["stage"] = "old_seed"
            saved = seed_documents(client, old_bundle, old.config)
            report["old_memory"] = metrics(old)
            before = capture(old)
            forbidden_activity(before)
            report["stage"] = "old_backup"
            old.backup()
            compare_snapshots(before, capture(old))
            # Same dedicated state and volumes; mandatory backup used the old source bundle.
            report["stage"] = "candidate_upgrade"
            deployment.up(updating=True)
            upgraded = capture(deployment)
            report["upgrade"] = compare_snapshots(before, upgraded, allow_new_tables=True)
            verify_documents(client, saved)  # Existing cookie/session, no replacement login.
            report["old_cookie_and_citations_preserved"] = True
            report["stage"] = "candidate_feature"
            check_path, check_packet = exercise_candidate(client, saved)
            # New feature writes occur after the strict old-row preservation comparison.
            expected = {
                case["id"]: request(client, "GET", f"/api/dossiers/{case['id']}") for case in saved
            }
            report["candidate_memory"] = metrics(deployment)
            report["stage"] = "candidate_backup"
            backup_before = capture(deployment)
            backup = deployment.backup()
            after_backup = capture(deployment)
            compare_snapshots(backup_before, after_backup)
            restored = fresh_deployment(
                module, candidate_manifest, suffix, "restore", port + 1, identity=old.config
            )
            report["stage"] = "candidate_restore"
            restored.restore(backup)
            cloned = capture(restored)
            report["restore"] = compare_snapshots(after_backup, cloned)
            report["mail_and_formal_decision_counts"] = forbidden_activity(cloned)
            report["stage"] = "restored_readback"
            require(
                cloned["database"]["schema_head"] == after_backup["database"]["schema_head"],
                "restored_schema_mismatch",
            )
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port + 1}",
                trust_env=False,
                timeout=90,
                cookies=client.cookies,
            ) as clone:
                health(clone)
                for case in saved:
                    value = request(clone, "GET", f"/api/dossiers/{case['id']}")
                    require(value == expected[case["id"]], "restored_snapshot_changed")
                    verify_baseline_version(clone, case, value)
                    original = clone.get(case["download_url"])
                    require(
                        original.status_code == 200 and original.content == case["raw"],
                        "restored_original_changed",
                    )
                require(
                    request(clone, "GET", check_path) == check_packet,
                    "restored_revision_check_changed",
                )
            report["restore_memory"] = metrics(restored)
            report["restore_project"] = restored.config["project"]
            report["restore_state"] = str(restored.state)
            report["snapshot_hashes"] = {
                "before_upgrade": before,
                "after_upgrade": upgraded,
                "before_restore": after_backup,
                "restored": cloned,
            }
            report["existing_service_ids_unchanged"] = before_containers <= running_ids()
            require(report["existing_service_ids_unchanged"], "unrelated_service_changed")
            report["passed"] = True
            report["stage"] = "completed"
    except Exception as error:
        report["failure_code"] = (
            str(error) if isinstance(error, UpgradeError) else "isolated_upgrade_acceptance_failed"
        )
        raise
    finally:
        stopped = True
        for active in (restored, deployment):
            if active is None:
                continue
            try:
                require_test_config(active.state, active.config)
                active.dc("stop")
            except Exception:
                stopped = False
        report["test_projects_stopped"] = stopped
        report["passed"] = report["passed"] and stopped
        report["data_volumes_retained"] = True
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        write_report(report_path, report)
    require(report["test_projects_stopped"], "test_project_stop_failed")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-bundle", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--port", type=int, default=13320)
    parser.add_argument("--report", type=Path, default=ARTIFACTS / "vps-upgrade-acceptance.json")
    args = parser.parse_args()
    try:
        report = run(args.old_bundle, args.bundle, port=args.port, report_path=args.report)
    except Exception:
        # No raw exception, command, config, cookie, password or source body output.
        print(json.dumps({"passed": False, "error": "isolated_upgrade_acceptance_failed"}))
        raise SystemExit(2) from None
    print(json.dumps({"passed": report["passed"], "provider": "mock", "report": str(args.report)}))


if __name__ == "__main__":
    main()
