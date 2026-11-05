"""Real synthetic PDF/DOCX imports, human checkpoints and version-bound source traces.

Every database write is enclosed by the API fixtures' outer rollback. Files are
private temporary CAS objects. No real model, external lookup or mail is used.
"""

import base64
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.domain import document_imports
from apps.api.publishing.domain.decision_models import EditorialDecision
from apps.api.publishing.domain.document_models import (
    DocumentApproval,
    DocumentImport,
    DocumentSource,
)
from apps.api.publishing.domain.dossier_chat_models import DossierAnswer
from apps.api.publishing.domain.dossiers import DossierCheck, DossierTurn, DossierVersion
from apps.api.publishing.domain.models import ActionReceipt, HumanConfirmation, SubmissionWorkflow
from apps.api.publishing.models import AuditEvent, EmailDraft, Manuscript, Membership, User
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_dossier_chat import completion, source
from tests.api.test_dossiers import create, detail, metadata, save

ROOT = Path(__file__).resolve().parents[2]
MARKER = "END-OF-SYNTHETIC-DOCUMENT-TRACE-2026"
TITLE = "Synthetic Editorial Review Manuscript"


def rid():
    return str(uuid4())


def count(db, model, **filters):
    return db.scalar(select(func.count()).select_from(model).filter_by(**filters))


def endpoint(snapshot, import_id=None, suffix=""):
    return (
        f"/api/dossiers/{snapshot['id']}/imports" + (f"/{import_id}" if import_id else "") + suffix
    )


def file_payload(extension="pdf", filename=None, raw=None):
    name = filename or f"synthetic-manuscript.{extension}"
    material = (
        (ROOT / "tests/documents" / f"synthetic-manuscript.{extension}").read_bytes()
        if raw is None
        else raw
    )
    return {"filename": name, "content_base64": base64.b64encode(material).decode()}


def stage_body(snapshot, extension="pdf", **changes):
    return {
        "request_id": rid(),
        "expected_revision": snapshot["revision"],
        "version_id": snapshot["version_id"],
        "file": file_payload(extension),
        "authorized_material": True,
        **changes,
    }


def get_import(client, snapshot, import_id):
    response = client.get(endpoint(snapshot, import_id))
    assert response.status_code == 200, response.text
    return response.json()


def stage(client, snapshot, extension="pdf", **changes):
    response = client.post(endpoint(snapshot), json=stage_body(snapshot, extension, **changes))
    assert response.status_code == 200, response.text
    assert response.json()["dossier_id"] == snapshot["id"]
    return get_import(client, snapshot, response.json()["import_id"])


def confirm_body(snapshot, imported, **changes):
    return {
        "request_id": rid(),
        "expected_revision": snapshot["revision"],
        "digest": imported["digest"],
        "data": deepcopy(imported["proposed_data"]),
        "acknowledged": True,
        **changes,
    }


def accept(client, snapshot, imported, **changes):
    response = client.post(
        endpoint(snapshot, imported["id"], "/confirm"),
        json=confirm_body(snapshot, imported, **changes),
    )
    assert response.status_code == 200, response.text
    return detail(client, snapshot["id"], response.json()["version_id"])


def critical_counts(db):
    return {
        model: count(db, model)
        for model in (
            Manuscript,
            SubmissionWorkflow,
            EditorialDecision,
            HumanConfirmation,
            EmailDraft,
            DossierCheck,
            DossierVersion,
            DossierTurn,
            DossierAnswer,
        )
    }


def assert_no_receipt(db, request_id):
    assert db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == request_id)) is None


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    root = tmp_path / "document-import-private-cas"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


@pytest.fixture
def ready(client, login, request):
    login(getattr(request, "param", "editor"))
    return create(client, title="等待文件核对的合成资料")


