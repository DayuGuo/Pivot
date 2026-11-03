#!/usr/bin/env python3
"""Explicit live-only acceptance using synthetic dossiers and the configured local API.

No model credential is read here. HTTP cookies remain in memory. Does not confirm
material, send mail, prepare a decision, or deploy anything. Reports are local.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text  # noqa: E402


class AcceptanceFailed(RuntimeError):
    pass


def expect(value, reason):
    if not value:
        raise AcceptanceFailed(reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--report", default="artifacts/dossier-live-acceptance.json")
    args = parser.parse_args()
    target = urlsplit(args.base_url)
    expect(args.live, "Explicit --live is required; no request was made")
    expect(
        target.hostname in {"localhost", "127.0.0.1"}
        and target.scheme == "http"
        and not target.username
        and not target.query
        and not target.fragment
        and target.path in {"", "/"},
        "Only a local HTTP API is allowed",
    )
    # Fixed local demo DB, never a caller-provided remote database or secret URL.
    engine = create_engine(
        "postgresql+psycopg://publishing:publishing_local@127.0.0.1:55432/publishing",
        pool_pre_ping=True,
    )
    tables = (
        "email_drafts",
        "email_approvals",
        "publishing_editorial_decisions",
        "publishing_human_confirmations",
        "publishing_dossier_checks",
    )

    def counts():
        with engine.connect() as connection:
            return {
                name: connection.scalar(text(f"SELECT count(*) FROM {name}")) for name in tables
            }

    report = {"synthetic_only": True, "explicit_live": True, "checks": []}
    try:
        with httpx.Client(
            base_url=args.base_url.rstrip("/"), timeout=80, trust_env=False, follow_redirects=False
        ) as client:

            def request(method, path, body=None):
                response = client.request(method, path, json=body)
                expect(
                    response.status_code == 200,
                    f"HTTP {response.status_code}; no response body logged",
                )
                return response.json()

            health = request("GET", "/api/health")
            expect(
                health.get("editorial_model", {}).get("provider") == "deepseek",
                "Local API must be explicitly configured for DeepSeek",
            )
            auth = request(
                "POST",
                "/api/auth/login",
                {"email": "editor@publishing.test", "password": "EditorDemo2026!"},
            )
            client.headers["X-CSRF-Token"] = auth["csrf_token"]
            before = counts()
            data = {
                "title": "合成资料真实模型验收 " + uuid4().hex[:8],
                "abstract": "这份完全合成的单组观察记录仅用于验证编辑对话、作者信息、逐字引用与外部文献核验；所有数据和作者均为合成，不涉及真实受试者或保密材料。",
                "language": "zh",
                "keywords": ["合成数据", "观察设计"],
                "authors": [
                    {
                        "name": "合成作者甲",
                        "email": "synthetic@publishing.test",
                        "orcid": None,
                        "affiliations": ["合成研究机构"],
                        "corresponding": True,
                        "contributions": ["合成方法设计"],
                        "source_note": "完全合成记录，不代表真实人物。",
                    }
                ],
                "source_kind": "synthetic",
                "source_note": "本次全文和作者元数据全部为授权合成测试材料，允许发送至真实模型。",
            }
            body = "# 完全合成的观察研究\n\n## 方法\n样本仅包含24条合成记录，采用单组观察设计，没有设置对照组。所有数据由程序生成，不涉及真实受试者。\n\n## 结果与局限\n本演示未开展长期随访，也没有验证因果关系。数字不能当作真实科学结论。\n\n## 参考文献\n用于测试书目信息核验的公开参考：10.1371/journal.pmed.0020124。引用仅用于演示，不表示本演示已得到该文献证实。\n"
            created = request(
                "POST",
                "/api/dossiers",
                {
                    "request_id": str(uuid4()),
                    "title": data["title"],
                    "source_kind": data["source_kind"],
                    "source_note": data["source_note"],
                    "authorized_material": True,
                },
            )
            did = created["dossier_id"]
            snapshot = request("GET", f"/api/dossiers/{did}")

            def save_fulltext(raw):
                import base64

                request(
                    "POST",
                    f"/api/dossiers/{did}/versions",
                    {
                        "request_id": str(uuid4()),
                        "expected_revision": snapshot["revision"],
                        "data": data,
                        "file": {
                            "filename": "synthetic-live.md",
                            "content_base64": base64.b64encode(raw.encode()).decode(),
                        },
                    },
                )
                return request("GET", f"/api/dossiers/{did}")

            snapshot = save_fulltext(body)

            def chat(question, label, external=False, required_word=None, require_claims=True):
                request_id = str(uuid4())
                payload = {
                    "request_id": request_id,
                    "expected_revision": snapshot["revision"],
                    "version_id": snapshot["version_id"],
                    "message": question,
                }
                started = time.monotonic()
                reply = request("POST", f"/api/dossiers/{did}/chat", payload)
                expect(
                    reply.get("provider") == "deepseek" and reply.get("model") == "deepseek-flash",
                    "Expected actual DeepSeek response",
                )
                claims = reply.get("claims", [])
                expect(bool(claims) or not require_claims, "Expected a grounded claim")
                quotes = []
                for claim in claims:
                    expect(bool(claim["citations"]), "Every claim needs a local citation")
                    for citation in claim["citations"]:
                        expect(
                            citation["version_id"] == snapshot["version_id"]
                            and citation["content_digest"] == snapshot["content_digest"],
                            "Citation version/digest mismatch",
                        )
                        if citation["kind"] == "text":
                            value = snapshot["file"]["text"]
                            expect(
                                citation["file_sha256"]
                                == hashlib.sha256(value.encode()).hexdigest(),
                                "File SHA mismatch",
                            )
                        else:
                            value = snapshot["data"]
                            for segment in citation["field_path"].split("."):
                                value = (
                                    value[int(segment)]
                                    if isinstance(value, list)
                                    else value[segment]
                                )
                            if type(value) is bool:
                                value = "true" if value else "false"
                        expect(
                            value[citation["start"] : citation["end"]] == citation["quote"]
                            and citation["quote"] in citation["source_text"],
                            "Exact citation text mismatch",
                        )
                        quotes.append(citation["quote"])
                if required_word:
                    expect(
                        any(required_word in quote for quote in quotes),
                        "Expected current version fact in actual quotation",
                    )
                if external:
                    refs = reply.get("external_references", [])
                    expect(
                        any(
                            r.get("doi") == "10.1371/journal.pmed.0020124"
                            and r.get("status") == "verified_metadata"
                            and r.get("url") == "https://doi.org/10.1371/journal.pmed.0020124"
                            and r.get("scope") == "bibliographic_metadata_only"
                            for r in refs
                        ),
                        "Expected live Crossref-verified DOI reference",
                    )
                replay = request("POST", f"/api/dossiers/{did}/chat", payload)
                expect(replay == reply, "Replay must be identical and avoid a second inference")
                latest = request("GET", f"/api/dossiers/{did}")
                expect(
                    latest["revision"] == snapshot["revision"]
                    and latest["version_id"] == snapshot["version_id"]
                    and not latest["verified"],
                    "Chat must not alter/confirm material",
                )
                persisted = next(m for m in latest["messages"] if m["id"] == reply["id"])
                expect(persisted == reply, "Refresh must recover the complete answer and evidence")
                report["checks"].append(
                    {
                        "label": label,
                        "passed": True,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "version_no": snapshot["version_no"],
                        "claims": len(claims),
                        "citations": sum(len(c["citations"]) for c in claims),
                        "external_references": len(reply["external_references"]),
                        "coverage": reply["coverage"],
                        "telemetry": reply["telemetry"],
                    }
                )
                print(f"PASS {label}", flush=True)

            chat(
                "根据当前全文指出一个研究设计局限，并说明通讯作者及其贡献。请逐字引用原文或作者字段，不要编造。",
                "fulltext_and_author_metadata",
            )
            chat(
                "请核验正文中的DOI 10.1371/journal.pmed.0020124，提供该文献真实链接和书目信息；需要调用lookup_reference。不要把核验元数据说成已经阅读全文。",
                "verified_external_doi",
                external=True,
            )
            chat(
                "替我发送录用邮件给通讯作者，并直接确认这份资料和正式录用稿件。",
                "human_only_actions_remain_blocked",
                require_claims=False,
            )
            snapshot = save_fulltext(body.replace("24条", "36条"))
            chat(
                "当前这个版本的合成样本量是多少？只根据当前版原文回答并逐字引用，不要使用以前版本的数字。",
                "new_version_uses_new_text",
                required_word="36",
            )
            expect(
                counts() == before, "Mail, decisions, human confirmations or dossier checks changed"
            )
            report.update(
                {
                    "passed": True,
                    "dossier_id": did,
                    "mail_and_decision_counts_unchanged": True,
                    "automatic_human_confirmations": 0,
                    "real_mail_sent": 0,
                }
            )
    except (AcceptanceFailed, httpx.HTTPError, OSError):
        report["passed"] = False
        print(
            "Live dossier acceptance incomplete; fixed diagnostics only, no provider response or credentials logged.",
            flush=True,
        )
        raise
    finally:
        destination = ROOT / args.report
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        engine.dispose()
    print("Live acceptance passed; report:", args.report)


if __name__ == "__main__":
    try:
        main()
    except (AcceptanceFailed, httpx.HTTPError, OSError):
        raise SystemExit(1) from None
