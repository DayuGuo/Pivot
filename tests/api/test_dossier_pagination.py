"""Keyset positions never grant access; pages keep immutable version evidence."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from apps.api.publishing.domain.dossier_models import Dossier
from apps.api.publishing.domain.pagination import cursor_position
from tests.api.test_document_imports import stage
from tests.api.test_dossiers import create, metadata, save


def pages(client, path, limit=2):
    result = []
    cursor = None
    for _ in range(20):
        response = client.get(
            path, params={"limit": limit, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200, response.text
        page = response.json()
        result.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return result
    pytest.fail("Pagination did not terminate")


def test_list_stable_ties_search_and_scope(client, db, login):
    login("editor")
    tied = datetime(2026, 1, 1, tzinfo=UTC)

    def tie_timestamp(mapper, connection, target):
        target.created_at = tied

    event.listen(Dossier, "before_insert", tie_timestamp)
    try:
        items = [create(client, title=f"Synthetic literal %_ {n}") for n in range(5)]
    finally:
        event.remove(Dossier, "before_insert", tie_timestamp)
    first = client.get("/api/dossiers", params={"limit": 2}).json()
    # Editing a title must not reorder remaining pages.
    save(client, items[0], data=metadata(title="Changed synthetic title"))
    listed = pages(client, "/api/dossiers")
    assert [v["id"] for v in listed] == sorted([v["id"] for v in items], reverse=True)
    assert len({v["id"] for v in listed}) == 5
    matching = client.get("/api/dossiers", params={"query": "%_"}).json()
    assert len(matching["items"]) == 4  # SQL wildcards treated literally
    assert (
        client.get(
            "/api/dossiers", params={"query": "Changed", "cursor": first["next_cursor"]}
        ).status_code
        == 422
    )
    login("chief_editor")
    assert client.get("/api/dossiers", params={"cursor": first["next_cursor"]}).status_code == 422
    assert client.get("/api/dossiers").json()["items"] == []


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"cursor": "not-a-cursor"}, {"cursor": "a" * 601}]
)
def test_invalid_pagination(client, login, params):
    login("editor")
    assert client.get("/api/dossiers", params=params).status_code == 422


def test_message_version_and_import_pages(client, login, tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("editor")
    item = create(client)
    all_messages = []
    for n in range(5):
        response = client.post(
            f"/api/dossiers/{item['id']}/assist",
            json={
                "request_id": str(uuid4()),
                "expected_revision": item["revision"],
                "version_id": item["version_id"],
                "message": f"合成问题 {n}",
            },
        )
        assert response.status_code == 200
        all_messages.append(response.json())
        if n < 2:
            item = save(client, item, data=metadata(title=f"Synthetic version {n}"))
    path = f"/api/dossiers/{item['id']}"
    messages = pages(client, path + "/messages")
    assert {v["id"] for v in messages} == {v["id"] for v in all_messages}
    assert len(messages) == 5
    for message in messages:
        original = next(v for v in all_messages if v["id"] == message["id"])
        assert message["version_id"] == original["version_id"]
        assert message["version_no"] == original["version_no"]
    assert [v["number"] for v in pages(client, path + "/versions")] == [3, 2, 1]
    imports = [stage(client, item, "docx") for _ in range(3)]
    assert {v["id"] for v in pages(client, path + "/imports")} == {v["id"] for v in imports}
    cursor = client.get(path + "/messages", params={"limit": 2}).json()["next_cursor"]
    another = create(client)
    assert (
        client.get(f"/api/dossiers/{another['id']}/messages", params={"cursor": cursor}).status_code
        == 422
    )
    assert client.get(path + "/versions", params={"cursor": cursor}).status_code == 422
    login("chief_editor")
    for suffix in ("/messages", "/versions", "/imports"):
        assert client.get(path + suffix).status_code == 404


@pytest.mark.parametrize("identifier", [True, {}, [], 32])
def test_cursor_json_types_fail_closed(identifier):
    cursor = base64.urlsafe_b64encode(
        json.dumps(
            {"scope": "synthetic", "at": "2026-11-04T00:00:00+00:00", "id": identifier}
        ).encode()
    ).decode()
    with pytest.raises(HTTPException) as error:
        cursor_position(cursor, "synthetic")
    assert error.value.status_code == 422