@pytest.mark.parametrize("ready", ["editor", "chief_editor"], indirect=True)
@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_file_extraction_is_pending_and_never_silently_changes_the_current_version(
    client, db, ready, extension
):
    before = critical_counts(db)
    imported = stage(client, ready, extension)
    current = detail(client, ready["id"])
    assert current["revision"] == ready["revision"]
    assert current["version_id"] == ready["version_id"]
    assert current["data"] == ready["data"] and current["file"] is None
    assert critical_counts(db) == before
    assert imported["base_revision"] == ready["revision"]
    assert imported["base_version_id"] == ready["version_id"]
    assert imported["confirmed_version_id"] is None and imported["editable"] is True
    assert imported["metadata_provider"] == "mock"
    assert MARKER in imported["text"]
    assert imported["proposed_data"]["title"] == TITLE
    assert [a["name"] for a in imported["proposed_data"]["authors"]] == [
        "Synthetic Author Alpha",
        "Synthetic Author Beta",
    ]
    assert imported["proposed_data"]["authors"][0]["email"] == "alpha@synthetic.test"
    assert imported["proposed_data"]["authors"][0]["orcid"] == "0000-0002-1825-0097"
    assert imported["proposed_data"]["authors"][0]["corresponding"] is True
    assert "Synthetic Research Institute" in imported["proposed_data"]["authors"][0]["affiliations"]
    assert len(imported["proposed_data"]["abstract"]) >= 40
    assert imported["field_sources"]
    assert any(
        item["field_path"] == "authors.0.corresponding"
        and "Synthetic Author Alpha" in item["quote"]
        for item in imported["field_sources"]
    )
    for provenance in imported["field_sources"]:
        assert imported["text"][provenance["start"] : provenance["end"]] == provenance["quote"]
        assert provenance["quote"]
    assert imported == get_import(client, ready, imported["id"])
    raw = (ROOT / "tests/documents" / f"synthetic-manuscript.{extension}").read_bytes()
    original = client.get(imported["original_download_url"])
    assert original.status_code == 200 and original.content == raw
    assert imported["sha256"] == hashlib.sha256(raw).hexdigest()
    assert original.headers["cache-control"] == "no-store"
    assert original.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in original.headers["content-disposition"]
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 1
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_explicit_human_confirmation_freezes_reviewed_values_and_creates_only_one_version(
    client, db, world, ready, extension
):
    imported = stage(client, ready, extension)
    edited = deepcopy(imported["proposed_data"])
    edited["title"] = "人工核对后的合成题名"
    edited["authors"][0]["name"] = "人工核对作者甲"
    payload = confirm_body(ready, imported, data=edited)
    before = critical_counts(db)
    response = client.post(endpoint(ready, imported["id"], "/confirm"), json=payload)
    assert response.status_code == 200, response.text
    current = detail(client, ready["id"])
    assert current["version_id"] == response.json()["version_id"]
    assert current["revision"] == ready["revision"] + 1
    assert current["version_no"] == ready["version_no"] + 1
    assert current["data"] == edited
    assert current["file"]["text"] == imported["text"]
    assert current["verified"] is True
    assert current["verification"]["by"] == world.users["editor"].id
    checked = db.scalar(
        select(DossierCheck).where(DossierCheck.version_id == current["version_id"])
    )
    assert checked.content_digest == current["content_digest"]
    assert checked.checked_by == world.users["editor"].id
    assert len(checked.session_hash) == 64
    assert current["document"]["import_id"] == imported["id"]
    assert current["document"]["sha256"] == imported["sha256"]
    assert current["document"]["segments"] == imported["segments"]
    assert current["document"]["approval"]["by"] == world.users["editor"].id
    assert count(db, DocumentSource, version_id=current["version_id"]) == 1
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 1
    assert count(db, DossierCheck) == before[DossierCheck] + 1
    for model in before:
        expected = before[model] + (1 if model in {DossierVersion, DossierCheck} else 0)
        assert count(db, model) == expected
    assert detail(client, ready["id"], ready["version_id"])["data"] == ready["data"]
    assert detail(client, ready["id"], ready["version_id"])["file"] is None
    assert (
        client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).json()
        == response.json()
    )
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 1
    altered = deepcopy(payload)
    altered["data"]["title"] = "批准后不得替换的另一题名"
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=altered).status_code == 409
    altered["request_id"] = rid()
    altered["expected_revision"] = current["revision"]
    assert (
        client.post(endpoint(current, imported["id"], "/confirm"), json=altered).status_code == 409
    )
    assert detail(client, ready["id"])["data"] == edited
    final_import = get_import(client, ready, imported["id"])
    assert final_import["confirmed_version_id"] == current["version_id"]
    assert final_import["editable"] is False


def test_authorization_and_human_acknowledgement_require_strict_explicit_boolean_true(
    client, db, ready
):
    payload = stage_body(ready)
    for value in (False, None, 0, 1, 1.0, "true", "1", [], {}):
        bad = {**payload, "authorized_material": value}
        response = client.post(endpoint(ready), json=bad)
        assert response.status_code == 422, response.text
        assert_no_receipt(db, payload["request_id"])
        assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    imported = stage(client, ready)
    payload = confirm_body(ready, imported)
    for value in (False, None, 0, 1, 1.0, "true", "1", [], {}):
        bad = {**payload, "acknowledged": value}
        response = client.post(endpoint(ready, imported["id"], "/confirm"), json=bad)
        assert response.status_code == 422, response.text
        assert_no_receipt(db, payload["request_id"])
        assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
        assert detail(client, ready["id"])["version_id"] == ready["version_id"]
    absent = deepcopy(payload)
    del absent["acknowledged"]
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=absent).status_code == 422
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code == 200


def test_different_or_stale_review_snapshot_cannot_be_confirmed(client, db, ready):
    imported = stage(client, ready)
    before = critical_counts(db)
    for overrides in ({"digest": "f" * 64}, {"expected_revision": ready["revision"] + 1}):
        payload = confirm_body(ready, imported, **overrides)
        assert (
            client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code
            == 409
        )
        assert_no_receipt(db, payload["request_id"])
    missing = deepcopy(imported["proposed_data"])
    missing["authors"] = []
    payload = confirm_body(ready, imported, data=missing)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code == 409
    assert_no_receipt(db, payload["request_id"])
    assert critical_counts(db) == before
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0


def test_a_new_editorial_save_invalidates_an_old_import_confirmation(client, db, ready):
    imported = stage(client, ready)
    current = save(client, ready, data=metadata(title="并发人工新版本"))
    payload = confirm_body(ready, imported)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code == 409
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert detail(client, ready["id"])["version_id"] == current["version_id"]
    assert get_import(client, ready, imported["id"])["editable"] is False


def test_csrf_protects_upload_and_final_human_confirmation(client, db, ready):
    token = client.headers.pop("X-CSRF-Token")
    payload = stage_body(ready)
    assert client.post(endpoint(ready), json=payload).status_code == 403
    assert_no_receipt(db, payload["request_id"])
    client.headers["X-CSRF-Token"] = token
    imported = stage(client, ready)
    client.headers.pop("X-CSRF-Token")
    payload = confirm_body(ready, imported)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code == 403
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_role_or_same_journal_staff_does_not_grant_access_to_another_editors_import(
    client, db, login, ready, role
):
    imported = stage(client, ready)
    login(role)
    assert client.get(endpoint(ready, imported["id"])).status_code == 404
    assert client.get(imported["original_download_url"]).status_code == 404
    assert (
        client.post(
            endpoint(ready, imported["id"], "/confirm"), json=confirm_body(ready, imported)
        ).status_code
        == 404
    )
    assert client.post(endpoint(ready), json=stage_body(ready)).status_code in {403, 404}
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0


