from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from apps.api.publishing import actions, main
from apps.api.publishing.actions import CREATE_TOOL
from apps.api.publishing.db import engine
from apps.api.publishing.models import (
    AuditEvent,
    CommandReceipt,
    EditorialTask,
    Journal,
    Manuscript,
    Membership,
    Message,
    User,
)
from apps.api.publishing.runtime import execute_command
from apps.api.publishing.security import Actor, hash_password, new_session
from apps.api.publishing.workflow import transition
from packages.model_gateway import MockModelProvider

from .conftest import PASSWORD, PROMPT


def command(client, message=PROMPT, request_id=None):
    return client.post(
        "/api/conversations/commands",
        json={
            "message": message,
            "request_id": request_id or str(uuid4()),
        },
    )


def journal_count(db, table, journal_id):
    return db.scalar(select(func.count()).select_from(table).where(table.journal_id == journal_id))


def test_login_cookie_csrf_restore_and_logout(client, login, db, world):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/workspace").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"email": world.users["editor"].email, "password": "wrong"}
        ).status_code
        == 401
    )
    data = login()
    assert data["user"]["role"] == "editor"
    assert client.get("/api/auth/me").json() == data
    assert client.cookies.get("publishing_session")
    cookie = next(c for c in client.cookies.jar if c.name == "publishing_session")
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.get_nonstandard_attr("SameSite").lower() == "strict"
    client.headers.pop("X-CSRF-Token")
    assert command(client).status_code == 403
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = "invalid-token"
    assert command(client).status_code == 403
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert journal_count(db, Manuscript, world.journal.id) == 0


def test_cross_site_login_and_mutations_blocked(client, login):
    response = client.post(
        "/api/auth/login",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"email": "editor@publishing.test", "password": "EditorDemo2026!"},
    )
    assert response.status_code == 403
    login()
    assert (
        client.post(
            "/api/conversations/commands",
            headers={"Sec-Fetch-Site": "cross-site"},
            json={"message": PROMPT, "request_id": str(uuid4())},
        ).status_code
        == 403
    )


def test_real_intake_persists_state_task_and_audit(client, login, db, world):
    actor = login()["user"]
    request_id = str(uuid4())
    response = command(client, request_id=request_id)
    assert response.status_code == 200, response.text
    result = response.json()
    manuscript_id = result["manuscript"]["id"]
    assert result["provider"] == "mock"
    assert "模拟" in result["message"]["content"]
    assert result["manuscript"]["status"] == "screening"
    assert result["manuscript"]["task"]["kind"] == "initial_screening"
    db.expire_all()
    manuscript = db.get(Manuscript, manuscript_id)
    assert manuscript.journal_id == world.journal.id
    assert manuscript.author_id == world.synthetic_author.id
    assert manuscript.editor_id == actor["id"]
    assert manuscript.status == "screening"
    task = db.scalar(select(EditorialTask).where(EditorialTask.manuscript_id == manuscript_id))
    assert task.assignee_id == actor["id"] and task.status == "pending"
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == manuscript_id)).all()
    assert {e.action for e in events} >= {
        "manuscript.created",
        "manuscript.transitioned",
        "editorial_task.assigned",
        "agent.command_completed",
    }
    transitions = {
        (e.details["from"], e.details["to"])
        for e in events
        if e.action == "manuscript.transitioned"
    }
    assert transitions == {("draft", "submitted"), ("submitted", "screening")}
    assert all(e.actor_id == actor["id"] for e in events)
    restored = client.get("/api/workspace").json()
    assert manuscript_id in {m["id"] for m in restored["manuscripts"]}
    assert len(restored["messages"]) == 2
    assert restored["email_send_enabled"] is False
    assert client.get(f"/api/manuscripts/{manuscript_id}").json() == result["manuscript"]
    assert client.get("/api/health").json()["database"] == "postgresql"


def test_idempotency_duplicate_and_different_input_conflict(client, login, db, world):
    login()
    request_id = str(uuid4())
    original = command(client, request_id=request_id)
    duplicate = command(client, request_id=request_id)
    assert original.status_code == duplicate.status_code == 200
    assert duplicate.json() == original.json()
    assert journal_count(db, Manuscript, world.journal.id) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(CommandReceipt)
            .where(CommandReceipt.user_id == world.users["editor"].id)
        )
        == 1
    )
    conflict = command(client, message="不同内容", request_id=request_id)
    assert conflict.status_code == 409
    assert journal_count(db, Manuscript, world.journal.id) == 1
    assert len(client.get("/api/workspace").json()["messages"]) == 2


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_roles_cannot_trigger_editorial_actions(client, login, db, world, role):
    login(role)
    assert command(client).status_code == 403
    assert journal_count(db, Manuscript, world.journal.id) == 0
    workspace = client.get("/api/workspace").json()
    assert workspace["audit"] == []
    assert workspace["messages"] == []


def test_chief_editor_can_create(client, login):
    login("chief_editor")
    assert command(client).status_code == 200


def test_author_ownership_and_cross_journal_visibility(client, login, db, world):
    owner = world.users["author"]
    editor = world.users["editor"]
    owned = Manuscript(
        journal_id=world.journal.id,
        author_id=owner.id,
        editor_id=editor.id,
        title="Owned synthetic manuscript",
        status="screening",
    )
    foreign = Manuscript(
        journal_id=world.other_journal.id,
        author_id=owner.id,
        editor_id=editor.id,
        title="Cross-journal synthetic",
        status="screening",
    )
    others = Manuscript(
        journal_id=world.journal.id,
        author_id=world.synthetic_author.id,
        editor_id=editor.id,
        title="Other author's manuscript",
        status="screening",
    )
    db.add_all([owned, foreign, others])
    db.commit()
    login("author")
    assert client.get(f"/api/manuscripts/{owned.id}").status_code == 200
    assert client.get(f"/api/manuscripts/{foreign.id}").status_code == 404
    assert client.get(f"/api/manuscripts/{others.id}").status_code == 404
    assert {m["id"] for m in client.get("/api/workspace").json()["manuscripts"]} == {owned.id}
    login("editor")
    assert client.get(f"/api/manuscripts/{foreign.id}").status_code == 404
    assert foreign.id not in {m["id"] for m in client.get("/api/workspace").json()["manuscripts"]}
    login("reviewer")
    assert client.get(f"/api/manuscripts/{owned.id}").status_code == 404
    assert client.get("/api/workspace").json()["manuscripts"] == []


