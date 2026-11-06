import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import LoginSession, Membership, User, now

ROLE_ORDER = ("editor", "chief_editor", "reviewer", "author", "production_editor")


def journal_memberships(db: Session, user_id: str) -> list[Membership]:
    members = list(db.scalars(select(Membership).where(Membership.user_id == user_id)))
    if len({member.journal_id for member in members}) > 1:
        raise HTTPException(409, "账号关联多个工作期刊，请先配置明确的工作期刊")
    return sorted(
        members,
        key=lambda item: (ROLE_ORDER.index(item.role) if item.role in ROLE_ORDER else 99, item.id),
    )


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return f"scrypt${salt}${hashed.hex()}"


def check_password(password: str, encoded: str) -> bool:
    _, salt, expected = encoded.split("$")
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex(), expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Actor:
    user: User
    membership: Membership
    session: LoginSession

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def journal_id(self) -> str:
        return self.membership.journal_id


def ensure_current_actor(db: Session, actor: Actor, *, for_commit: bool = False):
    """Pin authority; the short final KEY SHARE lock serializes commits with switching.

    Never request for_commit before provider/network work. Session rotation deletes
    the old row, so every old request must either commit before the switch or fail.
    """
    identity = actor.__dict__.get("_publishing_identity")
    if identity is None:
        identity = (
            actor.user.id,
            actor.journal_id,
            actor.role,
            actor.membership.id,
            actor.session.token_hash,
            actor.session.csrf_token,
        )
        actor.__dict__["_publishing_identity"] = identity
    user_id, journal_id, role, membership_id, session_hash, csrf = identity
    query = select(
        LoginSession.user_id,
        LoginSession.expires_at,
        LoginSession.active_membership_id,
        LoginSession.csrf_token,
    ).where(LoginSession.token_hash == session_hash)
    if for_commit:
        query = query.with_for_update(read=True, key_share=True)
    session = db.execute(query).one_or_none()
    member_query = select(Membership.user_id, Membership.journal_id, Membership.role).where(
        Membership.id == membership_id
    )
    if for_commit:
        member_query = member_query.with_for_update(read=True)
    membership = db.execute(member_query).one_or_none()
    if (
        not membership
        or tuple(membership) != (user_id, journal_id, role)
        or not session
        or session.user_id != user_id
        or session.expires_at <= now()
        or session.csrf_token != csrf
        or (
            session.active_membership_id is not None
            and session.active_membership_id != membership_id
        )
    ):
        raise HTTPException(403, "身份、期刊或会话已变化，请重新登录")
    # Compatibility for direct single-role session helpers. Ambiguous null sessions
    # never select a newly granted role after revocation.
    if session.active_membership_id is None:
        ids = list(db.scalars(select(Membership.id).where(Membership.user_id == user_id)))
        if ids != [membership_id]:
            raise HTTPException(403, "会话未绑定明确身份，请重新登录")


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = request.cookies.get("publishing_session", "")
    session = db.get(LoginSession, token_digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, "请先登录 Publishing OS")
    user = db.get(User, session.user_id)
    memberships = journal_memberships(db, session.user_id)
    membership = next((m for m in memberships if m.id == session.active_membership_id), None)
    if session.active_membership_id is None and len(memberships) == 1:
        membership = memberships[0]
    if not user or not membership:
        raise HTTPException(403, "没有期刊访问权限")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "CSRF 验证失败")
    actor = Actor(user, membership, session)
    actor.__dict__["_publishing_identity"] = (
        user.id,
        membership.journal_id,
        membership.role,
        membership.id,
        session.token_hash,
        session.csrf_token,
    )
    return actor


def new_session(user: User, membership: Membership | None = None) -> tuple[str, LoginSession]:
    token = secrets.token_urlsafe(32)
    return token, LoginSession(
        token_hash=token_digest(token),
        user_id=user.id,
        active_membership_id=membership.id if membership else None,
        csrf_token=secrets.token_hex(32),
        expires_at=now() + timedelta(hours=8),
    )