@pytest.mark.parametrize("action", ["upload", "confirm"])
def test_successful_import_receipts_are_reauthorized_after_role_revocation(
    client, db, world, ready, action
):
    payload = stage_body(ready)
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 200
    imported = get_import(client, ready, response.json()["import_id"])
    path = endpoint(ready)
    if action == "confirm":
        payload = confirm_body(ready, imported)
        path = endpoint(ready, imported["id"], "/confirm")
        assert client.post(path, json=payload).status_code == 200
    db.execute(
        update(Membership)
        .where(
            Membership.user_id == world.users["editor"].id,
            Membership.journal_id == world.journal.id,
        )
        .values(role="author")
    )
    db.commit()
    assert client.post(path, json=payload).status_code in {403, 404}
    assert client.get(endpoint(ready, imported["id"])).status_code == 404
    assert client.get(imported["original_download_url"]).status_code == 404


def test_import_receipt_replay_is_exact_and_cannot_change_uploaded_bytes(client, db, ready):
    payload = stage_body(ready)
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 200
    assert client.post(endpoint(ready), json=payload).json() == response.json()
    changed = deepcopy(payload)
    changed["file"] = file_payload("docx")
    assert client.post(endpoint(ready), json=changed).status_code == 409
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 1


@pytest.mark.parametrize(
    "variant", ["pdf-corrupt", "docx-corrupt", "legacy-doc", "path", "over-limit"]
)
def test_invalid_original_cannot_leave_an_import_or_version(client, db, ready, variant):
    bad_files = {
        "pdf-corrupt": file_payload("pdf", raw=b"%PDF-1.7\nnot a valid PDF"),
        "docx-corrupt": file_payload("docx", raw=b"PK\x03\x04not a valid DOCX"),
        "legacy-doc": file_payload("pdf", filename="legacy.doc"),
        "path": file_payload("pdf", filename="../../private.pdf"),
        "over-limit": file_payload("pdf", raw=b"%PDF-1.7\n" + b"x" * (5 * 1024 * 1024)),
    }
    before = critical_counts(db)
    payload = stage_body(ready, file=bad_files[variant])
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 422, response.text
    assert critical_counts(db) == before
    assert_no_receipt(db, payload["request_id"])
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0


def test_original_filename_is_per_import_while_shared_bytes_remain_unchanged(client, ready):
    first = stage(client, ready, file=file_payload("pdf", filename="first-synthetic.pdf"))
    second = stage(client, ready, file=file_payload("pdf", filename="second-synthetic.pdf"))
    assert first["id"] != second["id"] and first["sha256"] == second["sha256"]
    one = client.get(first["original_download_url"])
    two = client.get(second["original_download_url"])
    assert one.content == two.content
    assert "first-synthetic.pdf" in one.headers["content-disposition"]
    assert "second-synthetic.pdf" in two.headers["content-disposition"]


@pytest.mark.parametrize("extension,number", [("pdf", 2), ("docx", 23)])
def test_original_source_mapping_survives_metadata_edits_and_grounded_quotes_locate_the_real_segment(
    client, db, monkeypatch, ready, extension, number
):
    from apps.api.publishing.domain import dossier_chat

    imported = stage(client, ready, extension)
    first = accept(client, ready, imported)
    changed = deepcopy(first["data"])
    changed["title"] = "人工调整题名后保持原文件定位"
    current = save(client, first, data=changed)
    assert current["document"]["import_id"] == imported["id"]
    assert current["document"]["origin_digest"] != first["document"]["origin_digest"]
    assert current["document"]["sha256"] == first["document"]["sha256"]
    assert current["document"]["approval"]["id"] == first["document"]["approval"]["id"]
    assert current["verified"] is False

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        last_telemetry = None
        last_attempt_telemetry = []
        before_attempt = None

        def __init__(self):
            self.calls = 0

        def completion(self, messages, tools):
            if tools[0]["function"]["name"] == "assess_claims":
                return completion(
                    "assess_claims",
                    {"checks": [{"index": 0, "status": "supported", "reason": "direct_support"}]},
                )
            self.calls += 1
            if self.calls == 1:
                return completion("read_dossier", {})
            selected = source(messages, contains=MARKER)
            return completion(
                "respond",
                {
                    "claims": [
                        {
                            "text": "当前版本原文件保留了完整末尾段落。",
                            "citations": [{"source_id": selected["source_id"], "quote": MARKER}],
                        }
                    ],
                    "questions": [],
                    "external_dois": [],
                },
            )

    provider = Supplier()
    monkeypatch.setattr(dossier_chat, "get_editorial_provider", lambda provider=provider: provider)
    payload = {
        "request_id": rid(),
        "expected_revision": current["revision"],
        "version_id": current["version_id"],
        "message": "定位末尾合成标记。",
    }
    response = client.post(f"/api/dossiers/{current['id']}/chat", json=payload)
    assert response.status_code == 200, response.text
    citation = response.json()["claims"][0]["citations"][0]
    assert citation["quote"] == MARKER
    assert current["file"]["text"][citation["start"] : citation["end"]] == MARKER
    original = citation["document"]
    assert original["origin_digest"] == current["document"]["origin_digest"]
    assert original["sha256"] == imported["sha256"]
    assert [location["number"] for location in original["locations"]] == [number]
    assert original["locations"][0]["kind"] == (
        "pdf_page" if extension == "pdf" else "docx_paragraph"
    )
    assert client.get(original["download_url"]).status_code == 200
    recovered = detail(client, current["id"])["messages"][-1]
    assert recovered == response.json()
    assert count(db, DocumentApproval, dossier_id=current["id"]) == 1
    assert count(db, DossierCheck, dossier_id=current["id"]) == 1

    class MetadataSupplier(Supplier):
        def completion(self, messages, tools):
            if tools[0]["function"]["name"] == "assess_claims":
                return completion(
                    "assess_claims",
                    {"checks": [{"index": 0, "status": "supported", "reason": "direct_support"}]},
                )
            self.calls += 1
            if self.calls == 1:
                return completion("read_dossier", {})
            selected = source(messages, kind="metadata", contains=changed["title"])
            return completion(
                "respond",
                {
                    "claims": [
                        {
                            "text": "当前题名由负责人修改后保存。",
                            "citations": [
                                {"source_id": selected["source_id"], "quote": changed["title"]}
                            ],
                        }
                    ],
                    "questions": [],
                    "external_dois": [],
                },
            )

    metadata_provider = MetadataSupplier()
    monkeypatch.setattr(dossier_chat, "get_editorial_provider", lambda: metadata_provider)
    payload["request_id"] = rid()
    payload["message"] = "核对当前人工修改的题名，不要冒充原文件内容。"
    response = client.post(f"/api/dossiers/{current['id']}/chat", json=payload)
    assert response.status_code == 200, response.text
    manual = response.json()["claims"][0]["citations"][0]
    assert manual["kind"] == "metadata" and manual["quote"] == changed["title"]
    assert manual.get("document") is None
    assert count(db, DossierCheck, dossier_id=current["id"]) == 1


