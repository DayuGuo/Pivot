"""Offline licensed corpus compilation, with byte hashes and exact Unicode spans."""

import hashlib
import json
from pathlib import Path

from packages.document_ingest import extract_document
from packages.text_evidence import raw_whitespace_span

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evals/public_documents/manifest.json"
GOLD = ROOT / "evals/public_documents/support_cases.json"


def corpus(all_files=False):
    manifest = json.loads(MANIFEST.read_text())
    for paper in manifest["papers"]:
        for item in paper["files"]:
            if not all_files and not item.get("bundled"):
                continue
            path = (
                ROOT / "evals/public_documents" / item["bundled"]
                if item.get("bundled")
                else ROOT / "artifacts/public-papers" / item["path"]
            )
            if not path.is_file():
                raise RuntimeError(
                    "Missing authorized original; run scripts/evaluate-public-papers.py --fetch first"
                )
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise RuntimeError("Public corpus hash mismatch")
            yield paper, item, extract_document(path.name, raw)


def support_cases(all_files=False):
    gold = json.loads(GOLD.read_text())
    for paper, item, extraction in corpus(all_files):
        text = extraction["text"]
        for case in gold["cases"]:
            if case["paper"] != paper["id"]:
                continue
            quote = case.get("quote_by_format", {}).get(item["format"], case["quote"])
            span = raw_whitespace_span(text, quote)
            if span is None:
                raise RuntimeError(f"Missing exact quote: {case['id']} / {item['case']}")
            start, end = span
            # Preserve the same surrounding text a reader would need to detect
            # negation, scope or qualifiers omitted by a short exact quote.
            context_start, context_end = max(0, start - 250), min(len(text), end + 350)
            context = text[context_start:context_end]
            raw_quote = text[start:end]
            citation = {
                "source_id": "CORPUS1",
                "kind": "text",
                "field_path": None,
                "quote": raw_quote,
                "source_text": context,
                "start": start,
                "end": end,
            }
            yield {
                "id": case["id"] + ":" + item["case"],
                "expected": case["expected"],
                "file_case": item["case"],
                "paper": paper["id"],
                "source_url": paper["source_url"],
                "original_sha256": item["sha256"],
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "quote_exact": text[start:end] == raw_quote,
                "result": {"claims": [{"text": case["claim"], "citations": [citation]}]},
            }
