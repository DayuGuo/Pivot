"""Optional source-text metadata: old wire compatibility, exact evidence, no signing."""

import hashlib
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from apps.api.publishing.domain import document_candidates
from apps.api.publishing.domain.core import digest
from apps.api.publishing.domain.document_candidates import (
    CandidateEvidenceError,
    DocumentMetadataCandidate,
    MetadataCandidate,
    identify,
    local_candidate,
    merge_candidate,
)
from apps.api.publishing.domain.document_sources import attach_document, source_projection
from apps.api.publishing.domain.dossier_access import snapshot_digest
from apps.api.publishing.domain.dossier_evidence import EvidenceIndex, leaf_fields, source_label
from apps.api.publishing.domain.dossier_models import Dossier, DossierVersion
from apps.api.publishing.domain.dossier_schemas import DossierData, SaveInput
from apps.api.publishing.domain.models import HumanConfirmation, SubmissionWorkflow
from apps.api.publishing.models import EmailDraft, Manuscript
from evals.public_revisions.build import docx
from tests.api.test_document_candidate_quality import evidence_case
from tests.api.test_document_imports import confirm_body, endpoint, file_payload, stage
from tests.api.test_dossier_chat import completion
from tests.api.test_dossiers import create, detail, metadata, save

FUNDING = "Funding: Supported by Synthetic Foundation grant TEST-123."
DECLARATIONS = "Competing interests: The authors declare no competing interests."
TEXT = (
    "Title: Synthetic optional-metadata manuscript\nArticle type: Research article\n\n"
    + FUNDING
    + "\n\n"
    + DECLARATIONS
    + "\n\nReferences\nSynthetic reference only."
)
EXTENSION = {
    "article_type": "Research article",
    "funding_statement": FUNDING,
    "declarations_text": DECLARATIONS,
}