def test_unsupported_prompt_records_explanation_without_manuscript(client, login, db, world):
    login()
    result = command(client, message="你好，介绍一下系统")
    assert result.status_code == 200
    assert result.json()["manuscript"] is None
    assert "当前原型支持" in result.json()["message"]["content"]
    assert journal_count(db, Manuscript, world.journal.id) == 0
    assert len(client.get("/api/workspace").json()["messages"]) == 2


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("send_email", {}),
        ("accept_manuscript", {}),
        (CREATE_TOOL, {"title": "Forged", "status": "accepted"}),
        (CREATE_TOOL, {"journal_id": "forged-journal", "editor_id": "forged-editor"}),
        (CREATE_TOOL, {"title": ""}),
        (CREATE_TOOL, {"title": 42}),
    ],
)
def test_model_cannot_escalate_tools_or_arguments(
    client, login, db, world, monkeypatch, tool, arguments
):
    login()
    monkeypatch.setattr(
        main,
        "provider",
        SimpleNamespace(
            propose=lambda _message: SimpleNamespace(
                tool=tool, arguments=arguments, provider="mock"
            )
        ),
    )
    assert command(client).status_code == 422
    assert journal_count(db, Manuscript, world.journal.id) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.user_id == world.users["editor"].id)
        )
        == 0
    )


def test_failed_transaction_rolls_back_manuscript_task_receipt_and_audit(
    client, login, db, world, monkeypatch
):
    login()
    actual_transition = actions.transition

    def fail_after_first_transition(db, actor, manuscript, target):
        actual_transition(db, actor, manuscript, target)
        if target == "screening":
            raise HTTPException(409, "Injected workflow failure")

    monkeypatch.setattr(actions, "transition", fail_after_first_transition)
    result = command(client)
    assert result.status_code == 409
    assert journal_count(db, Manuscript, world.journal.id) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.journal_id == world.journal.id, AuditEvent.action.like("manuscript.%")
            )
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(CommandReceipt)
            .where(CommandReceipt.user_id == world.users["editor"].id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.user_id == world.users["editor"].id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.journal_id == world.journal.id, AuditEvent.action == "action.denied")
        )
        == 1
    )


def test_workflow_blocks_major_decisions_and_cross_journal(db, world):
    user = world.users["editor"]
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    actor = Actor(user, membership, new_session(user)[1])
    manuscript = Manuscript(
        journal_id=world.journal.id,
        author_id=world.synthetic_author.id,
        editor_id=user.id,
        title="Synthetic",
        status="screening",
    )
    db.add(manuscript)
    db.flush()
    for target in ("accepted", "rejected", "withdrawn", "published"):
        with pytest.raises(HTTPException) as denied:
            transition(db, actor, manuscript, target)
        assert denied.value.status_code == 409
        assert manuscript.status == "screening"
    manuscript.journal_id = world.other_journal.id
    manuscript.status = "draft"
    with pytest.raises(HTTPException) as denied:
        transition(db, actor, manuscript, "submitted")
    assert denied.value.status_code == 403


def test_concurrent_duplicate_commands_use_real_connections():
    """Keeps uniquely named synthetic evidence; never deletes shared demo/E2E data."""
    suffix = uuid4().hex
    with Session(engine, expire_on_commit=False) as setup:
        journal = Journal(name=f"Pytest concurrency {suffix}")
        user = User(
            email=f"concurrent-{suffix}@publishing.test",
            name="并发测试编辑",
            password_hash=hash_password(PASSWORD),
        )
        setup.add_all([journal, user])
        setup.flush()
        synthetic_author = setup.scalar(select(User).where(User.email == "author@publishing.test"))
        assert synthetic_author is not None, "Run bootstrap before the PostgreSQL integration suite"
        membership = Membership(user_id=user.id, journal_id=journal.id, role="editor")
        setup.add_all(
            [
                membership,
                Membership(user_id=synthetic_author.id, journal_id=journal.id, role="author"),
            ]
        )
        setup.commit()
        user_id, journal_id = user.id, journal.id
    request_id = str(uuid4())

    def run(_):
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            membership = db.scalar(select(Membership).where(Membership.user_id == user_id))
            actor = Actor(user, membership, new_session(user)[1])
            return execute_command(db, actor, PROMPT, request_id, MockModelProvider())

    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(run, range(4)))
    finally:
        # Revoke only the grant created by this test, retaining manuscripts/audit
        # evidence. A shared demo account must not acquire ambiguous journals.
        with Session(engine) as cleanup:
            cleanup.execute(
                delete(Membership).where(
                    Membership.user_id == synthetic_author.id,
                    Membership.journal_id == journal_id,
                )
            )
            cleanup.commit()

    assert all(result == results[0] for result in results)
    with Session(engine) as db:
        assert journal_count(db, Manuscript, journal_id) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(CommandReceipt)
                .where(CommandReceipt.user_id == user_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.journal_id == journal_id, AuditEvent.action == "manuscript.created"
                )
            )
            == 1
        )
