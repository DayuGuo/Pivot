"""Persisted independent connections serialize session rotation with final authority."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from apps.api.publishing import security
from apps.api.publishing.db import engine
from apps.api.publishing.main import app
from apps.api.publishing.models import AuditEvent, Journal, LoginSession, Membership, User
from apps.api.publishing.security import Actor, new_session


@pytest.fixture
def persisted_identity():
    # Unique synthetic records remain as evidence, like the existing confirmation
    # concurrency harness. No shared data or unrelated sessions are removed.
    suffix = uuid4().hex
    with Session(engine, expire_on_commit=False) as db:
        journal = Journal(name=f"Pytest identity concurrency {suffix}")
        user = User(
            email=f"identity-{suffix}@synthetic.test",
            name="合成身份并发测试",
            password_hash="not-a-login",
        )
        db.add_all([journal, user])
        db.flush()
        editor = Membership(user_id=user.id, journal_id=journal.id, role="editor")
        reviewer = Membership(user_id=user.id, journal_id=journal.id, role="reviewer")
        db.add_all([editor, reviewer])
        db.flush()
        raw_cookie, session = new_session(user, editor)
        db.add(session)
        db.commit()
        return SimpleNamespace(
            user_id=user.id,
            journal_id=journal.id,
            editor_id=editor.id,
            reviewer_id=reviewer.id,
            session_hash=session.token_hash,
            raw_cookie=raw_cookie,
            csrf=session.csrf_token,
            expires_at=session.expires_at,
        )


def load_actor(db, identity):
    return Actor(
        db.get(User, identity.user_id),
        db.get(Membership, identity.editor_id),
        db.get(LoginSession, identity.session_hash),
    )


def rotate_on_connection(identity, started=None, backend_pid=None):
    with Session(engine, expire_on_commit=False) as db:
        if backend_pid is not None:
            backend_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
        if started is not None:
            started.set()
        db.execute(delete(LoginSession).where(LoginSession.token_hash == identity.session_hash))
        _, replacement = new_session(
            db.get(User, identity.user_id), db.get(Membership, identity.reviewer_id)
        )
        replacement.expires_at = identity.expires_at
        db.add(replacement)
        db.commit()
        return replacement.token_hash


def test_final_authority_lock_serializes_rotation_after_pending_commit(persisted_identity):
    identity = persisted_identity
    started = Event()
    backend_pid = []
    action = f"identity.concurrency_committed.{uuid4().hex}"
    with Session(engine, expire_on_commit=False) as db, ThreadPoolExecutor(max_workers=1) as pool:
        actor = load_actor(db, identity)
        security.ensure_current_actor(db, actor, for_commit=True)
        db.add(
            AuditEvent(
                actor_id=identity.user_id,
                journal_id=identity.journal_id,
                action=action,
                entity_id=identity.user_id,
                details={"synthetic": True},
            )
        )
        rotation = pool.submit(rotate_on_connection, identity, started, backend_pid)
        try:
            assert started.wait(5), "rotation did not reach its independent connection"
            deadline = monotonic() + 5
            blocked = False
            with Session(engine) as observation:
                while monotonic() < deadline:
                    blocked = bool(
                        observation.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": backend_pid[0]},
                        )
                    )
                    if blocked:
                        break
                    sleep(0.01)
            assert blocked, "rotation must wait for final authorization's session row lock"
            assert not rotation.done()
            db.commit()
            replacement_hash = rotation.result(timeout=5)
        finally:
            db.rollback()
        db.expire_all()
        assert db.get(LoginSession, identity.session_hash) is None
        assert db.get(LoginSession, replacement_hash).active_membership_id == identity.reviewer_id
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == action))


def test_rotation_before_final_authority_rejects_old_pending_write(persisted_identity):
    identity = persisted_identity
    action = f"identity.concurrency_rolled_back.{uuid4().hex}"
    with Session(engine, expire_on_commit=False) as pending:
        actor = load_actor(pending, identity)
        security.ensure_current_actor(pending, actor)
        replacement_hash = rotate_on_connection(identity)
        pending.add(
            AuditEvent(
                actor_id=identity.user_id,
                journal_id=identity.journal_id,
                action=action,
                entity_id=identity.user_id,
                details={"synthetic": True},
            )
        )
        with pytest.raises(HTTPException) as failure:
            security.ensure_current_actor(pending, actor, for_commit=True)
        assert failure.value.status_code in {401, 403}
        pending.rollback()
    with Session(engine) as check:
        assert check.get(LoginSession, identity.session_hash) is None
        assert (
            check.get(LoginSession, replacement_hash).active_membership_id == identity.reviewer_id
        )
        assert not check.scalar(select(AuditEvent.id).where(AuditEvent.action == action))


def test_simultaneous_switches_with_same_old_cookie_rotate_only_once(persisted_identity):
    identity = persisted_identity
    ready = Barrier(2)

    def request_switch(_):
        with TestClient(app) as client:
            ready.wait(timeout=5)
            return client.post(
                "/api/auth/identity",
                headers={
                    "Cookie": f"publishing_session={identity.raw_cookie}",
                    "X-CSRF-Token": identity.csrf,
                },
                json={"role": "reviewer", "request_id": str(uuid4())},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(request_switch, range(2)))
    assert statuses.count(200) == 1
    assert all(status in {200, 401, 403} for status in statuses)
    with Session(engine) as db:
        assert db.get(LoginSession, identity.session_hash) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LoginSession)
                .where(LoginSession.user_id == identity.user_id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.actor_id == identity.user_id,
                    AuditEvent.action == "auth.identity_switched",
                )
            )
            == 1
        )
