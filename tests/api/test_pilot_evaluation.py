"""Offline pilot-reference checks use synthetic temp files, never models or databases."""

import json
from copy import deepcopy

import pytest

from evals.single_journal_pilot.validate import canonical_paper_id, sha256, validate_dataset


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "repository"
    dataset = root / "evaluation"
    root.mkdir()
    dataset.mkdir()
    upstream = {"papers": []}
    manifest = {
        "schema": "single-journal-pilot-preparation.v1",
        "reference_status": "engineering_draft_not_editor_validated",
        "human_evaluation_status": "not_executed",
        "upstream_manifests": {},
        "papers": [],
        "sources": [],
    }
    checkpoints = []
    license_record = {
        "id": "CC-BY-4.0",
        "evidence_url": "https://example.invalid/synthetic-license-record",
        "statement": "Synthetic unit-test fixture, not a real licensed research paper.",
    }
    for number in range(5):
        paper = {
            "id": f"synthetic-{number}",
            "source_url": f"https://example.invalid/papers/{number}",
            "license": deepcopy(license_record),
            "files": [],
        }
        identity = canonical_paper_id(paper, "documents")
        text = "\n".join(f"Synthetic fact {number}-{i}." for i in range(8))
        original = root / "originals" / f"{number}.txt"
        original.parent.mkdir(exist_ok=True)
        original.write_text(text, encoding="utf-8")
        digest = sha256(original.read_bytes())
        paper["files"].append({"case": f"case-{number}", "sha256": digest})
        upstream["papers"].append(paper)
        manifest["papers"].append(
            {
                "id": identity,
                "corpus": "documents",
                "upstream_id": paper["id"],
                "license": deepcopy(license_record),
            }
        )
        snapshot = {
            "parser": "synthetic-unit-test-parser",
            "text": text,
            "segments": [{"kind": "paragraph", "number": 1, "start": 0, "end": len(text)}],
        }
        snapshot_path = dataset / "snapshots" / f"{number}.json"
        write_json(snapshot_path, snapshot)
        source_id = f"source-{number}"
        manifest["sources"].append(
            {
                "id": source_id,
                "paper_id": identity,
                "version": "1",
                "path": original.relative_to(root).as_posix(),
                "sha256": digest,
                "snapshot": snapshot_path.relative_to(dataset).as_posix(),
                "snapshot_sha256": sha256(snapshot_path.read_bytes()),
                "text_sha256": sha256(text.encode()),
                "parser": snapshot["parser"],
                "binding": {"case": f"case-{number}"},
                "license": deepcopy(license_record),
            }
        )
        for index in range(8):
            quote = f"Synthetic fact {number}-{index}."
            start = text.index(quote)
            checkpoints.append(
                {
                    "id": f"SYNTHETIC-{number}-{index}",
                    "paper_id": identity,
                    "semantic_key": f"fact-{index}",
                    "task": "A",
                    "split": "retained_for_followup" if number == 4 else "development",
                    "question": f"What is synthetic fact {index}?",
                    "reference": {
                        "status": "engineering_draft_not_editor_validated",
                        "answerability": "answerable",
                        "result": "bounded_fact",
                    },
                    "evidence": [
                        {
                            "source_id": source_id,
                            "file_sha256": digest,
                            "version": "1",
                            "start": start,
                            "end": start + len(quote),
                            "quote": quote,
                            "locations": [
                                {
                                    "kind": "paragraph",
                                    "number": 1,
                                    "start": start,
                                    "end": start + len(quote),
                                }
                            ],
                        }
                    ],
                }
            )
    upstream_path = root / "upstream.json"
    write_json(upstream_path, upstream)
    manifest["upstream_manifests"]["documents"] = {
        "path": "upstream.json",
        "sha256": sha256(upstream_path.read_bytes()),
    }
    write_json(dataset / "manifest.json", manifest)
    write_json(dataset / "checkpoints.json", checkpoints)
    return root, dataset, manifest, checkpoints


def test_valid_reference_integrity_is_not_editor_validation(prepared):
    root, dataset, _, _ = prepared
    result = validate_dataset(dataset, root)
    assert result["passed"] is True
    assert result["counts"]["independent_papers"] == 5
    assert result["counts"]["checkpoints"] == 40
    assert result["counts"]["splits"]["retained_for_followup"] == 8
    assert result["human_evaluation_count"] == 0
    assert result["human_evaluation_status"] == "not_executed"
    assert result["validation_kind"] == "offline_engineering_reference_integrity_only"