@pytest.mark.parametrize(
    "extension", [None, {}, {"article_type": "", "funding_statement": "", "declarations_text": ""}]
)
def test_legacy_dumps_and_action_fingerprints_do_not_gain_empty_keys(extension):
    legacy = metadata()
    value = DossierData.model_validate(legacy)
    assert value.model_dump() == legacy
    assert (
        value.model_dump_json().encode()
        == json.dumps(legacy, ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert (
        DossierData.model_validate({**legacy, "document_metadata": extension}).model_dump(
            mode="json"
        )
        == legacy
    )
    request_id = str(uuid4())
    original_body = {"request_id": request_id, "expected_revision": 1, "data": legacy, "file": None}
    changed_body = deepcopy(original_body)
    changed_body["data"]["document_metadata"] = extension
    packet = SaveInput.model_validate(changed_body).model_dump(mode="json", exclude={"request_id"})
    expected = {key: val for key, val in original_body.items() if key != "request_id"}
    assert packet == expected
    assert digest({"action": "dossier.save", "payload": packet}) == digest(
        {"action": "dossier.save", "payload": expected}
    )
    assert snapshot_digest(value.model_dump(), None, None, None) == snapshot_digest(
        legacy, None, None, None
    )


def test_nonempty_extension_is_versioned_text_and_unknown_subfields_stay_absent():
    legacy = metadata()
    value = DossierData.model_validate(
        {**legacy, "document_metadata": {"funding_statement": FUNDING}}
    )
    assert value.model_dump()["document_metadata"] == {"funding_statement": FUNDING}
    assert snapshot_digest(value.model_dump(), None, None, None) != snapshot_digest(
        legacy, None, None, None
    )
    assert DossierData.model_validate(value.model_dump()).model_dump() == value.model_dump()


@pytest.mark.parametrize("field", ["article_type", "funding_statement", "declarations_text"])
@pytest.mark.parametrize("bad", [True, False, 1, {"originality": True}, "text\x00tail"])
def test_extension_values_cannot_be_boolean_declarations_or_nul_text(field, bad):
    with pytest.raises(ValidationError):
        DossierData.model_validate({**metadata(), "document_metadata": {field: bad}})
    with pytest.raises(ValidationError):
        DocumentMetadataCandidate.model_validate({field: bad})


@pytest.mark.parametrize(
    ("field", "maximum"),
    [("article_type", 200), ("funding_statement", 4000), ("declarations_text", 8000)],
)
def test_extension_fields_are_bounded(field, maximum):
    with pytest.raises(ValidationError):
        DossierData.model_validate(
            {**metadata(), "document_metadata": {field: "a" * (maximum + 1)}}
        )
    with pytest.raises(ValidationError):
        DocumentMetadataCandidate.model_validate(
            {field: {"value": "a" * (maximum + 1), "quote": "a" * (maximum + 1)}}
        )


def test_labelled_mock_candidates_keep_actual_source_text_and_positions():
    data, sources = merge_candidate(local_candidate(TEXT), evidence_case(TEXT), metadata())
    assert data["document_metadata"] == EXTENSION
    source_by_path = {item["field_path"]: item for item in sources}
    for key, expected in EXTENSION.items():
        source = source_by_path["document_metadata." + key]
        assert source["value"] == expected
        assert TEXT[source["start"] : source["end"]] == source["quote"]
        assert source["end"] <= 14000
    assert dict(leaf_fields(data))["document_metadata.funding_statement"] == FUNDING
    assert source_label("document_metadata.declarations_text") == "声明原文（未签署）"


def test_unknown_or_outside_window_is_not_relabelled_as_no_funding():
    text = "A synthetic study introduction without explicit type, funder, or declaration."
    data, _ = merge_candidate(local_candidate(text), evidence_case(text), metadata())
    assert "document_metadata" not in data
    late = "x" * 14020 + "\n" + FUNDING + "\n\n" + DECLARATIONS
    assert local_candidate(late).document_metadata is None
    candidate = MetadataCandidate(
        document_metadata=DocumentMetadataCandidate.model_validate(
            {"funding_statement": {"value": FUNDING, "quote": FUNDING}}
        )
    )
    with pytest.raises(CandidateEvidenceError) as caught:
        merge_candidate(candidate, evidence_case(late), metadata())
    assert caught.value.reason == "metadata_outside_model_window"


def test_statement_cut_at_model_window_is_unknown_instead_of_truncated():
    text = "x" * 13900 + "\nFunding:\n" + "Funded by Synthetic Foundation. " * 20
    assert local_candidate(text).document_metadata is None


def test_type_is_not_inferred_from_methods_or_mentioned_article_category():
    text = "Methods\nWe conduct a Research article discussion, not a type declaration."
    candidate = MetadataCandidate(
        document_metadata=DocumentMetadataCandidate.model_validate(
            {"article_type": {"value": "Research article", "quote": "Research article"}}
        )
    )
    with pytest.raises(CandidateEvidenceError) as caught:
        merge_candidate(candidate, evidence_case(text), metadata())
    assert caught.value.reason == "article_type_evidence_invalid"
    assert local_candidate(text).document_metadata is None


def test_first_line_title_cannot_borrow_a_type_label_from_the_document_tail():
    title = "This is a title, not an article category"
    text = title + "\nMethods\nSynthetic study.\nArticle type:\n"
    candidate = MetadataCandidate.model_validate(
        {"document_metadata": {"article_type": {"value": title, "quote": title}}}
    )
    with pytest.raises(CandidateEvidenceError) as caught:
        merge_candidate(candidate, evidence_case(text), metadata())
    assert caught.value.reason == "article_type_evidence_invalid"


@pytest.mark.parametrize(
    ("field", "text", "fragment"),
    [
        (
            "funding_statement",
            'Introduction\nAn earlier article stated "no funding was received."\nMethods\nStudy.',
            "no funding was received.",
        ),
        (
            "declarations_text",
            "Competing interests: No competing interests except grant support from Synthetic Sponsor.",
            "No competing interests",
        ),
        (
            "funding_statement",
            "Funding: Supported by Synthetic Sponsor only for the pilot, not the full study.",
            "Supported by Synthetic Sponsor",
        ),
    ],
)
def test_statement_candidate_cannot_relabel_other_work_or_drop_qualifiers(field, text, fragment):
    candidate = MetadataCandidate.model_validate(
        {"document_metadata": {field: {"value": fragment, "quote": fragment}}}
    )
    with pytest.raises(CandidateEvidenceError) as caught:
        merge_candidate(candidate, evidence_case(text), metadata())
    assert caught.value.reason == "document_statement_evidence_invalid"


def test_unknown_new_candidate_preserves_existing_recorded_metadata_without_new_provenance():
    base = {**metadata(), "document_metadata": EXTENSION}
    data, sources = merge_candidate(
        MetadataCandidate(), evidence_case("Unknown fields remain unknown."), base
    )
    assert data["document_metadata"] == EXTENSION
    assert not any(item["field_path"].startswith("document_metadata.") for item in sources)


def test_metadata_only_fields_enter_the_existing_grounded_read_contract():
    data = DossierData.model_validate({**metadata(), "document_metadata": EXTENSION}).model_dump()
    index = EvidenceIndex(data, None, "funding")
    index.read(0, 32)
    item = next(
        value
        for value in index.issued.values()
        if value.field_path == "document_metadata.funding_statement"
    )
    cite = index.citation(
        item.source_id,
        FUNDING,
        version_id="version",
        version_no=1,
        content_digest="a" * 64,
        file_sha256=None,
    )
    assert (
        cite["kind"] == "metadata" and cite["field_path"] == "document_metadata.funding_statement"
    )
    assert cite["quote"] == FUNDING
    assert cite.get("document") is None


def test_live_protocol_metadata_evidence_only_uses_the_sent_frontmatter_and_keeps_contributions_empty(
    monkeypatch,
):
    captured = []

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def completion(self, messages, tools):
            captured.append(messages)
            parameters = tools[0]["function"]["parameters"]
            assert (
                parameters["properties"]["authors"]["items"]["properties"]["contributions"][
                    "maxItems"
                ]
                == 0
            )
            assert "document_metadata" in parameters["properties"]
            return completion(
                "propose_metadata",
                {
                    "document_metadata": {
                        key: {
                            "value": value,
                            "quote": value
                            if key != "article_type"
                            else "Article type: Research article",
                        }
                        for key, value in EXTENSION.items()
                    }
                },
            )

    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: Supplier())
    text = TEXT + "\n" + "x" * 14000 + "TAIL_NOT_SENT_TO_METADATA_MODEL"
    data, sources, provider, _, _ = identify(evidence_case(text), metadata(), lambda: None, 10**20)
    assert provider == "deepseek" and data["document_metadata"] == EXTENSION
    assert captured[0][1]["content"] == text[:14000]
    assert "TAIL_NOT_SENT_TO_METADATA_MODEL" not in captured[0][1]["content"]
    assert all(source["end"] <= 14000 for source in sources)


@pytest.mark.parametrize("candidate_field", ["funding_statement", "title", "author"])
def test_correction_never_sends_an_unseen_tail_as_verified_metadata_feedback(
    monkeypatch, candidate_field
):
    payloads = []
    tail = "Funding: UNSEEN_TAIL_MUST_NOT_ENTER_CORRECTION"

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def completion(self, messages, tools):
            payloads.append(json.dumps(messages))
            if len(payloads) == 1:
                quoted = {"value": "fabricated unsupported value", "quote": tail}
                data = (
                    {"title": quoted}
                    if candidate_field == "title"
                    else {"authors": [{"name": quoted}]}
                    if candidate_field == "author"
                    else {"document_metadata": {"funding_statement": quoted}}
                )
                return completion(
                    "propose_metadata",
                    data,
                )
            return completion("propose_metadata", {})

    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: Supplier())
    text = "Title: Synthetic safe prefix\n" + "x" * 14020 + "\n" + tail
    data, _, _, _, _ = identify(evidence_case(text), metadata(), lambda: None, 10**20)
    assert len(payloads) == 2
    assert all("UNSEEN_TAIL_MUST_NOT_ENTER_CORRECTION" not in payload for payload in payloads)
    assert "document_metadata" not in data


