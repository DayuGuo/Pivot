"""Offline preparation checks. No network, database, application or model imports."""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
DATASET = Path(__file__).resolve().parent


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def child_path(root, value):
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError("path_not_relative")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path_outside_root")
    return path


def canonical_paper_id(paper, corpus):
    if corpus == "revisions":
        ids = {
            version["doi"].lower().removesuffix("." + number)
            for number, version in paper["versions"].items()
        }
        if len(ids) != 1:
            raise ValueError("inconsistent_version_dois")
        return "doi:" + ids.pop()
    url = urlparse(paper["source_url"])
    if url.hostname == "zenodo.org" and re.fullmatch(r"/records/\d+", url.path):
        return "zenodo:" + url.path.rsplit("/", 1)[-1]
    doi = parse_qs(url.query).get("id", [None])[0]
    if doi and re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.I):
        return "doi:" + unquote(doi).lower()
    return "source:" + paper["source_url"]


def paper_license(paper, corpus):
    if corpus == "documents":
        return paper["license"]
    return {
        "id": "CC-BY-4.0",
        "url": paper["license_url"],
        "evidence_url": paper["versions"]["2"]["publisher_xml_url"],
    }


def field_value(value, path):
    for key in path:
        value = value[key]
    return value


def source_binding(source, paper, corpus):
    """Return the pinned upstream file hash and, for a field source, its exact text."""
    binding = source["binding"]
    if corpus == "documents":
        file = next(file for file in paper["files"] if file["case"] == binding["case"])
        return file["sha256"], paper["license"], None
    if binding["kind"] == "manuscript":
        file = paper["versions"][source["version"]][binding["format"]]
        return file["sha256"], paper_license(paper, corpus), None
    if binding["kind"] == "response_excerpt":
        return paper["response"]["sha256"], paper_license(paper, corpus), None
    report = paper["review_requirements"][binding["index"]]
    return (
        None,
        {
            "id": "CC-BY-4.0",
            "url": report["license_url"],
            "evidence_url": report["source_url"],
            "credit": report["credit"],
        },
        report["text"],
    )


