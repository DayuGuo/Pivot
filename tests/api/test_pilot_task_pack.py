"""Synthetic pack tests; no real document parsing, network, DB or model calls."""

import json
from pathlib import Path

import pytest

from evals.single_journal_pilot import task_pack


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(task_pack.encoded(value))


@pytest.fixture
def pack_source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    dataset = root / "eval"
    dataset.mkdir(parents=True)
    sources, papers, upstream, checkpoints = [], [], [], []
    for source_id, ids in task_pack.SELECTION.items():
        fmt = "docx" if source_id == "clinical" else "pdf"
        # Deliberately not valid PDF/Word: this layer only copies validated bytes.
        original = root / "originals" / f"{source_id}.{fmt}"
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(f"synthetic {source_id} fixture".encode())
        snapshot = f"snapshots/{source_id}.json"
        write(dataset / snapshot, {"text": "synthetic parsed text"})
        source = {
            "id": source_id,
            "paper_id": source_id + "-paper",
            "path": original.relative_to(root).as_posix(),
            "sha256": task_pack.digest(original.read_bytes()),
            "snapshot": snapshot,
            "snapshot_sha256": task_pack.digest((dataset / snapshot).read_bytes()),
            "role": "manuscript",
            "version": "source-record",
            "binding": {"case": source_id + "-case"},
            "license": {"id": "synthetic-not-real-license"},
            "scope": "synthetic-only",
        }
        sources.append(source)
        papers.append(
            {
                "id": source["paper_id"],
                "title": "Synthetic fixture " + source_id,
                "corpus": "documents",
                "upstream_id": source_id,
                "credit": ["Synthetic Test Author"],
                "source_url": "https://example.invalid/" + source_id,
            }
        )
        upstream.append(
            {
                "id": source_id,
                "files": [
                    {
                        "case": source["binding"]["case"],
                        "format": fmt,
                        "kind": "author original" if fmt == "docx" else "publisher original",
                        "sha256": source["sha256"],
                    }
                ],
            }
        )
        for identity in ids:
            checkpoints.append(
                {
                    "id": identity,
                    "paper_id": source["paper_id"],
                    "task": "A",
                    "split": "development",
                    "input_materials": [source_id],
                    "question": "Synthetic question " + identity,
                    "reference": {"expected_response": "HIDDEN ENGINEERING ANSWER"},
                    "evidence": [{"quote": "HIDDEN PRESELECTED EVIDENCE"}],
                    "limitations": ["HIDDEN ENGINEERING HINT"],
                }
            )
    checkpoints.append(
        {"id": "retained", "split": "retained_for_followup", "question": "HIDDEN RETAINED QUESTION"}
    )
    write(root / "upstream.json", {"papers": upstream})
    manifest = {
        "upstream_manifests": {
            "documents": {
                "path": "upstream.json",
                "sha256": task_pack.digest((root / "upstream.json").read_bytes()),
            }
        },
        "sources": sources,
        "papers": papers,
        "prior_exposure": "Synthetic fixtures, never a blind evaluation",
    }
    write(dataset / "manifest.json", manifest)
    write(dataset / "checkpoints.json", checkpoints)
    calls = []

    def validated(actual_dataset, actual_root):
        calls.append((actual_dataset, actual_root))
        return {"passed": True}

    # Full-corpus validator has its own real-schema synthetic tests; these focus on
    # release projection and post-validation byte binding, not bypassing production.
    monkeypatch.setattr(task_pack, "validate_dataset", validated)
    return root, dataset, manifest, checkpoints, calls


def test_pack_is_deterministic_blank_and_does_not_disclose_answers(pack_source):
    root, dataset, _, _, calls = pack_source
    first = task_pack.prepare_pack(root, dataset)
    assert first == task_pack.prepare_pack(root, dataset)
    assert calls == [(dataset, root), (dataset, root)]
    all_bytes = b"\n".join(first.values())
    assert b"HIDDEN" not in all_bytes
    record = json.loads(first["editor-record.json"])
    assert record["status"] == "not_executed"
    assert record["editor_code"] is None and record["completed"] is None
    assert len(record["items"]) == 4
    assert all(item["assessment"]["text_support"] is None for item in record["items"])
    package = json.loads(first["pack.json"])
    assert package["human_evaluations"] == 0
    assert package["task_B_included"] is False
    assert set(package["files"]) == set(first) - {"pack.json", "pack.sha256"}
    assert all(task_pack.digest(first[name]) == digest for name, digest in package["files"].items())
    materials = json.loads(first["materials.json"])
    assert {m["format"] for m in materials} == {"pdf", "docx"}
    assert all(m["credit"] and m["license"] and m["source_url"] for m in materials)