def test_upload_a_new_plain_text_file_does_not_inherit_a_different_original_document(client, ready):
    imported = stage(client, ready)
    first = accept(client, ready, imported)
    from tests.api.test_dossiers import upload

    current = save(
        client,
        first,
        data=first["data"],
        file=upload(raw=b"Synthetic replacement text with no PDF origin."),
    )
    assert current.get("document") is None
    assert (
        detail(client, first["id"], first["version_id"])["document"]["import_id"] == imported["id"]
    )


def test_import_audits_contain_references_not_full_text_or_author_details(client, db, ready):
    imported = stage(client, ready)
    accept(client, ready, imported)
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == ready["id"])).all()
    serialized = json.dumps([event.details for event in events])
    assert imported["text"] not in serialized
    assert "alpha@synthetic.test" not in serialized
    assert "Synthetic Author Alpha" not in serialized
    assert file_payload()["content_base64"] not in serialized
    assert "PUBLISHING_STORAGE_DIR" not in serialized


def test_cross_journal_and_wrong_parent_import_ids_are_never_access_grants(
    client, db, login, world, ready
):
    imported = stage(client, ready)
    another = create(client, title="另一个独立合成资料包")
    assert client.get(endpoint(another, imported["id"])).status_code == 404
    assert client.get(endpoint(another, imported["id"], "/file")).status_code == 404
    assert (
        client.post(
            endpoint(another, imported["id"], "/confirm"), json=confirm_body(another, imported)
        ).status_code
        == 404
    )
    foreign = User(
        email=f"foreign-{rid()}@publishing.test",
        name="其他期刊合成编辑",
        password_hash=hash_password(PASSWORD),
    )
    db.add(foreign)
    db.flush()
    db.add(Membership(user_id=foreign.id, journal_id=world.other_journal.id, role="editor"))
    db.commit()
    world.users["foreign_editor"] = foreign
    login("foreign_editor")
    assert client.get(endpoint(ready, imported["id"])).status_code == 404
    assert client.get(imported["original_download_url"]).status_code == 404
    assert (
        client.post(
            endpoint(ready, imported["id"], "/confirm"), json=confirm_body(ready, imported)
        ).status_code
        == 404
    )
    assert client.post(endpoint(ready), json=stage_body(ready)).status_code == 404
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_original_bytes_are_rechecked_before_download_confirmation_and_any_model_use(
    client, db, monkeypatch, private_storage, ready, failure
):
    imported = stage(client, ready)
    stored = db.get(DocumentImport, imported["id"])
    binary_root = private_storage / "document-originals"
    target = binary_root / stored.storage_key
    assert target.resolve().is_relative_to(binary_root.resolve())
    assert target.read_bytes() == (ROOT / "tests/documents/synthetic-manuscript.pdf").read_bytes()
    if failure == "missing":
        target.unlink()
    else:
        target.write_bytes(b"%PDF-1.7\ncorrupted original CAS")
    assert client.get(imported["original_download_url"]).status_code == 409
    payload = confirm_body(ready, imported)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=payload).status_code == 409
    assert_no_receipt(db, payload["request_id"])
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert detail(client, ready["id"])["version_id"] == ready["version_id"]


def test_corrupt_approved_original_is_not_sent_to_model_or_mislabelled_as_valid_evidence(
    client, db, monkeypatch, private_storage, ready
):
    from apps.api.publishing.domain import dossier_chat

    imported = stage(client, ready)
    current = accept(client, ready, imported)
    stored = db.get(DocumentImport, imported["id"])
    (private_storage / "document-originals" / stored.storage_key).write_bytes(b"corrupt original")
    calls = []

    def unexpected_provider():
        calls.append(True)
        raise AssertionError("Original validation must precede model access")

    monkeypatch.setattr(dossier_chat, "get_editorial_provider", unexpected_provider)
    payload = {
        "request_id": rid(),
        "expected_revision": current["revision"],
        "version_id": current["version_id"],
        "message": "读取这份原始文件。",
    }
    assert client.post(f"/api/dossiers/{current['id']}/chat", json=payload).status_code == 409
    assert calls == []
    assert count(db, DossierTurn, dossier_id=current["id"]) == 0
    assert_no_receipt(db, payload["request_id"])


