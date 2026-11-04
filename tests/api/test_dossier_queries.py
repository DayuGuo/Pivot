"""Private list queries must stay owner-scoped and constant in number."""

import re
from uuid import uuid4

from sqlalchemy import event

from apps.api.publishing.models import Membership, User
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_dossiers import create


def test_list_has_one_content_query_and_never_includes_another_editors_dossiers(
    client, db, world, login
):
    login("editor")
    owned = [create(client, title=f"Owned synthetic dossier {i}") for i in range(4)]
    other = User(
        email=f"other-list-{uuid4().hex}@publishing.test",
        name="Other editor",
        password_hash=hash_password(PASSWORD),
    )
    db.add(other)
    db.flush()
    db.add(Membership(user_id=other.id, journal_id=world.journal.id, role="editor"))
    db.commit()
    response = client.post("/api/auth/login", json={"email": other.email, "password": PASSWORD})
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    foreign = create(client, title="Private other editor title")
    login("editor")
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and re.search(
            r"\bpublishing_dossier(?:s|_versions|_checks)\b", statement
        ):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        result = client.get("/api/dossiers")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert result.status_code == 200
    items = result.json()["items"]
    assert {item["id"] for item in items} == {item["id"] for item in owned}
    assert foreign["id"] not in {item["id"] for item in items}
    assert all(item["version_no"] == 1 and item["verified"] is False for item in items)
    assert len(statements) == 1, "The private list must not issue per-dossier version/check queries"


def test_detail_batches_legacy_turns_without_one_answer_query_per_message(client, db, login):
    login("editor")
    item = create(client)
    for number in range(6):
        response = client.post(
            f"/api/dossiers/{item['id']}/assist",
            json={
                "request_id": str(uuid4()),
                "expected_revision": item["revision"],
                "version_id": item["version_id"],
                "message": f"合成资料检查 {number}",
            },
        )
        assert response.status_code == 200
    queries = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "publishing_dossier_answers" in statement
        ):
            queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        response = client.get(f"/api/dossiers/{item['id']}")
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert len(messages) == 6
    assert all(
        message["provider"] == "rules" and message["version_no"] == 1 for message in messages
    )
    assert len(queries) == 1