def test_api_import_save_material_exports_exact_new_fields_without_signed_declarations(
    client, login, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    before = {
        model: db.scalar(select(func.count()).select_from(model))
        for model in (Manuscript, SubmissionWorkflow, HumanConfirmation, EmailDraft)
    }
    initial = create(client)
    imported = stage(client, initial, "docx", file=file_payload("docx", raw=docx(TEXT.split("\n"))))
    assert imported["proposed_data"]["document_metadata"] == EXTENSION
    result = client.post(
        endpoint(initial, imported["id"], "/save-material"), json=confirm_body(initial, imported)
    )
    assert result.status_code == 200, result.text
    saved = detail(client, initial["id"], result.json()["version_id"])
    assert saved["data"]["document_metadata"] == EXTENSION and not saved["verified"]
    row = db.get(Dossier, saved["id"])
    version = db.get(DossierVersion, saved["version_id"])
    document = source_projection(db, row, version)
    index = EvidenceIndex(saved["data"], saved["file"]["text"], "funding")
    index.read(0, 32)
    field = next(
        value
        for value in index.issued.values()
        if value.field_path == "document_metadata.funding_statement"
    )
    cite = index.citation(
        field.source_id,
        FUNDING,
        version_id=version.id,
        version_no=version.version_no,
        content_digest=version.content_digest,
        file_sha256=saved["file"]["sha256"],
    )
    linked = attach_document(cite, document, db, version)
    assert linked["document"]["source_quote"] == FUNDING
    exported = client.get(
        f"/api/dossiers/{saved['id']}/versions/{saved['version_id']}/metadata-export"
    )
    assert exported.status_code == 200, exported.text
    out = exported.json()
    assert out["data"]["document_metadata"] == EXTENSION
    assert {"document_metadata." + key for key in EXTENSION} <= {
        source["field_path"] for source in out["field_sources"]
    }
    assert out["file"]["sha256"] == hashlib.sha256(saved["file"]["text"].encode()).hexdigest()
    changed = deepcopy(saved["data"])
    changed["document_metadata"]["funding_statement"] = (
        "Edited metadata supplied by the editor, not the original funding text."
    )
    current = save(client, saved, data=changed)
    revised_export = client.get(
        f"/api/dossiers/{current['id']}/versions/{current['version_id']}/metadata-export"
    ).json()
    assert "document_metadata.funding_statement" not in {
        source["field_path"] for source in revised_export["field_sources"]
    }
    old_export = client.get(
        f"/api/dossiers/{saved['id']}/versions/{saved['version_id']}/metadata-export"
    ).json()
    assert old_export["data"]["document_metadata"] == EXTENSION
    assert {model: db.scalar(select(func.count()).select_from(model)) for model in before} == before