@pytest.mark.parametrize("duplicate", ["id", "semantic_key", "question"])
def test_duplicates_cannot_increase_checkpoint_coverage(prepared, duplicate):
    root, dataset, _, points = prepared
    points[1][duplicate] = points[0][duplicate]
    write_json(dataset / "checkpoints.json", points)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert "duplicate_checkpoint" in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("quote", "Not in the original", "evidence_quote"),
        ("version", "other-version", "evidence_source_identity"),
        ("file_sha256", "f" * 64, "evidence_source_identity"),
        ("start", True, "evidence_quote"),
        ("locations", [], "evidence_location"),
    ],
)
def test_wrong_quote_version_file_or_position_refuses_validation(prepared, field, value, expected):
    root, dataset, _, points = prepared
    points[0]["evidence"][0][field] = value
    write_json(dataset / "checkpoints.json", points)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert expected in {error["code"] for error in result["errors"]}


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_actual_original_file_is_required(prepared, damage):
    root, dataset, manifest, _ = prepared
    original = root / manifest["sources"][0]["path"]
    if damage == "missing":
        original.unlink()
    else:
        original.write_bytes(b"Different original")
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    expected = "source_file_missing" if damage == "missing" else "source_file_sha256"
    assert expected in {error["code"] for error in result["errors"]}


def test_snapshot_or_license_cannot_be_substituted(prepared):
    root, dataset, manifest, _ = prepared
    manifest["sources"][0]["license"] = {"id": "unknown"}
    write_json(dataset / "manifest.json", manifest)
    snapshot = dataset / manifest["sources"][0]["snapshot"]
    value = json.loads(snapshot.read_text())
    value["text"] += "Changed parsed text"
    write_json(snapshot, value)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert {"source_license", "snapshot_sha256", "snapshot_text_sha256"} <= {
        error["code"] for error in result["errors"]
    }


def test_a_second_format_does_not_become_another_independent_paper(prepared):
    root, dataset, manifest, _ = prepared
    duplicate = deepcopy(manifest["papers"][0])
    duplicate["id"] += "-word-version"
    manifest["papers"].append(duplicate)
    write_json(dataset / "manifest.json", manifest)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert "paper_identity_or_duplicate" in {error["code"] for error in result["errors"]}


def test_revision_reference_cannot_approve_or_invent_full_reply(prepared):
    root, dataset, _, points = prepared
    points[0]["task"] = "B"
    points[0]["reference"].update(
        full_reply_available=True,
        layers={
            "author_response": {"status": "claimed"},
            "text_implementation": {"status": "located"},
            "editor_sufficiency": {"status": "approved"},
        },
    )
    write_json(dataset / "checkpoints.json", points)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert {"revision_auto_decision", "revision_reply_scope"} <= {
        error["code"] for error in result["errors"]
    }


def test_bad_schema_and_unreadable_dataset_report_failure(prepared):
    root, dataset, _, _ = prepared
    write_json(dataset / "manifest.json", [])
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert result["errors"][0]["code"] == "manifest_schema"
    (dataset / "manifest.json").unlink()
    result = validate_dataset(dataset, root)
    assert result["errors"][0]["code"] == "dataset_unreadable"


def test_version_dois_share_one_paper_identity():
    paper = {
        "versions": {
            "1": {"doi": "10.12688/f1000research.5686.1"},
            "2": {"doi": "10.12688/f1000research.5686.2"},
        }
    }
    assert canonical_paper_id(paper, "revisions") == "doi:10.12688/f1000research.5686"
    paper["versions"]["2"]["doi"] = "10.12688/f1000research.154614.2"
    with pytest.raises(ValueError, match="inconsistent_version_dois"):
        canonical_paper_id(paper, "revisions")


def test_bad_question_schema_reports_error_without_traceback(prepared):
    root, dataset, _, points = prepared
    points[0]["question"] = None
    write_json(dataset / "checkpoints.json", points)
    result = validate_dataset(dataset, root)
    assert result["passed"] is False
    assert "checkpoint_schema_or_source" in {error["code"] for error in result["errors"]}
