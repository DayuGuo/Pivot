"""Independent evaluation export is private, source-bound and free of labels/writes."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.claim_evaluation_package import (
    InvalidEvaluationSource,
    citation_projection,
    package_projection,
)
from apps.api.publishing.domain.claim_review_models import ClaimReview
from apps.api.publishing.domain.dossier_chat_models import DossierAnswer
from apps.api.publishing.domain.models import ActionReceipt
from apps.api.publishing.models import AuditEvent
from tests.api.test_claim_reviews import payload, target
from tests.api.test_dossier_chat import BODY, body, path
from tests.api.test_dossiers import create, metadata, save, upload


@pytest.fixture
def reviewed_answer(client, login, monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    item = save(client, create(client), data=metadata(), file=upload(raw=BODY.encode()))
    response = client.post(path(item), json=body(item))
    assert response.status_code == 200, response.text
    return item, response.json()


def endpoint(item, answer):
    return f"/api/dossiers/{item['id']}/answers/{answer['id']}/evaluation-package"


def test_export_is_label_hidden_exact_and_does_not_write(client, db, reviewed_answer):
    item, answer = reviewed_answer
    original = db.get(DossierAnswer, answer["id"])
    frozen = deepcopy(original.result_json)
    url = target(item, answer)
    assert client.post(url, json=payload(client.get(url).json())).status_code == 200
    before = client.get(f"/api/dossiers/{item['id']}").json()
    counts = {
        m: db.scalar(select(func.count()).select_from(m))
        for m in (AuditEvent, ActionReceipt, ClaimReview)
    }
    response = client.get(endpoint(item, answer))
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="pivot-evaluation-'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    out = response.json()
    assert out["schema"] == "claim-evaluation-package.v1"
    assert out["source"]["text"] == item["file"]["text"]
    assert out["source"]["data"] == item["data"]
    assert out["source"]["content_digest"] == item["content_digest"]
    import hashlib

    from apps.api.publishing.domain.dossier_access import snapshot_digest

    source = out["source"]
    assert hashlib.sha256(source["text"].encode()).hexdigest() == source["file_sha256"]
    assert (
        snapshot_digest(
            source["data"], source["file_sha256"], source["file_name"], source["file_media_type"]
        )
        == source["content_digest"]
    )
    assert out["source"]["version_id"] == answer["version_id"]
    assert len(out["claims"]) == len(frozen["claims"]) + len(frozen.get("withheld_claims", []))
    assert {c["text"] for c in out["claims"]} == {c["text"] for c in frozen["claims"]}
    assert all(c["assessment"] == {"verdict": None, "note": ""} for c in out["claims"])
    assert all(set(c) == {"id", "text", "citations", "assessment"} for c in out["claims"])
    assert all(
        "support" not in c and "source_id" not in cit and "document" not in cit
        for c in out["claims"]
        for cit in c["citations"]
    )
    assert "provider" not in out and "metrics" not in out and "reviews" not in out
    assert client.get(f"/api/dossiers/{item['id']}").json() == before
    assert db.get(DossierAnswer, answer["id"]).result_json == frozen
    assert counts == {m: db.scalar(select(func.count()).select_from(m)) for m in counts}
    again = client.get(endpoint(item, answer)).json()
    assert again["package_id"] != out["package_id"]
    assert {c["id"] for c in again["claims"]}.isdisjoint(c["id"] for c in out["claims"])


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_other_identity_cannot_export(client, login, reviewed_answer, role):
    item, answer = reviewed_answer
    login(role)
    assert client.get(endpoint(item, answer)).status_code == 404


def test_unknown_or_cross_dossier_answer_cannot_export(client, reviewed_answer):
    item, answer = reviewed_answer
    assert client.get(endpoint(create(client), answer)).status_code == 404
    assert client.get(endpoint(item, {"id": str(uuid4())})).status_code == 404


def test_export_keeps_historical_version_after_edit(client, reviewed_answer):
    item, answer = reviewed_answer
    changed = metadata()
    changed["title"] = "Another current version"
    updated = save(client, item, data=changed)
    out = client.get(endpoint(item, answer)).json()
    assert updated["version_id"] != out["source"]["version_id"] == item["version_id"]
    assert out["source"]["data"]["title"] == item["data"]["title"]


def test_metadata_only_answer_cannot_export_as_fulltext_evaluation(client, login):
    login()
    item = save(client, create(client), data=metadata())
    response = client.post(path(item), json=body(item))
    assert response.status_code == 200
    assert client.get(endpoint(item, response.json())).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"start": True},
        {"end": 1000},
        {"end": 1},
        {"quote": "wrong text"},
        {"version_id": str(uuid4())},
        {"content_digest": "f" * 64},
        {"file_sha256": "e" * 64},
        {"kind": "url"},
        {"field_path": "authors.0.name"},
    ],
)
def test_invalid_coordinates_and_source_identity_refused(changes):
    version = {"version_id": "version", "version_no": 1, "content_digest": "a" * 64, "data": {}}
    cite = {
        **version,
        "kind": "text",
        "field_path": None,
        "start": 0,
        "end": 4,
        "quote": "🙂研究\n",
        "file_sha256": "b" * 64,
    }
    cite.update(changes)
    with pytest.raises(InvalidEvaluationSource):
        citation_projection(cite, version=version, text="🙂研究\n下一行", file_sha256="b" * 64)


def test_unicode_and_boolean_metadata_use_codepoint_offsets():
    version = {
        "version_id": "v",
        "version_no": 1,
        "content_digest": "c" * 64,
        "data": {"authors": [{"corresponding": True}]},
    }
    cite = {
        **version,
        "kind": "text",
        "field_path": None,
        "start": 1,
        "end": 3,
        "quote": "研究",
        "file_sha256": "d" * 64,
    }
    result = citation_projection(cite, version=version, text="🙂研究\n下一行", file_sha256="d" * 64)
    assert result["quote"] == "研究" and result["start"] == 1 and result["end"] == 3
    result = citation_projection(
        {
            **cite,
            "kind": "metadata",
            "field_path": "authors.0.corresponding",
            "start": 0,
            "end": 4,
            "quote": "true",
        },
        version=version,
        text=None,
        file_sha256=None,
    )
    assert result["quote"] == "true"


def test_projection_copies_only_allowed_claim_fields():
    claims = [
        {
            "text": "An independent candidate",
            "citations": [],
            "support": {"status": "supported"},
            "claim_bucket": "claims",
            "reviewer_note": "private",
        }
    ]
    frozen = deepcopy(claims)
    out = package_projection({"text": "source"}, claims)
    assert set(out["claims"][0]) == {"id", "text", "citations", "assessment"}
    assert claims == frozen


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_original_import_citations_are_relocated_and_protected(
    client, db, login, monkeypatch, tmp_path, extension
):
    from tests.api.test_document_imports import accept, critical_counts, stage

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    item = create(client)
    imported = stage(client, item, extension)
    current = accept(client, item, imported)
    answer = client.post(path(current), json=body(current))
    assert answer.status_code == 200, answer.text
    before = critical_counts(db)
    out = client.get(endpoint(current, answer.json()))
    assert out.status_code == 200, out.text
    package = out.json()
    assert package["source"]["document"]["sha256"] == imported["sha256"]
    assert package["source"]["document"]["segments"] == current["document"]["segments"]
    assert any(c.get("document") for claim in package["claims"] for c in claim["citations"])
    for claim in package["claims"]:
        for cite in claim["citations"]:
            if "document" in cite:
                doc = cite["document"]
                assert (
                    package["source"]["text"][doc["source_start"] : doc["source_end"]]
                    == doc["source_quote"]
                )
                assert doc["locations"]
    raw = client.get(package["source"]["document"]["download_url"])
    assert raw.status_code == 200
    assert critical_counts(db) == before


@pytest.mark.parametrize("failure", ["quote", "document", "claim_shape"])
def test_archived_bad_citation_refuses_export_without_partial_success(
    client, reviewed_answer, monkeypatch, failure
):
    from types import SimpleNamespace

    from apps.api.publishing.domain import claim_evaluation

    item, answer = reviewed_answer
    real = claim_evaluation.answer_source

    def bad(*args):
        row, version, saved = real(*args)
        data = deepcopy(saved.result_json)
        if failure == "quote":
            data["claims"][0]["citations"][0]["quote"] = "not in the frozen source"
        elif failure == "document":
            data["claims"][0]["citations"][0]["document"] = {"sha256": "0" * 64}
        else:
            data["claims"][0]["citations"] = None
        return row, version, SimpleNamespace(result_json=data)

    monkeypatch.setattr(claim_evaluation, "answer_source", bad)
    response = client.get(endpoint(item, answer))
    assert response.status_code == 409, response.text
    assert "source" not in response.json()
    assert "not in the frozen source" not in response.text


def test_source_corruption_and_expired_session_block_download(client, reviewed_answer, monkeypatch):
    from fastapi import HTTPException

    from apps.api.publishing.domain import dossier_access

    item, answer = reviewed_answer

    def corrupt(*args):
        raise HTTPException(409, "synthetic corrupt source")

    monkeypatch.setattr(dossier_access, "file_content", corrupt)
    assert client.get(endpoint(item, answer)).status_code == 409
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get(endpoint(item, answer)).status_code == 401


def test_withheld_candidates_are_mixed_without_private_labels(client, reviewed_answer, monkeypatch):
    from types import SimpleNamespace

    from apps.api.publishing.domain import claim_evaluation

    item, answer = reviewed_answer
    original_source = claim_evaluation.answer_source
    marker = "PRIVATE_AI_OR_HUMAN_LABEL_DO_NOT_EXPORT"

    def mixed(*args):
        row, version, saved = original_source(*args)
        data = deepcopy(saved.result_json)
        candidate = deepcopy(data["claims"][0])
        candidate["text"] = "Additional independently assessed candidate"
        candidate["support"] = {"status": "contradicted", "reason": marker}
        candidate["reviewer_note"] = marker
        candidate["citations"][0]["label"] = marker
        candidate["citations"][0]["support"] = marker
        data["withheld_claims"] = [candidate]
        data["telemetry"] = {"private": marker}
        return row, version, SimpleNamespace(result_json=data)

    monkeypatch.setattr(claim_evaluation, "answer_source", mixed)
    response = client.get(endpoint(item, answer))
    assert response.status_code == 200, response.text
    assert marker not in response.text
    assert len(response.json()["claims"]) == len(answer["claims"]) + 1
    assert any(
        c["text"] == "Additional independently assessed candidate"
        for c in response.json()["claims"]
    )