def test_import_approval_and_version_provenance_are_immutable_and_cannot_be_grafted_to_new_text(
    client, db, world, ready
):
    imported = stage(client, ready)
    first = accept(client, ready, imported)
    approval = db.scalar(
        select(DocumentApproval).where(DocumentApproval.import_id == imported["id"])
    )
    assert approval.reviewed_data == first["data"]
    assert approval.reviewer_id == world.users["editor"].id
    assert len(approval.digest) == 64 and approval.digest != imported["digest"]
    assert len(approval.session_hash) == 64
    tables = {
        "publishing_document_imports": ("id", imported["id"]),
        "publishing_document_approvals": ("id", approval.id),
        "publishing_document_sources": ("version_id", first["version_id"]),
    }
    for table, (key, value) in tables.items():
        for statement in (
            f"UPDATE {table} SET {key}={key} WHERE {key}=:id",
            f"DELETE FROM {table} WHERE {key}=:id",
            f"TRUNCATE {table} CASCADE",
        ):
            with pytest.raises(DBAPIError):
                with db.begin_nested():
                    db.execute(text(statement), {"id": value})
    from tests.api.test_dossiers import upload

    replacement = save(
        client,
        first,
        data=first["data"],
        file=upload(raw=b"Different complete synthetic text, without any PDF source."),
    )
    assert replacement.get("document") is None
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.add(
                DocumentSource(
                    version_id=replacement["version_id"],
                    dossier_id=first["id"],
                    journal_id=world.journal.id,
                    import_id=imported["id"],
                    approval_id=approval.id,
                    origin_digest=document_imports.origin_digest(
                        db.get(DocumentImport, imported["id"]),
                        approval,
                        db.get(DossierVersion, replacement["version_id"]),
                    ),
                )
            )
            db.flush()
    assert db.get(DocumentSource, replacement["version_id"]) is None
    assert db.get(DocumentImport, imported["id"]).sha256 == imported["sha256"]
    assert db.get(DocumentApproval, approval.id).reviewed_data == first["data"]


@pytest.mark.parametrize("change", ["role", "version"])
def test_slow_extraction_does_not_hold_a_dossier_write_lock_and_cannot_commit_stale_authority(
    client, db, world, monkeypatch, ready, change
):
    statements = []
    connection = db.get_bind()

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", observe)
    extract = document_imports.extract_document
    committed = []

    def delayed(filename, raw):
        assert not any("FOR UPDATE" in s.upper() and "publishing_dossiers" in s for s in statements)
        result = extract(filename, raw)
        if change == "role":
            db.execute(
                update(Membership)
                .where(
                    Membership.user_id == world.users["editor"].id,
                    Membership.journal_id == world.journal.id,
                )
                .values(role="author")
            )
            db.commit()
        else:
            committed.append(
                save(client, ready, data=metadata(title="解析等待期间人工保存的新版本"))
            )
        return result

    monkeypatch.setattr(document_imports, "extract_document", delayed)
    payload = stage_body(ready)
    try:
        response = client.post(endpoint(ready), json=payload)
    finally:
        event.remove(connection, "before_cursor_execute", observe)
    assert response.status_code in ({403, 404} if change == "role" else {409}), response.text
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    assert_no_receipt(db, payload["request_id"])
    if change == "version":
        assert detail(client, ready["id"])["version_id"] == committed[0]["version_id"]


@pytest.mark.parametrize("failure", ["provider", "forged-evidence", "confirmation-tool"])
def test_metadata_model_failures_and_forged_human_tools_never_create_approved_material(
    client, db, monkeypatch, ready, failure
):
    from apps.api.publishing.domain import document_candidates
    from packages.model_gateway.gateway import GatewayError

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def completion(self, messages, tools):
            if failure == "provider":
                raise GatewayError("editorial_provider_unavailable")
            if failure == "confirmation-tool":
                return completion("confirm_import", {"acknowledged": True})
            return completion(
                "propose_metadata",
                {
                    "title": {
                        "value": "伪造的未出现题名",
                        "quote": "Title: Synthetic Editorial Review Manuscript",
                    },
                    "authors": [],
                    "keywords": [],
                },
            )

    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: Supplier())
    before = critical_counts(db)
    payload = stage_body(ready)
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 503, response.text
    assert critical_counts(db) == before
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert_no_receipt(db, payload["request_id"])
    serialized = json.dumps(
        [
            e.details
            for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == ready["id"])).all()
        ]
    )
    assert (
        "alpha@synthetic.test" not in serialized
        and "Synthetic Editorial Review Manuscript" not in serialized
    )


def test_credentials_in_actual_docx_text_are_blocked_before_any_model_call(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates

    secret = "sk-" + "synthetic-private-material-" * 2
    original = (ROOT / "tests/documents/synthetic-manuscript.docx").read_bytes()
    buffer = io.BytesIO()
    with ZipFile(io.BytesIO(original)) as source_zip, ZipFile(buffer, "w") as target_zip:
        for item in source_zip.infolist():
            raw = source_zip.read(item.filename)
            if item.filename == "word/document.xml":
                raw = raw.replace(TITLE.encode(), (TITLE + " " + secret).encode())
            target_zip.writestr(item, raw)
    calls = []

    def unexpected_provider():
        calls.append(True)
        raise AssertionError("Credential screening must precede model access")

    monkeypatch.setattr(document_candidates, "get_editorial_provider", unexpected_provider)
    payload = stage_body(ready, file=file_payload("docx", raw=buffer.getvalue()))
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 422
    assert calls == [] and secret not in response.text
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    assert_no_receipt(db, payload["request_id"])
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == ready["id"])).all()
    assert secret not in json.dumps([item.details for item in events])