def validate_dataset(dataset=DATASET, root=ROOT):
    errors = []

    def error(code, item="dataset"):
        errors.append({"code": code, "item": item})

    try:
        manifest = read_json(dataset / "manifest.json")
        checkpoints = read_json(dataset / "checkpoints.json")
    except (OSError, ValueError, TypeError):
        return {
            "schema": "pilot-preparation-check.v1",
            "passed": False,
            "errors": [{"code": "dataset_unreadable", "item": "dataset"}],
        }
    if not isinstance(manifest, dict):
        return {
            "schema": "pilot-preparation-check.v1",
            "passed": False,
            "errors": [{"code": "manifest_schema", "item": "dataset"}],
        }

    def records(name):
        value = manifest.get(name, [])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            error("manifest_records", name)
            return []
        return value

    if manifest.get("schema") != "single-journal-pilot-preparation.v1":
        error("manifest_schema")
    if not isinstance(checkpoints, list):
        checkpoints = []
        error("checkpoint_schema")
    if manifest.get("reference_status") != "engineering_draft_not_editor_validated":
        error("reference_status")
    if manifest.get("human_evaluation_status") != "not_executed":
        error("human_evaluation_status")
    upstream = {}
    upstream_entries = manifest.get("upstream_manifests", {})
    if not isinstance(upstream_entries, dict):
        error("upstream_manifest_schema")
        upstream_entries = {}
    for name, entry in upstream_entries.items():
        try:
            path = child_path(root, entry["path"])
            raw = path.read_bytes()
            if sha256(raw) != entry["sha256"]:
                error("upstream_manifest_sha256", name)
            upstream[name] = json.loads(raw)
        except (OSError, ValueError, KeyError, TypeError):
            error("upstream_manifest_unreadable", name)
    papers = {}
    canonical_ids = set()
    for paper in records("papers"):
        identity = paper.get("id", "unknown")
        try:
            collection = "papers" if paper["corpus"] == "documents" else "cases"
            original = next(
                p for p in upstream[paper["corpus"]][collection] if p["id"] == paper["upstream_id"]
            )
            canonical = canonical_paper_id(original, paper["corpus"])
            if identity != canonical or identity in canonical_ids:
                error("paper_identity_or_duplicate", identity)
            canonical_ids.add(identity)
            if paper["license"] != paper_license(original, paper["corpus"]):
                error("paper_license", identity)
            papers[identity] = (paper, original)
        except (KeyError, TypeError, ValueError, StopIteration):
            error("paper_upstream_binding", identity)
    sources = {}
    verified_originals = set()
    for source in records("sources"):
        identity = source.get("id", "unknown")
        if not isinstance(identity, str):
            error("source_id_schema")
            continue
        if identity in sources:
            error("duplicate_source_id", identity)
            continue
        try:
            paper, original_paper = papers[source["paper_id"]]
            expected_hash, license_record, field_text = source_binding(
                source, original_paper, paper["corpus"]
            )
            if source["license"] != license_record:
                error("source_license", identity)
            original = child_path(root, source["path"])
            if not original.is_file():
                error("source_file_missing", identity)
            else:
                actual_hash = sha256(original.read_bytes())
                if actual_hash != source["sha256"] or (
                    expected_hash and expected_hash != source["sha256"]
                ):
                    error("source_file_sha256", identity)
                else:
                    verified_originals.add(source["sha256"])
            snapshot_path = child_path(dataset, source["snapshot"])
            raw_snapshot = snapshot_path.read_bytes()
            snapshot = json.loads(raw_snapshot)
            if sha256(raw_snapshot) != source["snapshot_sha256"]:
                error("snapshot_sha256", identity)
            text = snapshot["text"]
            if not isinstance(text, str) or sha256(text.encode()) != source["text_sha256"]:
                error("snapshot_text_sha256", identity)
            if snapshot["parser"] != source["parser"]:
                error("snapshot_parser", identity)
            if field_text is not None:
                # These are the selected, licensed report fields, not a whole report.
                corpus_entry = manifest["upstream_manifests"][paper["corpus"]]
                if (
                    source["path"] != corpus_entry["path"]
                    or source["sha256"] != corpus_entry["sha256"]
                    or field_text != text
                    or field_value(upstream[paper["corpus"]], source["field_path"]) != text
                ):
                    error("source_field_binding", identity)
            for segment in snapshot["segments"]:
                start, end = segment["start"], segment["end"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(text)
                ):
                    error("snapshot_segment", identity)
            sources[identity] = (source, snapshot)
        except (KeyError, TypeError, ValueError, StopIteration, OSError, IndexError):
            error("source_unreadable_or_unbound", identity)
    seen_ids, seen_keys, seen_questions = set(), set(), set()
    used_papers = set()
    splits = Counter()
    tasks = Counter()
    categories = Counter()
    for checkpoint in checkpoints:
        identity = checkpoint.get("id", "unknown") if isinstance(checkpoint, dict) else "unknown"
        try:
            if checkpoint["paper_id"] not in papers:
                error("checkpoint_paper", identity)
            key = (checkpoint["paper_id"], checkpoint["semantic_key"])
            question = (checkpoint["paper_id"], " ".join(checkpoint["question"].split()).casefold())
            if identity in seen_ids or key in seen_keys or question in seen_questions:
                error("duplicate_checkpoint", identity)
            seen_ids.add(identity)
            seen_keys.add(key)
            seen_questions.add(question)
            used_papers.add(checkpoint["paper_id"])
            splits[checkpoint["split"]] += 1
            tasks[checkpoint["task"]] += 1
            categories[checkpoint["reference"]["result"]] += 1
            if checkpoint["reference"]["result"] not in {
                "bounded_fact",
                "qualified_fact",
                "located_change",
                "missing_material",
                "partial_implementation",
                "response_claim_unverified",
                "explained_no_change",
            }:
                error("checkpoint_reference_category", identity)
            if checkpoint["task"] not in {"A", "B"} or checkpoint["split"] not in {
                "development",
                "retained_for_followup",
            }:
                error("checkpoint_task_or_split", identity)
            if checkpoint["reference"]["status"] != "engineering_draft_not_editor_validated":
                error("checkpoint_reference_status", identity)
            if checkpoint["reference"]["answerability"] not in {
                "answerable",
                "partially_answerable",
                "insufficient_material",
            }:
                error("checkpoint_answerability", identity)
            if not checkpoint["evidence"] or not checkpoint["question"].strip():
                error("checkpoint_empty", identity)
            if checkpoint["task"] == "B":
                layers = checkpoint["reference"]["layers"]
                if set(layers) != {"author_response", "text_implementation", "editor_sufficiency"}:
                    error("revision_layers", identity)
                if layers["editor_sufficiency"]["status"] != "requires_editor":
                    error("revision_auto_decision", identity)
                if checkpoint["reference"]["full_reply_available"] is not False:
                    error("revision_reply_scope", identity)
            evidence_ids = set()
            for evidence in checkpoint["evidence"]:
                source, snapshot = sources[evidence["source_id"]]
                if (
                    source["paper_id"] != checkpoint["paper_id"]
                    or evidence["file_sha256"] != source["sha256"]
                    or evidence["version"] != source["version"]
                ):
                    error("evidence_source_identity", identity)
                start, end = evidence["start"], evidence["end"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start < end <= len(snapshot["text"])
                    or snapshot["text"][start:end] != evidence["quote"]
                ):
                    error("evidence_quote", identity)
                locations = [
                    {
                        "kind": segment["kind"],
                        "number": segment["number"],
                        "start": max(start, segment["start"]),
                        "end": min(end, segment["end"]),
                    }
                    for segment in snapshot["segments"]
                    if start < segment["end"] and end > segment["start"]
                ]
                if not locations or evidence["locations"] != locations:
                    error("evidence_location", identity)
                evidence_id = (evidence["source_id"], start, end)
                if evidence_id in evidence_ids:
                    error("duplicate_evidence", identity)
                evidence_ids.add(evidence_id)
        except (AttributeError, KeyError, TypeError, ValueError):
            error("checkpoint_schema_or_source", identity)
    if len(used_papers) < 5 or len(checkpoints) < 40:
        error("minimum_independent_papers_or_checkpoints")
    if splits["retained_for_followup"] < 8:
        error("minimum_retained_followup")
    return {
        "schema": "pilot-preparation-check.v1",
        "passed": not errors,
        "validation_kind": "offline_engineering_reference_integrity_only",
        "reference_status": "engineering_draft_not_editor_validated",
        "human_evaluation_status": "not_executed",
        "human_evaluation_count": 0,
        "counts": {
            "independent_papers": len(used_papers),
            "checkpoints": len(checkpoints),
            "sources": len(sources),
            "verified_distinct_original_bytes": len(verified_originals),
            "tasks": dict(tasks),
            "splits": dict(splits),
            "reference_categories": dict(categories),
        },
        "errors": errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "summary"], nargs="?", default="validate")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result = validate_dataset(args.dataset, args.root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
