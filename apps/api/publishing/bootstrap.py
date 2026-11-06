"""Idempotent synthetic bootstrap; private preview never enables public passwords."""

import os
import re
import secrets

from sqlalchemy import select, text

from .audit import record
from .db import SessionLocal
from .models import Journal, Membership, User
from .security import check_password, hash_password

DEMO_USERS = [
    ("editor@publishing.test", "林编辑", "editor", "EditorDemo2026!"),
    ("author@publishing.test", "陈作者", "author", "AuthorDemo2026!"),
    ("reviewer@publishing.test", "周审稿人", "reviewer", "ReviewerDemo2026!"),
    ("reviewer2@publishing.test", "刘审稿人", "reviewer", "Reviewer2Demo2026!"),
    ("chief@publishing.test", "许主编", "chief_editor", "ChiefDemo2026!"),
    ("production@publishing.test", "叶制作", "production_editor", "ProductionDemo2026!"),
]


LOCAL_MULTI_USER = ("multi@publishing.test", "顾多职务", "editor", "MultiDemo2026!")
PUBLIC_USERS = [*DEMO_USERS, LOCAL_MULTI_USER]


def configured_users():
    profile = os.getenv("PIVOT_BOOTSTRAP_PROFILE", "local")
    if profile == "local":
        return PUBLIC_USERS
    if profile != "private-preview":
        raise RuntimeError("Unknown bootstrap profile")
    email = os.getenv("PIVOT_OPERATOR_EMAIL", "").strip().lower()
    password = os.getenv("PIVOT_OPERATOR_PASSWORD", "")
    if (
        not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or len(email) > 254
        or email in {item[0] for item in PUBLIC_USERS}
        or not 16 <= len(password) <= 256
        or password in {item[3] for item in PUBLIC_USERS}
    ):
        raise RuntimeError("Private preview requires a unique operator email and strong password")
    # Synthetic role identities are needed by the sample workflow, but their random
    # passwords are never disclosed. Only the explicitly configured editor can log in.
    return [(email, "编辑", "editor", password)] + [
        (address, name, role, secrets.token_urlsafe(48)) for address, name, role, _ in DEMO_USERS
    ]


def seed() -> None:
    users = configured_users()  # Validate before any write.
    private = os.getenv("PIVOT_BOOTSTRAP_PROFILE") == "private-preview"
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(718420001)"))
        if private:
            for email, _, _, public_password in PUBLIC_USERS:
                existing = db.scalar(select(User).where(User.email == email))
                if existing and check_password(public_password, existing.password_hash):
                    raise RuntimeError(
                        "Private preview refuses a database with public demo passwords"
                    )
        journal = db.scalar(select(Journal).where(Journal.name == "开放科学 · 测试期刊"))
        if not journal:
            journal = Journal(name="开放科学 · 测试期刊")
            db.add(journal)
            db.flush()
            record(
                db,
                actor_id=None,
                journal_id=journal.id,
                action="journal.created",
                entity_id=journal.id,
                details={"synthetic": True},
            )
        for email, name, role, password in users:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, name=name, password_hash=hash_password(password))
                db.add(user)
                db.flush()
                granted_roles = [role]
                if not private and email == LOCAL_MULTI_USER[0]:
                    granted_roles.extend(("chief_editor", "reviewer", "author"))
                for granted_role in granted_roles:
                    db.add(Membership(user_id=user.id, journal_id=journal.id, role=granted_role))
                record(
                    db,
                    actor_id=None,
                    journal_id=journal.id,
                    action="user.created",
                    entity_id=user.id,
                    details={"role": role, "granted_roles": granted_roles, "synthetic": True},
                )


if __name__ == "__main__":
    seed()