def test_failed_real_corpus_gate_prevents_output(pack_source, monkeypatch):
    root, dataset, *_ = pack_source
    monkeypatch.setattr(task_pack, "validate_dataset", lambda *_: {"passed": False})
    output = root / "artifacts" / "pack"
    with pytest.raises(ValueError, match="corpus_validation_failed"):
        task_pack.build_pack(output, root, dataset)
    assert not output.exists()


def test_missing_original_fails_before_validator_or_output(pack_source):
    root, dataset, manifest, _, calls = pack_source
    (root / manifest["sources"][0]["path"]).unlink()
    with pytest.raises(ValueError, match="material_missing"):
        task_pack.prepare_pack(root, dataset)
    assert calls == []


def test_source_byte_tampering_fails(pack_source):
    root, dataset, manifest, *_ = pack_source
    (root / manifest["sources"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="material_digest_changed"):
        task_pack.prepare_pack(root, dataset)


def test_existing_human_annotations_are_never_overwritten(pack_source):
    root, dataset, *_ = pack_source
    output = root / "artifacts" / "pack"
    task_pack.build_pack(output, root, dataset)
    (output / "editor-record.json").write_text("human annotations")
    with pytest.raises(ValueError, match="output_exists"):
        task_pack.build_pack(output, root, dataset)
    assert (output / "editor-record.json").read_text() == "human annotations"


def test_sources_and_destination_must_not_follow_symlinks(pack_source, tmp_path):
    root, dataset, manifest, *_ = pack_source
    original = root / manifest["sources"][0]["path"]
    outside = tmp_path / "outside"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink_not_allowed"):
        task_pack.prepare_pack(root, dataset)
    (root / "artifacts").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink_not_allowed"):
        task_pack.build_pack(root / "artifacts" / "new-pack", root, dataset)


@pytest.mark.parametrize("change", ["retained", "other_paper", "other_source", "task_B"])
def test_selected_question_binding_cannot_drift(pack_source, change):
    root, dataset, _, checkpoints, _ = pack_source
    item = checkpoints[0]
    if change == "retained":
        item["split"] = "retained_for_followup"
    elif change == "other_paper":
        item["paper_id"] = "another-paper"
    elif change == "other_source":
        item["input_materials"] = ["wrong-source"]
    else:
        item["task"] = "B"
    write(dataset / "checkpoints.json", checkpoints)
    with pytest.raises(ValueError, match="development_task_binding_required"):
        task_pack.prepare_pack(root, dataset)


def test_derivative_word_cannot_be_presented_as_author_original(pack_source):
    root, dataset, manifest, *_ = pack_source
    upstream = json.loads((root / "upstream.json").read_text())
    upstream["papers"][0]["files"][0]["kind"] = "text-only derivative"
    write(root / "upstream.json", upstream)
    manifest["upstream_manifests"]["documents"]["sha256"] = task_pack.digest(
        (root / "upstream.json").read_bytes()
    )
    write(dataset / "manifest.json", manifest)
    with pytest.raises(ValueError, match="original_format_binding_required"):
        task_pack.prepare_pack(root, dataset)


def test_output_outside_artifacts_refused(pack_source, tmp_path):
    root, dataset, *_ = pack_source
    with pytest.raises(ValueError):
        task_pack.build_pack(tmp_path / "outside", root, dataset)
    with pytest.raises(ValueError, match="dedicated_output_directory_required"):
        task_pack.build_pack(root / "artifacts", root, dataset)


def test_traversal_path_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe_material_path"):
        task_pack.safe_path(tmp_path, Path("../outside"))