def test_a_corresponding_author_quote_cannot_be_misattached_to_another_person(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def completion(self, messages, tools):
            return completion(
                "propose_metadata",
                {
                    "authors": [
                        {
                            "name": {
                                "value": "Synthetic Author Beta",
                                "quote": "Author 2: Synthetic Author Beta",
                            },
                            "corresponding_quote": "Corresponding author: Synthetic Author Alpha",
                        }
                    ]
                },
            )

    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: Supplier())
    payload = stage_body(ready)
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 503
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert count(db, DossierCheck, dossier_id=ready["id"]) == 0
    assert_no_receipt(db, payload["request_id"])


def test_failed_metadata_attempt_keeps_safe_usage_without_storing_any_import(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates
    from packages.model_gateway.gateway import GatewayError, Telemetry

    private_diagnostic = "synthetic-private-provider-diagnostic"

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def completion(self, messages, tools):
            self.last_telemetry = Telemetry(
                "deepseek",
                "deepseek-flash",
                False,
                23,
                111,
                None,
                error_code="editorial_provider_unavailable",
            )
            self.last_attempt_telemetry = [self.last_telemetry]
            raise GatewayError(private_diagnostic)

    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: Supplier())
    payload = stage_body(ready)
    response = client.post(endpoint(ready), json=payload)
    assert response.status_code == 503 and private_diagnostic not in response.text
    assert count(db, DocumentImport, dossier_id=ready["id"]) == 0
    assert_no_receipt(db, payload["request_id"])
    failed = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == ready["id"],
            AuditEvent.action == "publishing.document_import_failed",
        )
    ).all()
    assert len(failed) == 1
    metrics = failed[0].details["telemetry"]
    assert len(metrics) == 1
    assert metrics[0]["input_tokens"] == 111 and metrics[0]["output_tokens"] is None
    assert metrics[0]["duration_ms"] == 23 and metrics[0]["cost_usd"] is None
    assert metrics[0]["success"] is False and metrics[0]["model"] == "deepseek-flash"
    assert private_diagnostic not in json.dumps(failed[0].details)


def test_metadata_retry_usage_is_preserved_once_per_attempt_without_double_counting(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates
    from packages.document_ingest import extract_document
    from packages.model_gateway.gateway import Telemetry

    raw = (ROOT / "tests/documents/synthetic-manuscript.pdf").read_bytes()
    extracted = extract_document("synthetic-manuscript.pdf", raw)
    valid = document_candidates.local_candidate(extracted["text"]).model_dump(mode="json")

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def __init__(self):
            self.calls = 0

        def completion(self, messages, tools):
            self.calls += 1
            self.last_telemetry = Telemetry("deepseek", "deepseek-flash", True, 23, 111, 17)
            self.last_attempt_telemetry = [self.last_telemetry]
            candidate = (
                {
                    "title": {
                        "value": "not an actual original title",
                        "quote": "Title: Synthetic Editorial Review Manuscript",
                    }
                }
                if self.calls == 1
                else valid
            )
            return completion("propose_metadata", candidate)

    supplier = Supplier()
    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: supplier)
    before = critical_counts(db)
    imported = stage(client, ready)
    assert supplier.calls == 2
    assert imported["metadata_provider"] == "deepseek"
    assert len(imported["telemetry"]) == 2
    assert sum(metric["input_tokens"] for metric in imported["telemetry"]) == 222
    assert sum(metric["output_tokens"] for metric in imported["telemetry"]) == 34
    assert all(metric["cost_usd"] is None for metric in imported["telemetry"])
    assert db.get(DocumentImport, imported["id"]).telemetry_json == imported["telemetry"]
    assert critical_counts(db) == before


def test_metadata_schema_diagnostics_never_reflect_unknown_field_names_or_values(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates
    from packages.document_ingest import extract_document

    extracted = extract_document(
        "synthetic-manuscript.pdf", (ROOT / "tests/documents/synthetic-manuscript.pdf").read_bytes()
    )
    valid = document_candidates.local_candidate(extracted["text"]).model_dump(mode="json")
    private_name = "synthetic-untrusted-private-property"
    private_value = "synthetic-untrusted-private-value"
    bad = {**valid, private_name: private_value}

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def __init__(self, correct):
            self.correct = correct
            self.calls = []

        def completion(self, messages, tools):
            self.calls.append(deepcopy(messages))
            candidate = valid if self.correct and len(self.calls) == 2 else bad
            return completion("propose_metadata", candidate)

    for correct in (True, False):
        provider = Supplier(correct)
        monkeypatch.setattr(
            document_candidates, "get_editorial_provider", lambda provider=provider: provider
        )
        payload = stage_body(ready)
        before = count(db, DocumentImport, dossier_id=ready["id"])
        response = client.post(endpoint(ready), json=payload)
        assert response.status_code == (200 if correct else 503), response.text
        assert len(provider.calls) == 2
        feedback = provider.calls[1][-1]["content"]
        assert "metadata_schema_invalid" in feedback and "unexpected_field" in feedback
        for value in (private_name, private_value):
            assert value not in json.dumps(provider.calls, ensure_ascii=False)
            assert value not in response.text
        if correct:
            imported = get_import(client, ready, response.json()["import_id"])
            assert imported["proposed_data"]["title"] == TITLE
            stored = db.get(DocumentImport, imported["id"])
            diagnostics = stored.extraction_json["metadata_diagnostics"]
            assert diagnostics == [
                {"attempt": 1, "reason": "metadata_schema_invalid", "field": "unexpected_field"}
            ]
            assert private_name not in json.dumps(imported)
            assert private_value not in json.dumps(stored.extraction_json)
        else:
            assert count(db, DocumentImport, dossier_id=ready["id"]) == before
            assert_no_receipt(db, payload["request_id"])
            failed = db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.entity_id == ready["id"],
                    AuditEvent.action == "publishing.document_import_failed",
                )
                .order_by(AuditEvent.created_at.desc())
            ).first()
            assert failed.details["diagnostics"] == [
                {"attempt": 1, "reason": "metadata_schema_invalid", "field": "unexpected_field"},
                {"attempt": 2, "reason": "metadata_schema_invalid", "field": "unexpected_field"},
            ]
            assert private_name not in json.dumps(failed.details)
            assert private_value not in json.dumps(failed.details)
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert count(db, DossierCheck, dossier_id=ready["id"]) == 0
    assert detail(client, ready["id"])["version_id"] == ready["version_id"]


