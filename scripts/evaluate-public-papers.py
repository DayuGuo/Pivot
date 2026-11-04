#!/usr/bin/env python3
"""Explicit public-paper evaluation. Fetch licensed originals, stage with real DeepSeek, audit.

No model key is read. --stage requires --live and creates private test dossiers;
human confirmation is deliberately left to the separate browser review driver.
"""

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from packages.document_ingest import extract_document  # noqa: E402

MANIFEST = ROOT / "evals/public_documents/manifest.json"
CACHE = ROOT / "artifacts/public-papers"


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def compact(value):
    return "".join(unicodedata.normalize("NFKC", value).split())


def files(manifest):
    return [(paper, f) for paper in manifest["papers"] for f in paper["files"]]


def check_file(spec):
    path = CACHE / spec["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
        raise RuntimeError("evaluation_file_hash_mismatch")
    return path


def fetch(manifest):
    with httpx.Client(timeout=45, trust_env=False, follow_redirects=True) as client:
        for _, spec in files(manifest):
            target = CACHE / spec["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                if "bundled" in spec:
                    shutil.copyfile(MANIFEST.parent / spec["bundled"], target)
                else:
                    response = client.get(spec["url"])
                    response.raise_for_status()
                    if len(response.content) > 5 * 1024 * 1024:
                        raise RuntimeError("public_file_size_changed")
                    target.write_bytes(response.content)
            check_file(spec)
    print("PASS: six exact public original/labelled derivative files available")


def stage(manifest, staging_path=None):
    staging_path = Path(staging_path or CACHE / "staging.json")
    result = {"schema": "public_paper_staging.v1", "cases": [], "passed": False}
    with httpx.Client(base_url="http://127.0.0.1:8100", timeout=80, trust_env=False) as client:
        assert client.get("/api/health").json()["editorial_model"]["provider"] == "deepseek"
        response = client.post(
            "/api/auth/login",
            json={"email": "editor@publishing.test", "password": "EditorDemo2026!"},
        )
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        for paper, spec in files(manifest):
            path = check_file(spec)
            created = client.post(
                "/api/dossiers",
                json={
                    "request_id": str(uuid4()),
                    "title": "公开论文评测 " + spec["case"],
                    "source_kind": "public_authorized",
                    "source_note": paper["review_data"]["source_note"],
                    "authorized_material": True,
                },
            )
            created.raise_for_status()
            did = created.json()["dossier_id"]
            before = client.get(f"/api/dossiers/{did}").json()
            response = client.post(
                f"/api/dossiers/{did}/imports",
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": before["revision"],
                    "version_id": before["version_id"],
                    "file": {
                        "filename": path.name,
                        "content_base64": base64.b64encode(path.read_bytes()).decode(),
                    },
                    "authorized_material": True,
                },
            )
            case = {
                "case": spec["case"],
                "path": spec["path"],
                "dossier_id": did,
                "http_status": response.status_code,
                "sha256": spec["sha256"],
            }
            if response.status_code == 200:
                iid = response.json()["import_id"]
                draft = client.get(f"/api/dossiers/{did}/imports/{iid}").json()
                candidate_path = staging_path.parent / (spec["case"] + ".candidate.json")
                save(candidate_path, draft)
                case["import_id"] = iid
                case["candidate_path"] = (
                    str(candidate_path.resolve())
                    if staging_path.parent.resolve() != CACHE.resolve()
                    else candidate_path.name
                )
            after = client.get(f"/api/dossiers/{did}").json()
            assert after["version_id"] == before["version_id"] and not after["verified"]
            case["candidate_did_not_advance"] = True
            result["cases"].append(case)
            save(staging_path, result)
            print(spec["case"], response.status_code, flush=True)
    result["passed"] = all(c["http_status"] == 200 for c in result["cases"])
    save(staging_path, result)
    if not result["passed"]:
        raise RuntimeError("public_metadata_stage_failed_see_safe_audit_diagnostics")


def author_audit(expected, actual):
    result = {
        "expected_authors": len(expected),
        "extracted_authors": len(actual),
        "name_errors": [],
        "affiliation_errors": [],
        "missing_affiliations": [],
        "email_errors": [],
        "missing_emails": [],
    }
    for i, gold in enumerate(expected):
        if i >= len(actual):
            result["name_errors"].append(i)
            continue
        author = actual[i]
        if compact(author["name"]) != compact(gold["name"]):
            result["name_errors"].append(i)
        allowed = {compact(v) for v in gold["affiliations"]}
        found = {compact(v) for v in author["affiliations"]}
        if found - allowed:
            result["affiliation_errors"].append(i)
        if allowed - found:
            result["missing_affiliations"].append(i)
        if author["email"] and author["email"] != gold["email"]:
            result["email_errors"].append(i)
        if gold["email"] and not author["email"]:
            result["missing_emails"].append(i)
    result["passed"] = len(actual) == len(expected) and not any(
        result[k] for k in ("name_errors", "affiliation_errors", "email_errors")
    )
    return result


def audit(manifest, staged_path, report_path=None):
    staged = {c["case"]: c for c in load(staged_path)["cases"]}
    results = []
    for paper, spec in files(manifest):
        path = check_file(spec)
        extracted = extract_document(path.name, path.read_bytes())
        case = staged[spec["case"]]
        draft = load(CACHE / case.get("candidate_path", spec["case"] + ".candidate.json"))
        assert draft["sha256"] == spec["sha256"] and draft["text"] == extracted["text"]
        for source in draft["field_sources"]:
            assert extracted["text"][source["start"] : source["end"]] == source["quote"]
            if not source["field_path"].endswith(".corresponding"):
                assert source["value"] in source["quote"]
        item = {
            "case": spec["case"],
            "metadata": author_audit(
                paper["review_data"]["authors"], draft["proposed_data"]["authors"]
            ),
            "chars": len(extracted["text"]),
            "segments": len(extracted["segments"]),
            "exact_field_sources": len(draft["field_sources"]),
            "metadata_uncertainties": draft.get("metadata_uncertainties", []),
            "warnings": extracted["warnings"],
        }
        if spec["format"] == "pdf":
            pages = []
            for segment in extracted["segments"]:
                response = subprocess.run(
                    [
                        "pdftotext",
                        "-raw",
                        "-f",
                        str(segment["number"]),
                        "-l",
                        str(segment["number"]),
                        str(path),
                        "-",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                reference = compact(response.stdout)
                actual = compact(segment["text"])
                # Independent per-page character multiset, plus retained text for
                # manual section/reading-order review; not a semantic completeness proof.
                counts = Counter(reference)
                matched = sum((counts & Counter(actual)).values())
                pages.append(
                    {
                        "page": segment["number"],
                        "reference_chars": len(reference),
                        "extracted_chars": len(actual),
                        "character_recall": round(matched / max(len(reference), 1), 5),
                    }
                )
            item["independent_poppler_pages"] = pages
            item["lowest_page_character_recall"] = min(p["character_recall"] for p in pages)
        else:
            reference_dir = CACHE / "independent-word" / paper["id"]
            references = sorted(reference_dir.glob("*.txt")) if reference_dir.exists() else []
            if references:
                reference = references[0].read_text(encoding="utf-8-sig")
                original = compact(extracted["text"])
                paragraphs = [
                    line.strip() for line in reference.splitlines() if len(line.strip()) >= 40
                ]
                missing = [i for i, line in enumerate(paragraphs) if compact(line) not in original]
                counts = Counter(compact(reference))
                item["independent_libreoffice"] = {
                    "reference_chars": sum(counts.values()),
                    "character_recall": round(
                        sum((counts & Counter(original)).values()) / max(sum(counts.values()), 1), 5
                    ),
                    "paragraphs_checked": len(paragraphs),
                    "unmatched_paragraph_indexes": missing,
                    "unmatched_after_visible_bullet_prefix_removed": [
                        i
                        for i in missing
                        if compact(re.sub(r"^[•◦▪][ \t]*", "", paragraphs[i])) not in original
                    ],
                    "note": "Original unmatched indexes are retained; ignoring a displayed bullet is a separate formatting analysis, not silently changed extraction.",
                }
            else:
                item["independent_libreoffice"] = {
                    "status": "not run; prepare separate LibreOffice text export"
                }
        results.append(item)
    save(
        report_path or CACHE / "quality-audit.json",
        {
            "cases": results,
            "passed": all(c["metadata"]["passed"] for c in results),
            "scope": "character recall and grounded metadata, not visual/formula/scientific verification",
        },
    )
    for result in results:
        print(result["case"], json.dumps(result["metadata"], ensure_ascii=False), flush=True)
    assert all(c["metadata"]["passed"] for c in results), "public_author_alignment_failed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--stage", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--staging", type=Path, default=CACHE / "staging.json")
    parser.add_argument(
        "--report", type=Path, help="Audit report path; preserves other evaluation runs"
    )
    args = parser.parse_args()
    if args.stage and not args.live:
        parser.error("--stage requires explicit --live; no model call or dossier was created")
    manifest = load(MANIFEST)
    if args.fetch:
        fetch(manifest)
    if args.stage:
        stage(manifest, args.staging)
    if args.audit:
        audit(manifest, args.staging, args.report)


if __name__ == "__main__":
    main()
