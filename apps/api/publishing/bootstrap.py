"""Idempotent local-only synthetic data bootstrap, after Alembic migrations."""

from sqlalchemy import select, text

from .audit import record
from .db import SessionLocal
from .models import Journal, Membership, User
from .security import hash_password

DEMO_USERS = [
    ("editor@publishing.test", "林编辑", "editor", "EditorDemo2026!"),
    ("author@publishing.test", "陈作者", "author", "AuthorDemo2026!"),
    ("reviewer@publishing.test", "周审稿人", "reviewer", "ReviewerDemo2026!"),
    ("reviewer2@publishing.test", "刘审稿人", "reviewer", "Reviewer2Demo2026!"),
    ("chief@publishing.test", "许主编", "chief_editor", "ChiefDemo2026!"),
]


def seed() -> None:
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(718420001)"))
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
        for email, name, role, password in DEMO_USERS:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, name=name, password_hash=hash_password(password))
                db.add(user)
                db.flush()
                db.add(Membership(user_id=user.id, journal_id=journal.id, role=role))
                record(
                    db,
                    actor_id=None,
                    journal_id=journal.id,
                    action="user.created",
                    entity_id=user.id,
                    details={"role": role, "synthetic": True},
                )


if __name__ == "__main__":
    seed()
