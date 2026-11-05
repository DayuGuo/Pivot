"""Large private queues must retain older work without per-manuscript projections."""

from uuid import uuid4

import pytest
from sqlalchemy import event, select

from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import WorkItem
from apps.api.publishing.models import LoginSession, Membership
from apps.api.publishing.security import Actor


def author_actor(db, world, role="author"):
    user = world.users[role]
    return Actor(
        user,
        db.scalar(select(Membership).where(Membership.user_id == user.id)),
        db.scalar(select(LoginSession).where(LoginSession.user_id == user.id)),
    )


@pytest.mark.parametrize("size", [1, 201])
def test_queue_retains_older_priority_work_with_bounded_sql(client, login, db, world, size):
    login("author")
    actor = author_actor(db, world)
    items = [core.new_draft(db, actor, f"合成队列规模回归 {i}") for i in range(size)]
    db.flush()
    old_id = items[0]["manuscript_id"]
    old_task = db.scalar(select(WorkItem).where(WorkItem.manuscript_id == old_id))
    old_task.priority = 99
    db.commit()
    queries = []

    def count(*args):
        queries.append(True)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", count)
    try:
        response = client.get("/api/publishing/workspace")
    finally:
        event.remove(connection, "before_cursor_execute", count)
    assert response.status_code == 200, response.text
    work = response.json()
    assert len(work["tasks"]) == size
    assert work["tasks"][0]["manuscript_id"] == old_id
    assert work["counts"]["actionable"] == size
    assert old_id in {s["id"] for s in work["submissions"]}
    assert len(queries) <= 14, len(queries)
    assert all(
        "visibility_scope" not in s and "allowed_actions" not in s for s in work["submissions"]
    )


def test_explicit_older_manuscript_conversation_is_not_limited_to_recent_list(
    client, login, db, world, monkeypatch, tmp_path
):
    from tests.api.test_publishing_screening import submit

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    older = submit(client, login)
    actor = author_actor(db, world)
    for i in range(201):
        core.new_draft(db, actor, f"合成较新草稿 {i}")
    db.commit()
    assert older not in {
        s["id"] for s in client.get("/api/publishing/workspace").json()["submissions"]
    }
    response = client.post(
        "/api/publishing/chat",
        json={
            "request_id": str(uuid4()),
            "message": "只读：这篇稿件目前是什么状态？",
            "context": {"manuscript_id": older, "scope": "case", "view": "work"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["state_changed"] is False
    assert any(
        r["manuscript_id"] == older for m in response.json()["messages"] for r in m["references"]
    )


def test_reviewer_queue_uses_invitation_title_and_a_narrow_anonymous_dto(
    client, login, db, world, monkeypatch, tmp_path
):
    import json

    from tests.api.test_publishing_peer_review import open_round, reviewer_selection

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    login("reviewer")
    invitation = client.get(f"/api/publishing/manuscripts/{mid}").json()["review"]["invitation"]
    response = client.get("/api/publishing/workspace")
    assert response.status_code == 200, response.text
    work = response.json()
    summary = next(s for s in work["submissions"] if s["id"] == mid)
    assert summary["title"] == invitation["title"]
    assert set(summary) == {
        "id",
        "number",
        "title",
        "stage",
        "stage_label",
        "revision",
        "is_legacy",
        "is_owner",
    }
    assert world.users["author"].email not in json.dumps(work)
    assert all(
        t["title"] == invitation["title"] for t in work["tasks"] if t["manuscript_id"] == mid
    )


def test_old_journal_history_reuses_scopes_only_within_one_get_and_rechecks_revocation(
    client, login, db, world, monkeypatch, tmp_path
):
    from datetime import timedelta

    from sqlalchemy import update

    from apps.api.publishing.domain.models import Assignment, PublishingChatTurn
    from apps.api.publishing.models import now
    from tests.api.test_publishing_screening import submit

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    mids = [submit(client, login) for _ in range(5)]
    login("editor")
    actor = author_actor(db, world, "editor")
    scopes = {
        mid: core.submission_projection(db, actor, mid, detail=False)["visibility_scope"]
        for mid in mids
    }
    for i in range(20):
        db.add(
            PublishingChatTurn(
                user_id=actor.user.id,
                journal_id=actor.journal_id,
                manuscript_id=None,
                request_id=str(uuid4()),
                input_digest=core.digest({"synthetic": i}),
                context_snapshot={
                    "role": "editor",
                    "read_manuscript_ids": mids,
                    "visibility_scopes": scopes,
                },
                response={
                    "messages": [
                        {
                            "id": str(uuid4()),
                            "role": "assistant",
                            "content": "合成旧版历史规模回归",
                            "provider": "mock",
                            "references": [],
                            "tool_receipts": [],
                            "action": None,
                        }
                    ]
                },
            )
        )
    db.commit()
    queries = []
    connection = db.connection()

    def count(*args):
        queries.append(True)

    event.listen(connection, "before_cursor_execute", count)
    try:
        response = client.get("/api/publishing/chat")
    finally:
        event.remove(connection, "before_cursor_execute", count)
    assert response.status_code == 200, response.text
    assert len(response.json()["messages"]) == 20
    assert len(queries) <= 100, len(queries)
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mids[0], Assignment.user_id == actor.user.id)
        .values(ends_at=now() - timedelta(seconds=1))
    )
    db.commit()
    denied = client.get("/api/publishing/chat")
    assert denied.status_code == 200 and denied.json()["messages"] == []