def test_metadata_evidence_diagnostics_are_precise_and_correction_keeps_exact_quote_validation(
    client, db, monkeypatch, ready
):
    from apps.api.publishing.domain import document_candidates
    from packages.document_ingest import extract_document

    extracted = extract_document(
        "synthetic-manuscript.pdf", (ROOT / "tests/documents/synthetic-manuscript.pdf").read_bytes()
    )
    valid = document_candidates.local_candidate(extracted["text"]).model_dump(mode="json")
    invalid = {
        "value_not_in_quote": {
            "title": {"value": "SYNTHETIC-VALUE-NOT-IN-QUOTE", "quote": "Title: " + TITLE}
        },
        "quote_not_in_document": {
            "title": {
                "value": "SYNTHETIC-QUOTE-NOT-IN-DOCUMENT",
                "quote": "Title: SYNTHETIC-QUOTE-NOT-IN-DOCUMENT",
            }
        },
    }

    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        before_attempt = None
        last_telemetry = None
        last_attempt_telemetry = []

        def __init__(self, candidate, correct):
            self.bad = candidate
            self.correct = correct
            self.calls = []

        def completion(self, messages, tools):
            self.calls.append(deepcopy(messages))
            candidate = valid if self.correct and len(self.calls) == 2 else self.bad
            return completion("propose_metadata", candidate)

    for reason, candidate in invalid.items():
        for correct in (True, False):
            provider = Supplier(candidate, correct)
            monkeypatch.setattr(
                document_candidates, "get_editorial_provider", lambda provider=provider: provider
            )
            payload = stage_body(ready)
            before = count(db, DocumentImport, dossier_id=ready["id"])
            response = client.post(endpoint(ready), json=payload)
            assert response.status_code == (200 if correct else 503), (reason, response.text)
            assert len(provider.calls) == 2
            feedback = provider.calls[1][-1]["content"]
            assert reason in feedback and '"field": "title"' in feedback
            assert candidate["title"]["value"] not in feedback
            if correct:
                imported = get_import(client, ready, response.json()["import_id"])
                assert imported["proposed_data"]["title"] == TITLE
                stored = db.get(DocumentImport, imported["id"])
                assert stored.extraction_json["metadata_diagnostics"] == [
                    {"attempt": 1, "reason": reason, "field": "title"}
                ]
                for provenance in imported["field_sources"]:
                    assert (
                        imported["text"][provenance["start"] : provenance["end"]]
                        == provenance["quote"]
                    )
            else:
                assert count(db, DocumentImport, dossier_id=ready["id"]) == before
                assert_no_receipt(db, payload["request_id"])
                failed = db.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.entity_id == ready["id"],
                        AuditEvent.action == "publishing.document_import_failed",
                    )
                    .order_by(AuditEvent.created_at.desc())
                ).first()
                assert failed.details["diagnostics"] == [
                    {"attempt": 1, "reason": reason, "field": "title"},
                    {"attempt": 2, "reason": reason, "field": "title"},
                ]
    assert count(db, DocumentApproval, dossier_id=ready["id"]) == 0
    assert count(db, DossierCheck, dossier_id=ready["id"]) == 0
    assert detail(client, ready["id"])["version_id"] == ready["version_id"]


def test_confirmation_replay_is_bound_to_import_path_even_for_identical_candidates(
    client, db, ready
):
    first = stage(client, ready)
    second = stage(client, ready)
    assert first["id"] != second["id"] and first["digest"] == second["digest"]
    body = confirm_body(ready, first)
    response = client.post(endpoint(ready, first["id"], "/confirm"), json=body)
    assert response.status_code == 200
    before = critical_counts(db)
    wrong = client.post(endpoint(ready, second["id"], "/confirm"), json=body)
    assert wrong.status_code == 409
    assert critical_counts(db) == before
    assert (
        client.post(endpoint(ready, first["id"], "/confirm"), json=body).json() == response.json()
    )


def test_confirmation_replay_does_not_accept_a_nonexistent_import_path(client, ready):
    imported = stage(client, ready)
    body = confirm_body(ready, imported)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=body).status_code == 200
    assert client.post(endpoint(ready, rid(), "/confirm"), json=body).status_code == 404


