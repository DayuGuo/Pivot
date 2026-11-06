"""Exact-version metadata exports retain gaps, provenance and current private access."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain import dossier_export
from apps.api.publishing.domain.document_models import DocumentImport
from apps.api.publishing.domain.dossier_models import DossierCheck, DossierVersion
from apps.api.publishing.domain.models import ActionReceipt
from apps.api.publishing.models import AuditEvent, Membership, User
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_document_imports import accept, stage
from tests.api.test_dossiers import confirm, create, detail, metadata, save, upload


def endpoint(item, version_id=None):
    return f"/api/dossiers/{item['id']}/versions/{version_id or item['version_id']}/metadata-export"


@pytest.fixture(autouse=True)
def private_export_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def ready(client, login):
    login()
    return save(client, create(client), file=upload())


def test_export_is_exact_private_and_does_not_write(client, db, ready, world):
    assert confirm(client, ready).status_code == 200
    current = detail(client, ready["id"])
    models = (AuditEvent, ActionReceipt, DossierCheck, DossierVersion)
    before = {model: db.scalar(select(func.count()).select_from(model)) for model in models}
    response = client.get(endpoint(ready))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="pivot-metadata-{ready["version_id"]}.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    out = response.json()
    assert out["schema"] == "dossier-metadata-export.v1"
    assert out["data"] == ready["data"]
    assert out["dossier_id"] == ready["id"]
    assert out["version_id"] == ready["version_id"]
    assert out["content_digest"] == ready["content_digest"]
    assert out["version_no"] == ready["version_no"]
    assert out["is_current"] is True and out["verified"] is True
    assert out["verification"] == current["verification"]
    assert out["verification"]["by"] == world.users["editor"].id
    assert out["missing"] == [] and out["author_issues"] == []
    assert out["file"] == {key: value for key, value in ready["file"].items() if key != "text"}
    assert out["document"] is None and out["field_sources"] == []
    assert set(out) == {
        "schema",
        "dossier_id",
        "version_id",
        "version_no",
        "content_digest",
        "is_current",
        "data",
        "missing",
        "author_issues",
        "verified",
        "verification",
        "file",
        "document",
        "field_sources",
    }
    assert before == {model: db.scalar(select(func.count()).select_from(model)) for model in models}


def test_incomplete_metadata_and_absent_file_remain_exportable(client, login):
    login()
    initial = create(client)
    empty = client.get(endpoint(initial))
    assert empty.status_code == 200, empty.text
    assert empty.json()["file"] is None
    assert {item["field"] for item in empty.json()["missing"]} >= {"authors", "file"}
    saved = save(client, initial, data=deepcopy(initial["data"]), file=upload())
    response = client.get(endpoint(saved))
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["data"]["authors"] == []
    assert out["data"]["abstract"] == ""
    assert "authors" in {item["field"] for item in out["missing"]}
    assert "file" not in {item["field"] for item in out["missing"]}
    assert out["verified"] is False and out["verification"] is None


def test_old_export_stays_bound_to_old_metadata_and_check(client, ready):
    assert confirm(client, ready).status_code == 200
    old = detail(client, ready["id"])
    changed = metadata(title="A different current manuscript version")
    updated = save(client, old, data=changed, file=upload(raw=b"new file text"))
    out = client.get(endpoint(old)).json()
    assert out["is_current"] is False
    assert out["version_id"] == old["version_id"] != updated["version_id"]
    assert out["data"] == old["data"]
    assert out["verification"] == old["verification"]
    assert out["file"]["sha256"] == old["file"]["sha256"] != updated["file"]["sha256"]


@pytest.mark.parametrize("role", ["chief_editor", "author", "reviewer"])
def test_other_identity_cannot_export(client, login, ready, role):
    login(role)
    assert client.get(endpoint(ready)).status_code == 404


def test_same_journal_peer_editor_cannot_export(client, login, db, world, ready):
    peer = User(
        email=f"metadata-peer-{uuid4().hex}@publishing.test",
        name="Same-journal synthetic editor",
        password_hash=hash_password(PASSWORD),
    )
    db.add(peer)
    db.flush()
    db.add(Membership(user_id=peer.id, journal_id=world.journal.id, role="editor"))
    db.commit()
    world.users["peer"] = peer
    login("peer")
    assert client.get(endpoint(ready)).status_code == 404


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_owner_losing_staff_role_cannot_export(client, db, world, ready, role):
    db.execute(
        update(Membership).where(Membership.user_id == world.users["editor"].id).values(role=role)
    )
    db.commit()
    assert client.get(endpoint(ready)).status_code == 404


def test_export_rechecks_authority_after_source_work(client, db, world, ready, monkeypatch):
    original = dossier_export.source_projection

    def revoke(*args):
        value = original(*args)
        db.execute(
            update(Membership)
            .where(Membership.user_id == world.users["editor"].id)
            .values(role="author")
        )
        db.flush()
        return value

    monkeypatch.setattr(dossier_export, "source_projection", revoke)
    response = client.get(endpoint(ready))
    assert response.status_code == 403
    assert "content-disposition" not in response.headers
    assert ready["data"]["title"] not in response.text


def test_wrong_parent_version_and_unknown_version_are_not_access_grants(client, ready):
    other = create(client)
    assert client.get(endpoint(other, ready["version_id"])).status_code == 404
    assert client.get(endpoint(ready, str(uuid4()))).status_code == 404


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_original_provenance_is_exported_only_for_unchanged_fields(client, login, extension):
    login()
    initial = create(client)
    imported = stage(client, initial, extension)
    approved = accept(client, initial, imported)
    changed = deepcopy(approved["data"])
    changed["title"] = "Manually corrected title without original-file evidence"
    changed["authors"] = list(reversed(changed["authors"]))
    changed["authors"][1]["email"] = "manually-corrected@synthetic.test"
    latest = save(client, approved, data=changed)
    response = client.get(endpoint(latest))
    assert response.status_code == 200, response.text
    out = response.json()
    document = out["document"]
    assert document["import_id"] == imported["id"]
    assert document["sha256"] == imported["sha256"]
    assert document["parser"] == imported["parser"]
    assert document["warnings"] == imported["warnings"]
    assert out["file"]["sha256"] == approved["file"]["sha256"]
    assert out["verified"] is False
    fields = {item["field_path"]: item for item in out["field_sources"]}
    assert "title" not in fields and "authors.1.email" not in fields
    assert fields["authors.1.name"]["value"] == "Synthetic Author Alpha"
    assert fields["authors.0.name"]["value"] == "Synthetic Author Beta"
    assert fields["authors.0.name"]["original_sha256"] == imported["sha256"]
    for field in fields.values():
        assert imported["text"][field["start"] : field["end"]] == field["quote"]
        assert field["locations"]
        assert all(
            location["kind"] == ("pdf_page" if extension == "pdf" else "docx_paragraph")
            for location in field["locations"]
        )


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_damaged_extracted_file_refuses_the_entire_export(
    client, ready, private_export_storage, damage
):
    sha = ready["file"]["sha256"]
    path = private_export_storage / sha[:2] / sha
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"not the original extracted text")
    response = client.get(endpoint(ready))
    assert response.status_code == 409
    assert "content-disposition" not in response.headers


def test_damaged_original_refuses_the_entire_export(client, login, db, private_export_storage):
    login()
    initial = create(client)
    imported = stage(client, initial)
    approved = accept(client, initial, imported)
    original = db.get(DocumentImport, imported["id"])
    (private_export_storage / "document-originals" / original.storage_key).write_bytes(b"corrupt")
    response = client.get(endpoint(approved))
    assert response.status_code == 409
    assert "content-disposition" not in response.headers


def test_expired_session_does_not_download_metadata(client, ready):
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get(endpoint(ready)).status_code == 401
