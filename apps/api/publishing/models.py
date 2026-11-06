from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Journal(Base):
    __tablename__ = "journals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "journal_id", "role", name="uq_membership_user_journal_role"),
        UniqueConstraint("id", "user_id", name="uq_membership_id_user"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    role: Mapped[str] = mapped_column(String(30))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["active_membership_id", "user_id"],
            ["memberships.id", "memberships.user_id"],
            name="fk_session_active_membership_user",
        ),
    )
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    active_membership_id: Mapped[str | None] = mapped_column(String(36))
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Manuscript(Base):
    __tablename__ = "manuscripts"
    __table_args__ = (
        UniqueConstraint("id", "journal_id", name="uq_manuscript_id_journal"),
        CheckConstraint(
            "workflow_kind IN ('legacy','publishing')", name="ck_manuscript_workflow_kind"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    editor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    workflow_kind: Mapped[str] = mapped_column(
        String(20), default="legacy", server_default="legacy"
    )
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EditorialTask(Base):
    __tablename__ = "editorial_tasks"
    __table_args__ = (UniqueConstraint("manuscript_id", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(ForeignKey("manuscripts.id"))
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(40), default="initial_screening")
    status: Mapped[str] = mapped_column(String(30), default="pending")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    title: Mapped[str] = mapped_column(String(120), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    manuscript_id: Mapped[str | None] = mapped_column(ForeignKey("manuscripts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CommandReceipt(Base):
    __tablename__ = "command_receipts"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str | None] = mapped_column(ForeignKey("journals.id"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="draft")


class EmailApproval(Base):
    __tablename__ = "email_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    draft_id: Mapped[str] = mapped_column(ForeignKey("email_drafts.id"))
    approver_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    digest: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSON)
    valid: Mapped[bool] = mapped_column(default=True)


class MailAccount(Base):
    __tablename__ = "mail_accounts"
    __table_args__ = (UniqueConstraint("journal_id", "provider", "address"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(120))
    smtp_host: Mapped[str | None] = mapped_column(String(253))
    smtp_port: Mapped[int | None]
    tls_mode: Mapped[str] = mapped_column(String(20), default="starttls")
    auth_mode: Mapped[str] = mapped_column(String(20), default="none")
    username: Mapped[str | None] = mapped_column(String(254))
    credential_ref: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    enabled: Mapped[bool] = mapped_column(default=True)
    last_error: Mapped[str | None] = mapped_column(String(200))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