@pytest.mark.parametrize("damaged", ["original", "extracted_text"])
def test_confirmation_replay_revalidates_original_integrity(
    client, db, ready, private_storage, damaged
):
    imported = stage(client, ready)
    body = confirm_body(ready, imported)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=body).status_code == 200
    item = db.get(DocumentImport, imported["id"])
    if damaged == "original":
        path = private_storage / "document-originals" / item.storage_key
    else:
        from apps.api.publishing.domain.models import FileObject

        version = db.scalar(
            select(DossierVersion).where(
                DossierVersion.dossier_id == ready["id"], DossierVersion.version_no == 2
            )
        )
        path = private_storage / db.get(FileObject, version.file_object_id).storage_key
    path.write_bytes(b"changed synthetic original")
    before = critical_counts(db)
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=body).status_code == 409
    assert critical_counts(db) == before


def test_confirmation_replay_preserves_legacy_fingerprint_and_does_not_revert_newer_versions(
    client, db, ready
):
    from apps.api.publishing.domain.core import digest

    imported = stage(client, ready)
    body = confirm_body(ready, imported)
    reply = client.post(endpoint(ready, imported["id"], "/confirm"), json=body)
    assert reply.status_code == 200
    receipt = db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == body["request_id"]))
    payload = document_imports.ApproveInput.model_validate(body).model_dump(
        mode="json", exclude={"request_id"}
    )
    payload["dossier_id"] = ready["id"]
    assert receipt.input_digest == digest(
        {"action": "dossier.document_approve", "payload": payload}
    )
    current = detail(client, ready["id"])
    revised = save(
        client, current, data={**current["data"], "title": "Later synthetic metadata version"}
    )
    assert revised["version_no"] == 3 and revised["verified"] is False
    replay = client.post(endpoint(ready, imported["id"], "/confirm"), json=body)
    assert replay.status_code == 200 and replay.json() == reply.json()
    assert detail(client, ready["id"])["version_id"] == revised["version_id"]


def test_unique_author_reordering_keeps_email_source_with_the_person_not_the_slot(
    client, db, ready
):
    from apps.api.publishing.domain.document_sources import attach_document
    from apps.api.publishing.domain.dossier_evidence import EvidenceIndex

    original = accept(client, ready, stage(client, ready, "docx"))
    changed = deepcopy(original["data"])
    changed["authors"].reverse()
    current = save(client, original, data=changed)
    index = EvidenceIndex(current["data"], None, "")
    index.read(count=32)
    item = next(s for s in index.issued.values() if s.field_path == "authors.0.email")
    citation = index.citation(
        item.source_id,
        "beta@synthetic.test",
        version_id=current["version_id"],
        version_no=current["version_no"],
        content_digest=current["content_digest"],
        file_sha256=None,
    )
    version = db.get(DossierVersion, current["version_id"])
    attached = attach_document(citation, current["document"], db, version)
    assert attached["document"]["source_quote"] == "Email 2: beta@synthetic.test"
    ambiguous = deepcopy(current["data"])
    ambiguous["authors"][0]["name"] = ambiguous["authors"][1]["name"]
    duplicate = save(client, current, data=ambiguous)
    citation.update(
        version_id=duplicate["version_id"],
        version_no=duplicate["version_no"],
        content_digest=duplicate["content_digest"],
    )
    assert "document" not in attach_document(
        citation, duplicate["document"], db, db.get(DossierVersion, duplicate["version_id"])
    )


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_incomplete_material_can_be_saved_for_reading_without_a_complete_metadata_check(
    client, db, ready, extension
):
    imported = stage(client, ready, extension)
    incomplete = deepcopy(imported["proposed_data"])
    incomplete.update(authors=[], abstract="", keywords=[])
    body = confirm_body(ready, imported, data=incomplete)
    before = critical_counts(db)
    path = endpoint(ready, imported["id"], "/save-material")
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    current = detail(client, ready["id"])
    assert current["data"] == incomplete
    assert current["file"]["text"] == imported["text"]
    assert current["document"]["sha256"] == imported["sha256"]
    assert current["verified"] is False and current["verification"] is None
    assert {issue["field"] for issue in current["missing"]} >= {"authors", "abstract", "keywords"}
    assert count(db, DossierCheck, version_id=current["version_id"]) == 0
    assert count(db, DocumentApproval, version_id=current["version_id"]) == 1
    assert client.post(path, json=body).json() == response.json()
    # Neither the new path nor its receipt can become the existing complete approval.
    assert client.post(endpoint(ready, imported["id"], "/confirm"), json=body).status_code == 409
    after = critical_counts(db)
    assert after.pop(DossierVersion) == before.pop(DossierVersion) + 1
    assert after == before
    result = client.post(
        f"/api/dossiers/{ready['id']}/chat",
        json={
            "request_id": rid(),
            "expected_revision": current["revision"],
            "version_id": current["version_id"],
            "message": "请根据已有正文解释研究方法",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["provider"] == "mock"
    assert result.json()["version_id"] == current["version_id"]
    assert count(db, DossierCheck, version_id=current["version_id"]) == 0


def test_material_only_save_revalidates_path_permission_csrf_and_exact_snapshot(
    client, db, world, ready
):
    imported = stage(client, ready)
    body = confirm_body(ready, imported)
    path = endpoint(ready, imported["id"], "/save-material")
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post(path, json=body).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post(path, json={**body, "digest": "0" * 64}).status_code == 409
    assert client.post(path, json=body).status_code == 200
    other = stage(client, detail(client, ready["id"]))
    assert client.post(endpoint(ready, other["id"], "/save-material"), json=body).status_code == 409
    db.execute(
        update(Membership)
        .where(
            Membership.user_id == world.users["editor"].id,
            Membership.journal_id == world.journal.id,
        )
        .values(role="author")
    )
    db.commit()
    assert client.post(path, json=body).status_code in {403, 404}
