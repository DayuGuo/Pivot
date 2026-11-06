"""Deterministic, audited authentication gateway. Never available to model tools.

Changing identity selects an existing membership, never creates a role grant.
The old session is deleted atomically; no bearer or CSRF token enters the audit.
"""

import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .db import get_db
from .domain.core import digest, lock_request
from .domain.models import ActionReceipt
from .models import Journal, LoginSession, Membership, now
from .security import Actor, ensure_current_actor, get_actor, journal_memberships, new_session
from .serialization import user_json

router = APIRouter(prefix="/api/auth", tags=["identity"])


class SwitchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["editor", "chief_editor", "reviewer", "author", "production_editor"]
    request_id: UUID


def identities_json(db: Session, actor: Actor):
    journal = db.get(Journal, actor.journal_id)
    roles = [m.role for m in journal_memberships(db, actor.user.id)]
    return {
        "user": user_json(actor),
        "journal": {"id": journal.id, "name": journal.name},
        "active_role": actor.role,
        "roles": roles,
        "csrf_token": actor.session.csrf_token,
    }


@router.get("/identities")
def identities(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return identities_json(db, actor)


@router.post("/identity")
def switch_identity(
    body: SwitchInput,
    response: Response,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    request_id = str(body.request_id)
    lock_request(db, actor, request_id)
    # Match the business gateway's request→session order, including reused UUIDs.
    # A short session lock serializes concurrent switches and final commits. No
    # provider, mailbox, or document work is performed while holding this lock.
    db.execute(
        select(LoginSession.token_hash)
        .where(LoginSession.token_hash == actor.session.token_hash)
        .with_for_update()
    ).one_or_none()
    ensure_current_actor(db, actor)
    fingerprint = digest({"action": "switch_identity", "role": body.role})
    previous = db.scalar(
        select(ActionReceipt).where(
            ActionReceipt.user_id == actor.user.id,
            ActionReceipt.journal_id == actor.journal_id,
            ActionReceipt.request_id == request_id,
        )
    )
    if previous:
        if (
            previous.action_type != "switch_identity"
            or previous.input_digest != fingerprint
            or actor.role != body.role
        ):
            raise HTTPException(409, "此切换请求已处理，请重新核对当前身份")
        return identities_json(db, actor)
    membership = db.scalar(
        select(Membership)
        .where(
            Membership.user_id == actor.user.id,
            Membership.journal_id == actor.journal_id,
            Membership.role == body.role,
        )
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    ensure_current_actor(db, actor, for_commit=True)
    if not membership or membership.journal_id != actor.journal_id:
        raise HTTPException(403, "此账号尚未获授该身份")
    if membership.id == actor.membership.id:
        return identities_json(db, actor)
    token, replacement = new_session(actor.user, membership)
    replacement.expires_at = actor.session.expires_at  # Switching never extends login lifetime.
    db.add(replacement)
    db.add(
        ActionReceipt(
            user_id=actor.user.id,
            journal_id=actor.journal_id,
            request_id=request_id,
            action_type="switch_identity",
            input_digest=fingerprint,
            response={"role": membership.role},
        )
    )
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="auth.identity_switched",
        entity_id=actor.user.id,
        details={
            "from_role": actor.role,
            "to_role": membership.role,
            "request_id": str(body.request_id),
        },
    )
    db.delete(actor.session)
    db.commit()
    response.set_cookie(
        "publishing_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=max(1, int((replacement.expires_at - now()).total_seconds())),
        path="/",
    )
    return identities_json(db, Actor(actor.user, membership, replacement))
