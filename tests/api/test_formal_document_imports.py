import base64
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.formal_document_models import FormalDocumentBinding
from apps.api.publishing.domain.models import SubmissionWorkflow, VersionFile
from tests.api.test_publishing_intake import draft

FILES = Path(__file__).resolve().parents[1] / "documents"


def prepare(client, mid, extension="pdf", **extra):
    detail = client.get(f"/api/publishing/manuscripts/{mid}").json()
    body = {
        "request_id": str(uuid4()),
        "expected_revision": detail["revision"],
        "version_id": detail["version"]["id"],
        "purpose": "manuscript",
        "filename": "synthetic-manuscript." + extension,
        "content_base64": base64.b64encode(
            (FILES / f"synthetic-manuscript.{extension}").read_bytes()
        ).decode(),
        "authorized_material": True,
        "source_kind": "synthetic",
        "source_note": "全部为合成公开接口测试，无保密资料。",
        **extra,
    }
    response = client.post(f"/api/publishing/manuscripts/{mid}/document-imports", json=body)
    assert response.status_code == 200, response.text
    iid = response.json()["import_id"]
    imported = client.get(f"/api/publishing/manuscripts/{mid}/document-imports/{iid}").json()
    return imported, body


def confirm(client, mid, imported, **extra):
    return client.post(
        f"/api/publishing/manuscripts/{mid}/document-imports/{imported['id']}/confirmations",
        json={
            "request_id": str(uuid4()),
            "expected_revision": imported["base_revision"],
            "digest": imported["digest"],
            "first_segment": 1,
            "last_segment": len(imported["segments"]),
            "acknowledged_original": True,
            "acknowledged_text": True,
            "acknowledged_scope": True,
            **extra,
        },
    )


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_prepare_is_not_file_then_owner_confirms_exact_text_and_origin(
    client, login, db, monkeypatch, tmp_path, extension
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    before = client.get(f"/api/publishing/manuscripts/{mid}").json()
    imported, _ = prepare(client, mid, extension)
    assert client.get(f"/api/publishing/manuscripts/{mid}").json() == before
    out = confirm(client, mid, imported)
    assert out.status_code == 200, out.text
    binding = db.scalar(
        select(FormalDocumentBinding).where(FormalDocumentBinding.file_id == out.json()["file_id"])
    )
    assert binding.confirmed_by and binding.kind == "confirmed"
    assert (
        client.get(f"/api/publishing/files/{binding.file_id}").content.decode() == imported["text"]
    )
    assert (
        client.get(f"/api/publishing/files/{binding.file_id}/original").content
        == (FILES / f"synthetic-manuscript.{extension}").read_bytes()
    )
    assert (
        db.scalar(select(SubmissionWorkflow.stage).where(SubmissionWorkflow.manuscript_id == mid))
        == "author_draft"
    )
    login("editor")
    assert client.get(f"/api/publishing/files/{binding.file_id}/original").status_code == 404


def test_stale_import_and_nonexplicit_ack_do_not_bind_file(
    client, login, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(client, mid)
    assert confirm(client, mid, imported, acknowledged_scope=1).status_code == 422
    assert confirm(client, mid, imported, first_segment=2, last_segment=1).status_code == 422
    assert (
        db.scalar(
            select(func.count()).select_from(VersionFile).where(VersionFile.manuscript_id == mid)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(FormalDocumentBinding)
            .where(FormalDocumentBinding.manuscript_id == mid)
        )
        == 0
    )


def test_import_source_is_inherited_but_not_new_human_confirmation(
    client, login, db, world, monkeypatch, tmp_path
):
    from tests.api import test_publishing_screening as screening
    from tests.api.test_publishing_decisions import closed_round, decide, recommend

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    old_fill = screening.fill

    def fill_with_document(client, created):
        current = old_fill(client, created)
        imported, _ = prepare(client, current["id"])
        response = confirm(client, current["id"], imported)
        assert response.status_code == 200, response.text
        return client.get(f"/api/publishing/manuscripts/{current['id']}").json()

    monkeypatch.setattr(screening, "fill", fill_with_document)
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    decide(client, login, mid)
    bindings = db.scalars(
        select(FormalDocumentBinding).where(FormalDocumentBinding.manuscript_id == mid)
    ).all()
    root = next(b for b in bindings if b.kind == "confirmed")
    child = next(b for b in bindings if b.kind == "inherited")
    assert child.parent_id == root.id and child.confirmed_by is None and child.session_hash is None
    assert child.version_id != root.version_id and child.file_object_id == root.file_object_id
    login("editor")
    assert client.get(f"/api/publishing/files/{child.file_id}/original").status_code == 404
    login("author")
    assert client.get(f"/api/publishing/files/{child.file_id}/original").status_code == 200


def test_replacement_preserves_immutable_confirmation_and_no_accidental_origin(
    client, login, db, monkeypatch, tmp_path
):
    from tests.api.test_publishing_intake import request_id

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(client, mid)
    r = confirm(client, mid, imported)
    assert r.status_code == 200, r.text
    old_id = r.json()["file_id"]
    current = client.get(f"/api/publishing/manuscripts/{mid}").json()
    replaced = client.post(
        f"/api/publishing/manuscripts/{mid}/files",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "file": {
                "filename": "replacement.txt",
                "content_base64": base64.b64encode(b"Different synthetic text.").decode(),
                "purpose": "manuscript",
            },
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert (
        db.scalar(select(FormalDocumentBinding).where(FormalDocumentBinding.file_id == old_id))
        is not None
    )
    assert client.get(f"/api/publishing/files/{old_id}/original").status_code == 404
    assert (
        client.get(f"/api/publishing/files/{replaced.json()['file_id']}/original").status_code
        == 404
    )


def test_selected_word_paragraphs_are_exact_and_do_not_include_appendix(
    client, login, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(client, mid, "docx")
    out = confirm(client, mid, imported, first_segment=2, last_segment=3)
    assert out.status_code == 200, out.text
    restored = client.get(
        f"/api/publishing/manuscripts/{mid}/document-imports/{imported['id']}"
    ).json()
    assert restored["confirmed_range"] == {"first_segment": 2, "last_segment": 3}
    expected = imported["text"][imported["segments"][1]["start"] : imported["segments"][2]["end"]]
    assert client.get(f"/api/publishing/files/{out.json()['file_id']}").content.decode() == expected
    from apps.api.publishing.domain.formal_document_sources import origin_for
    from packages.document_ingest.locations import original_location

    link = db.get(VersionFile, out.json()["file_id"])
    origin = origin_for(db, link)
    quote = expected[:20]
    location = original_location(origin, 0, len(quote), quote)
    assert location["locations"][0]["number"] == 2
    assert location["locations"][0]["quote"] == quote


def test_unconfirmed_or_corrupt_original_cannot_be_replayed_as_success(
    client, login, db, monkeypatch, tmp_path
):
    from apps.api.publishing.domain import formal_document_sources

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(client, mid)

    def corrupt(_):
        raise formal_document_sources.FileValidationError("synthetic_corruption")

    monkeypatch.setattr(formal_document_sources, "read_original", corrupt)
    assert confirm(client, mid, imported).status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(FormalDocumentBinding)
            .where(FormalDocumentBinding.manuscript_id == mid)
        )
        == 0
    )


def test_non_bmp_text_scope_uses_unicode_code_points_in_sql_and_original_mapping(
    client, login, db, monkeypatch, tmp_path
):
    from apps.api.publishing.domain.formal_document_sources import origin_for
    from packages.document_ingest.locations import original_location

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(
        client,
        mid,
        "docx",
        content_base64=base64.b64encode((FILES / "synthetic-unicode.docx").read_bytes()).decode(),
    )
    out = confirm(client, mid, imported, first_segment=2, last_segment=2)
    assert out.status_code == 200, out.text
    expected = "第二段：𝛽 和 😀 均须完整保留。"
    assert client.get(f"/api/publishing/files/{out.json()['file_id']}").content.decode() == expected
    origin = origin_for(db, db.get(VersionFile, out.json()["file_id"]))
    located = original_location(origin, 0, len(expected), expected)
    assert located["locations"][0]["number"] == 2 and located["locations"][0]["quote"] == expected


def test_pending_pagination_is_scoped_replay_is_exact_and_stale_import_is_conflict(
    client, login, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    first, original_body = prepare(client, mid)
    repeated = client.post(
        f"/api/publishing/manuscripts/{mid}/document-imports", json=original_body
    )
    assert repeated.status_code == 200 and repeated.json()["import_id"] == first["id"]
    second, _ = prepare(client, mid, "docx")
    url = f"/api/publishing/manuscripts/{mid}/document-imports"
    page = client.get(url, params={"limit": 1}).json()
    assert page["next_cursor"] and len(page["items"]) == 1
    rest = client.get(url, params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert {page["items"][0]["id"], rest["items"][0]["id"]} == {first["id"], second["id"]}
    other = draft(client)["manuscript_id"]
    assert (
        client.get(
            f"/api/publishing/manuscripts/{other}/document-imports",
            params={"cursor": page["next_cursor"]},
        ).status_code
        == 422
    )
    assert client.get(url, params={"limit": 21}).status_code == 422
    assert confirm(client, mid, first).status_code == 200
    # Sending the new workflow revision must not rebase an old extraction snapshot.
    assert confirm(client, mid, second, expected_revision=1).status_code == 409
    assert confirm(client, mid, second).status_code == 409
    pending = client.get(url).json()["items"]
    assert len(pending) == 1 and pending[0]["id"] == second["id"] and not pending[0]["editable"]
    login("editor")
    assert client.get(url).status_code in {403, 404}


def test_confirmation_lost_response_replay_and_sql_immutability(
    client, login, db, monkeypatch, tmp_path
):
    from sqlalchemy import delete, update
    from sqlalchemy.exc import DBAPIError

    from apps.api.publishing.domain.formal_document_models import FormalDocumentImport

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("author")
    mid = draft(client)["manuscript_id"]
    imported, _ = prepare(client, mid)
    request = str(uuid4())
    one = confirm(client, mid, imported, request_id=request)
    two = confirm(client, mid, imported, request_id=request)
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    assert (
        confirm(client, mid, imported, request_id=request, expected_revision=1).status_code == 409
    )
    assert client.get(f"/api/publishing/manuscripts/{mid}").json()["revision"] == 1
    for statement in [
        update(FormalDocumentImport)
        .where(FormalDocumentImport.id == imported["id"])
        .values(source_note="篡改批准材料来源"),
        delete(FormalDocumentImport).where(FormalDocumentImport.id == imported["id"]),
        update(FormalDocumentBinding)
        .where(FormalDocumentBinding.import_id == imported["id"])
        .values(selection_start=1),
        delete(FormalDocumentBinding).where(FormalDocumentBinding.import_id == imported["id"]),
    ]:
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(statement)
