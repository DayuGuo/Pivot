"""Fixed-round, confirmed in-app peer review; policy/projections live in the gateway.

Independent implementation of spec008. OJS stage/round/assignment separation and
Janeway frozen review-form patterns inform these relations, not runtime dependencies.
No mail transport, external invitation token, author release or chief decision here.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid
from .models import _same_manuscript, _tenant_manuscript


def _round_version(name):
    return ForeignKeyConstraint(
        ["round_id", "manuscript_id", "version_id"],
        [
            "publishing_review_rounds.id",
            "publishing_review_rounds.manuscript_id",
            "publishing_review_rounds.version_id",
        ],
        name=name,
    )


class ReviewRound(Base):
    __tablename__ = "publishing_review_rounds"
    __table_args__ = (
        _tenant_manuscript("fk_pub_review_round_tenant"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_review_round_version"),
        _same_manuscript(
            "opening_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_round_confirmation",
        ),
        _same_manuscript(
            "closing_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_round_closing_confirmation",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_review_round_id_manuscript"),
        UniqueConstraint("id", "manuscript_id", "version_id", name="uq_pub_review_round_version"),
        UniqueConstraint("manuscript_id", "round_no", name="uq_pub_review_round_sequence"),
        CheckConstraint(
            "round_no >= 1 AND policy_version >= 1", name="ck_pub_review_round_sequence"
        ),
        CheckConstraint("required_reports BETWEEN 1 AND 3", name="ck_pub_review_round_target"),
        CheckConstraint(
            "status IN ('initializing','open','closed','cancelled')",
            name="ck_pub_review_round_status",
        ),
        CheckConstraint(
            "review_method = 'double_anonymous' AND form_key = 'basic_peer_review' AND form_version = 1",
            name="ck_pub_review_round_form",
        ),
        CheckConstraint(
            "form_digest ~ '^[0-9a-f]{64}$' AND material_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_review_round_digests",
        ),
        CheckConstraint(
            "jsonb_typeof(form_snapshot) = 'object'", name="ck_pub_review_round_schema"
        ),
        CheckConstraint(
            "(status='initializing' AND material_sealed_at IS NULL AND closed_at IS NULL) OR (status='open' AND material_sealed_at IS NOT NULL AND closed_at IS NULL) OR (status IN ('closed','cancelled') AND material_sealed_at IS NOT NULL AND closed_at IS NOT NULL AND closing_confirmation_id IS NOT NULL AND length(btrim(closure_reason))>0)",
            name="ck_pub_review_round_lifecycle",
        ),
        Index(
            "uq_pub_review_round_open",
            "manuscript_id",
            unique=True,
            postgresql_where=text("status='open'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    round_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default="initializing", server_default="initializing"
    )
    material_sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    required_reports: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    policy_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    review_method: Mapped[str] = mapped_column(
        String(30), default="double_anonymous", server_default="double_anonymous"
    )
    form_key: Mapped[str] = mapped_column(
        String(60), default="basic_peer_review", server_default="basic_peer_review"
    )
    form_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    form_snapshot: Mapped[dict] = mapped_column(JSONB)
    form_digest: Mapped[str] = mapped_column(String(64))
    material_digest: Mapped[str] = mapped_column(String(64))
    opened_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    opening_confirmation_id: Mapped[str] = mapped_column(String(36))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closure_reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    closing_confirmation_id: Mapped[str | None] = mapped_column(String(36))


class ReviewRoundFile(Base):
    __tablename__ = "publishing_review_round_files"
    __table_args__ = (
        _round_version("fk_pub_review_round_file_round"),
        ForeignKeyConstraint(
            ["version_file_id", "manuscript_id", "version_id"],
            [
                "publishing_version_files.id",
                "publishing_version_files.manuscript_id",
                "publishing_version_files.version_id",
            ],
            name="fk_pub_review_round_file_version_file",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_review_round_file_id_manuscript"),
        UniqueConstraint("round_id", "version_file_id", name="uq_pub_review_round_file_link"),
        CheckConstraint("role='blinded_manuscript'", name="ck_pub_review_round_file_role"),
        CheckConstraint(
            "display_name IN ('review-manuscript.txt','review-manuscript.md')",
            name="ck_pub_review_round_file_name",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    round_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    version_file_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(
        String(40), default="blinded_manuscript", server_default="blinded_manuscript"
    )
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewInvitation(Base):
    __tablename__ = "publishing_review_invitations"
    __table_args__ = (
        _tenant_manuscript("fk_pub_review_invitation_tenant"),
        _round_version("fk_pub_review_invitation_round"),
        _same_manuscript(
            "invitation_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_invitation_confirmation",
        ),
        _same_manuscript(
            "response_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_invitation_response",
        ),
        _same_manuscript(
            "terminal_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_invitation_terminal",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_review_invitation_id_manuscript"),
        UniqueConstraint(
            "id",
            "manuscript_id",
            "version_id",
            "reviewer_id",
            name="uq_pub_review_invitation_target",
        ),
        UniqueConstraint(
            "round_id", "reviewer_id", "attempt_no", name="uq_pub_review_invitation_attempt"
        ),
        CheckConstraint(
            "attempt_no >= 1 AND policy_version >= 1", name="ck_pub_review_invitation_attempt"
        ),
        CheckConstraint(
            "status IN ('pending','accepted','declined','cancelled','expired','submitted')",
            name="ck_pub_review_invitation_status",
        ),
        CheckConstraint(
            "conflict_status IN ('unanswered','none','declared')",
            name="ck_pub_review_invitation_conflict",
        ),
        CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(invitation_snapshot)='object'",
            name="ck_pub_review_invitation_content",
        ),
        CheckConstraint(
            "report_due_at > response_due_at AND response_due_at > invited_at",
            name="ck_pub_review_invitation_deadlines",
        ),
        CheckConstraint(
            "(status='pending' AND responded_at IS NULL AND accepted_at IS NULL AND declined_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND conflict_status='unanswered' AND response_confirmation_id IS NULL AND terminal_confirmation_id IS NULL) OR (status IN ('accepted','submitted') AND responded_at IS NOT NULL AND accepted_at IS NOT NULL AND declined_at IS NULL AND cancelled_at IS NULL AND conflict_status='none' AND response_confirmation_id IS NOT NULL AND ((status='accepted' AND completed_at IS NULL) OR (status='submitted' AND completed_at IS NOT NULL))) OR (status='declined' AND responded_at IS NOT NULL AND declined_at IS NOT NULL AND accepted_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND response_confirmation_id IS NOT NULL) OR (status='cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL AND terminal_confirmation_id IS NOT NULL) OR (status='expired' AND responded_at IS NULL AND accepted_at IS NULL AND declined_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND response_confirmation_id IS NULL AND terminal_confirmation_id IS NULL)",
            name="ck_pub_review_invitation_lifecycle",
        ),
        Index(
            "uq_pub_review_invitation_effective",
            "round_id",
            "reviewer_id",
            unique=True,
            postgresql_where=text("status IN ('pending','accepted','submitted')"),
        ),
        Index("ix_pub_review_invitation_reviewer", "reviewer_id", "status", "response_due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    round_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    attempt_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    invited_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    invitation_snapshot: Mapped[dict] = mapped_column(JSONB)
    content_digest: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[int] = mapped_column(Integer)
    response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    invited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conflict_status: Mapped[str] = mapped_column(
        String(20), default="unanswered", server_default="unanswered"
    )
    response_notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    invitation_confirmation_id: Mapped[str] = mapped_column(String(36))
    response_confirmation_id: Mapped[str | None] = mapped_column(String(36))
    terminal_confirmation_id: Mapped[str | None] = mapped_column(String(36))


class ReviewReport(Base):
    __tablename__ = "publishing_review_reports"
    __table_args__ = (
        _same_manuscript(
            "invitation_id", "publishing_review_invitations", "fk_pub_review_report_invitation"
        ),
        _same_manuscript(
            "human_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_review_report_confirmation",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_review_report_id_manuscript"),
        UniqueConstraint("invitation_id", name="uq_pub_review_report_invitation"),
        CheckConstraint(
            "status IN ('draft','submitted','withdrawn') AND revision >= 0",
            name="ck_pub_review_report_status",
        ),
        CheckConstraint(
            "recommendation IN ('unanswered','accept','minor_revision','major_revision','reject')",
            name="ck_pub_review_report_recommendation",
        ),
        CheckConstraint(
            "form_digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(form_snapshot)='object' AND jsonb_typeof(answers_json)='object'",
            name="ck_pub_review_report_schema",
        ),
        CheckConstraint(
            "(status='submitted' AND submitted_at IS NOT NULL AND human_confirmation_id IS NOT NULL AND content_digest IS NOT NULL AND content_digest ~ '^[0-9a-f]{64}$' AND recommendation <> 'unanswered') OR (status IN ('draft','withdrawn') AND submitted_at IS NULL AND human_confirmation_id IS NULL AND content_digest IS NULL)",
            name="ck_pub_review_report_submission",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    invitation_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    form_snapshot: Mapped[dict] = mapped_column(JSONB)
    form_digest: Mapped[str] = mapped_column(String(64))
    author_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    editor_private_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    answers_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    recommendation: Mapped[str] = mapped_column(
        String(30), default="unanswered", server_default="unanswered"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    human_confirmation_id: Mapped[str | None] = mapped_column(String(36))
    content_digest: Mapped[str | None] = mapped_column(String(64))
