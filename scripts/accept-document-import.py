#!/usr/bin/env python3
"""Live synthetic PDF/DOCX acceptance; simulates the responsible demo user explicitly.

The model only proposes metadata. The test driver, outside the model tool runtime,
submits the synthetic review form as the demo editor. No real mail or editorial
human decision is executed. No model credential is read or logged.
"""

import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent


class AcceptanceFailed(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise AcceptanceFailed(code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    require(args.live, "explicit_live_required")
    engine = create_engine(
        "postgresql+psycopg://publishing:publishing_local@127.0.0.1:55432/publishing",
        pool_pre_ping=True,
    )
    report = {
        "synthetic_only": True,
        "human_actions_simulated_by_test_driver_not_model": True,
        "cases": [],
        "passed": False,
    }

    def counts():
        with engine.connect() as c:
            return {
                name: c.scalar(text(f"SELECT count(*) FROM {name}"))
                for name in (
                    "email_drafts",
                    "email_approvals",
                    "publishing_editorial_decisions",
                    "publishing_human_confirmations",
                )
            }

    try:
        with httpx.Client(
            base_url="http://127.0.0.1:8100", timeout=80, trust_env=False, follow_redirects=False
        ) as client:

            def request(method, path, body=None):
                response = client.request(method, path, json=body)
                require(response.status_code == 200, f"http_{response.status_code}")
                return response.json()

            health = request("GET", "/api/health")
            require(health["editorial_model"]["provider"] == "deepseek", "actual_deepseek_required")
            auth = request(
                "POST",
                "/api/auth/login",
                {"email": "editor@publishing.test", "password": "EditorDemo2026!"},
            )
            client.headers["X-CSRF-Token"] = auth["csrf_token"]
            before = counts()
            for ext in ("pdf", "docx"):
                started = time.monotonic()
                filename = "synthetic-manuscript." + ext
                raw = (ROOT / "tests/documents" / filename).read_bytes()
                created = request(
                    "POST",
                    "/api/dossiers",
                    {
                        "request_id": str(uuid4()),
                        "title": "合成" + ext.upper() + "导入验收 " + uuid4().hex[:8],
                        "source_kind": "synthetic",
                        "source_note": "完全合成资料；自动化验收会模拟测试编辑逐项核对，仅验证软件边界，不代表真实稿件已由人类审阅。",
                        "authorized_material": True,
                    },
                )
                did = created["dossier_id"]
                base = request("GET", f"/api/dossiers/{did}")
                payload = {
                    "request_id": str(uuid4()),
                    "expected_revision": base["revision"],
                    "version_id": base["version_id"],
                    "file": {
                        "filename": filename,
                        "content_base64": base64.b64encode(raw).decode(),
                    },
                    "authorized_material": True,
                }
                staged = request("POST", f"/api/dossiers/{did}/imports", payload)
                require(
                    request("POST", f"/api/dossiers/{did}/imports", payload) == staged,
                    "stage_replay",
                )
                draft = request("GET", f"/api/dossiers/{did}/imports/{staged['import_id']}")
                unchanged = request("GET", f"/api/dossiers/{did}")
                require(
                    unchanged["version_id"] == base["version_id"]
                    and not unchanged["verified"]
                    and unchanged["file"] is None,
                    "candidate_must_not_advance",
                )
                require(draft["metadata_provider"] == "deepseek", "real_metadata_provider")
                require(
                    "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026" in draft["text"]
                    and draft["sha256"] == hashlib.sha256(raw).hexdigest(),
                    "complete_extraction_and_original_hash",
                )
                authors = draft["proposed_data"]["authors"]
                require(
                    {a["name"] for a in authors}
                    == {"Synthetic Author Alpha", "Synthetic Author Beta"},
                    "automatic_author_names",
                )
                require(
                    {a["email"] for a in authors}
                    == {"alpha@synthetic.test", "beta@synthetic.test"},
                    "automatic_author_emails",
                )
                require(all(a["affiliations"] for a in authors), "automatic_affiliations")
                require(
                    all(
                        s["quote"] == draft["text"][s["start"] : s["end"]]
                        for s in draft["field_sources"]
                    ),
                    "candidate_quotes_exact",
                )
                original = client.get(draft["original_download_url"])
                require(
                    original.status_code == 200 and original.content == raw,
                    "original_bytes_preserved",
                )
                data = draft["proposed_data"]
                data["source_note"] = (
                    "全部为合成验收材料；此表由测试脚本明确模拟负责人核对，模型没有确认权限。"
                )
                data["title"] = data["title"] + " · 人工核对修正示例"
                approval_body = {
                    "request_id": str(uuid4()),
                    "expected_revision": base["revision"],
                    "digest": draft["digest"],
                    "data": data,
                    "acknowledged": True,
                }
                approved = request(
                    "POST", f"/api/dossiers/{did}/imports/{draft['id']}/confirm", approval_body
                )
                require(
                    request(
                        "POST", f"/api/dossiers/{did}/imports/{draft['id']}/confirm", approval_body
                    )
                    == approved,
                    "approval_exactly_once",
                )
                current = request("GET", f"/api/dossiers/{did}")
                require(
                    current["version_no"] == base["version_no"] + 1
                    and current["verified"]
                    and current["data"] == data,
                    "human_snapshot_saved",
                )
                require(
                    current["document"]["sha256"] == draft["sha256"]
                    and current["document"]["import_id"] == draft["id"],
                    "version_origin_bound",
                )
                question = {
                    "request_id": str(uuid4()),
                    "expected_revision": current["revision"],
                    "version_id": current["version_id"],
                    "message": "请逐字引用全文末尾标记 END-OF-SYNTHETIC-DOCUMENT-TRACE-2026，用一个短结论说明标记存在，引用必须包含这个完整标记；不要复述其他问题。",
                }
                reply = request("POST", f"/api/dossiers/{did}/chat", question)
                require(reply["provider"] == "deepseek", "actual_grounded_dialogue")
                citations = [
                    c
                    for claim in reply["claims"]
                    for c in claim["citations"]
                    if c["kind"] == "text" and "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026" in c["quote"]
                ]
                require(bool(citations), "tail_quote_present")
                for citation in citations:
                    require(
                        current["file"]["text"][citation["start"] : citation["end"]]
                        == citation["quote"],
                        "quote_exact",
                    )
                    origin = citation.get("document", {})
                    require(
                        origin.get("sha256") == draft["sha256"]
                        and origin.get("origin_digest") == current["document"]["origin_digest"],
                        "quote_original_fingerprint",
                    )
                    matching = [
                        s
                        for s in draft["segments"]
                        if citation["start"] < s["end"] and citation["end"] > s["start"]
                    ]
                    expected = [
                        {
                            "kind": s["kind"],
                            "number": s["number"],
                            "start": max(citation["start"], s["start"]),
                            "end": min(citation["end"], s["end"]),
                        }
                        for s in matching
                    ]
                    require(origin["locations"] == expected, "page_or_paragraph_exact")
                    require(
                        any(
                            x["kind"] == ("pdf_page" if ext == "pdf" else "docx_paragraph")
                            and x["number"] == (2 if ext == "pdf" else len(draft["segments"]))
                            for x in origin["locations"]
                        ),
                        "tail_page_or_paragraph",
                    )
                refreshed = request("GET", f"/api/dossiers/{did}")
                require(refreshed["messages"][-1] == reply, "answer_evidence_refresh")
                report["cases"].append(
                    {
                        "format": ext,
                        "passed": True,
                        "dossier_id": did,
                        "import_id": draft["id"],
                        "version_id": current["version_id"],
                        "metadata_provider": draft["metadata_provider"],
                        "authors": len(authors),
                        "field_sources": len(draft["field_sources"]),
                        "candidate_did_not_advance": True,
                        "explicit_test_driver_confirmation": True,
                        "original_download_exact": True,
                        "source_locations": citations[0]["document"]["locations"],
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "metadata_telemetry": draft["telemetry"],
                        "qa_telemetry": reply["telemetry"],
                    }
                )
                print(
                    "PASS",
                    ext,
                    "real metadata, explicit simulated human confirmation, new version and exact original location",
                    flush=True,
                )
            require(counts() == before, "mail_or_editorial_decisions_changed")
            report.update(
                passed=True,
                mail_and_editorial_decisions_unchanged=True,
                model_human_confirm_tool_calls=0,
            )
    except (AcceptanceFailed, httpx.HTTPError, OSError) as error:
        print(
            "Live document acceptance incomplete:",
            str(error) if isinstance(error, AcceptanceFailed) else "local_transport_error",
            flush=True,
        )
        raise
    finally:
        (ROOT / "artifacts").mkdir(exist_ok=True)
        (ROOT / "artifacts/document-import-live.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except (AcceptanceFailed, httpx.HTTPError, OSError):
        raise SystemExit(1) from None
