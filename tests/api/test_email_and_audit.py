from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.audit import record
from apps.api.publishing.email_gateway import (
    approve_draft,
    create_draft,
    digest_snapshot,
    revise_draft,
    send_email,
)
from apps.api.publishing.models import AuditEvent, EmailApproval, EmailDraft, Membership
from apps.api.publishing.security import Actor, new_session


@pytest.fixture
def editor_actor(db, world):
    user = world.users["editor"]
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    return Actor(user, membership, new_session(user)[1])


@pytest.fixture
def snapshot():
    return {
        "to": ["recipient@publishing.test"],
        "cc": [],
        "bcc": [],
        "subject": "Synthetic review invitation",
        "body": "Synthetic full body.",
        "attachments": [{"filename": "synthetic.txt", "sha256": "a" * 64}],
    }


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("to", ["different@publishing.test"]),
        ("cc", ["copy@publishing.test"]),
        ("bcc", ["hidden@publishing.test"]),
        ("subject", "Changed subject"),
        ("body", "Changed full body"),
        ("attachments", [{"filename": "synthetic.txt", "sha256": "b" * 64}]),
    ],
)
def test_email_approval_bound_to_complete_snapshot_and_revoked_on_edit(
    db, editor_actor, snapshot, field, replacement
):
    draft = create_draft(db, editor_actor, snapshot)
    approval = approve_draft(db, editor_actor, draft)
    db.flush()
    approved_id = approval.id
    original_digest = approval.digest
    assert approval.snapshot == snapshot
    assert draft.status == "approved"
    changed = deepcopy(snapshot)
    changed[field] = replacement
    revise_draft(db, editor_actor, draft, changed)
    db.flush()
    db.expire_all()
    saved_approval = db.get(EmailApproval, approved_id)
    saved_draft = db.get(EmailDraft, draft.id)
    assert saved_approval.valid is False
    assert saved_approval.snapshot == snapshot
    assert saved_approval.digest == original_digest
    assert saved_draft.digest != original_digest
    assert saved_draft.status == "draft"
    assert saved_draft.snapshot == changed


def test_snapshot_digest_is_deterministic_and_includes_attachment_contents(snapshot):
    assert digest_snapshot(snapshot) == digest_snapshot(dict(reversed(list(snapshot.items()))))
    changed = deepcopy(snapshot)
    changed["attachments"][0]["sha256"] = "c" * 64
    assert digest_snapshot(snapshot) != digest_snapshot(changed)


def test_email_send_fails_closed_even_if_environment_enabled(
    db, editor_actor, snapshot, monkeypatch
):
    monkeypatch.setenv("EMAIL_SEND_ENABLED", "true")
    draft = create_draft(db, editor_actor, snapshot)
    approve_draft(db, editor_actor, draft)
    db.flush()
    with pytest.raises(HTTPException) as blocked:
        send_email(db, editor_actor, draft, str(uuid4()))
    assert blocked.value.status_code == 403
    assert (
        db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "email.send_blocked", AuditEvent.entity_id == draft.id
            )
        )
        is not None
    )
    assert draft.status != "sent"


def test_email_cross_journal_and_non_editor_operations_forbidden(db, world, editor_actor, snapshot):
    draft = EmailDraft(
        journal_id=world.other_journal.id,
        snapshot=snapshot,
        digest=digest_snapshot(snapshot),
        status="draft",
    )
    db.add(draft)
    db.flush()
    for operation in (
        lambda: approve_draft(db, editor_actor, draft),
        lambda: revise_draft(db, editor_actor, draft, snapshot),
        lambda: send_email(db, editor_actor, draft, str(uuid4())),
    ):
        with pytest.raises(HTTPException) as denied:
            operation()
        assert denied.value.status_code == 404
    user = world.users["author"]
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    author = Actor(user, membership, new_session(user)[1])
    with pytest.raises(HTTPException) as denied:
        create_draft(db, author, snapshot)
    assert denied.value.status_code == 403


@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
def test_audit_log_is_append_only_in_postgresql(db, world, operation):
    event = record(
        db,
        actor_id=world.users["editor"].id,
        journal_id=world.journal.id,
        action="test.append_only",
        entity_id=str(uuid4()),
        details={"synthetic": True},
    )
    db.flush()
    event_id = event.id
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            if operation == "update":
                db.execute(
                    update(AuditEvent).where(AuditEvent.id == event_id).values(action="tampered")
                )
            elif operation == "delete":
                db.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
            else:
                db.execute(text("TRUNCATE audit_events"))
    db.expire_all()
    assert db.get(AuditEvent, event_id).action == "test.append_only"


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("to", "recipient@publishing.test"),
        ("to", []),
        ("cc", ["invalid-address"]),
        ("subject", "Header\nInjection"),
        ("body", None),
        ("attachments", [{"filename": "synthetic.txt", "sha256": "not-a-hash"}]),
    ],
)
def test_email_malformed_snapshot_rejected(db, editor_actor, snapshot, field, replacement):
    invalid = deepcopy(snapshot)
    invalid[field] = replacement
    with pytest.raises(HTTPException) as denied:
        create_draft(db, editor_actor, invalid)
    assert denied.value.status_code == 422


@pytest.mark.parametrize("operation", ["content", "delete", "reactivate"])
def test_approval_snapshot_is_immutable_in_postgresql(db, editor_actor, snapshot, operation):
    draft = create_draft(db, editor_actor, snapshot)
    approval = approve_draft(db, editor_actor, draft)
    db.flush()
    approval_id = approval.id
    if operation == "reactivate":
        revise_draft(db, editor_actor, draft, {**snapshot, "body": "Changed body"})
        db.flush()
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            if operation == "content":
                db.execute(
                    update(EmailApproval)
                    .where(EmailApproval.id == approval_id)
                    .values(snapshot={**snapshot, "body": "Tampered approval"})
                )
            elif operation == "delete":
                db.execute(delete(EmailApproval).where(EmailApproval.id == approval_id))
            else:
                db.execute(
                    update(EmailApproval).where(EmailApproval.id == approval_id).values(valid=True)
                )
    db.expire_all()
    assert db.get(EmailApproval, approval_id).snapshot == snapshot
