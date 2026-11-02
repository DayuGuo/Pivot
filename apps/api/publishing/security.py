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


def get_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = request.cookies.get("publishing_session", "")
    session = db.get(LoginSession, token_digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401, "请先登录 Publishing OS")
    user = db.get(User, session.user_id)
    membership = db.scalar(select(Membership).where(Membership.user_id == session.user_id))
    if not user or not membership:
        raise HTTPException(403, "没有期刊访问权限")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(csrf, session.csrf_token):
            raise HTTPException(403, "CSRF 验证失败")
    return Actor(user, membership, session)


def new_session(user: User) -> tuple[str, LoginSession]:
    token = secrets.token_urlsafe(32)
    return token, LoginSession(
        token_hash=token_digest(token),
        user_id=user.id,
        csrf_token=secrets.token_hex(32),
        expires_at=now() + timedelta(hours=8),
    )
