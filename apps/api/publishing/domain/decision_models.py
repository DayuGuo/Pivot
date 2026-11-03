"""Confirmed editorial decisions, anonymous releases and immutable revision lineage.

OJS separates recommendations/decisions/rounds; Janeway preserves form and author
snapshots. These independently written relations implement spec009, without mail,
publication, model authority or the service's multi-hop minor-revision reasoning.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
from . import review_models as review_models  # register existing round/report FK parents
from .models import _same_manuscript, _tenant_manuscript


class EditorialDecision(Base):
    __tablename__ = "publishing_editorial_decisions"
    __table_args__ = (
        _tenant_manuscript("fk_pub_decision_tenant"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_decision_version"),
        _same_manuscript("step_run_id", "publishing_step_runs", "fk_pub_decision_step"),
        _same_manuscript(
            "basis_round_id", "publishing_review_rounds", "fk_pub_decision_basis_round"
        ),
        _same_manuscript(
            "recommendation_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_decision_recommendation",
        ),
        _same_manuscript(
            "reassessment_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_decision_reassessment",
        ),
        _same_manuscript(
            "human_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_decision_confirmation",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_decision_id_manuscript"),
        UniqueConstraint("human_confirmation_id", name="uq_pub_decision_confirmation"),
        UniqueConstraint("step_run_id", name="uq_pub_decision_step"),
        CheckConstraint(
            "decision_code IN ('request_revision','accept','reject')", name="ck_pub_decision_code"
        ),
        CheckConstraint(
            "(decision_code='request_revision' AND revision_kind IS NOT NULL AND revision_kind IN ('minor','major')) OR (decision_code IN ('accept','reject') AND revision_kind IS NULL)",
            name="ck_pub_decision_revision_kind",
        ),
        CheckConstraint(
            "length(btrim(rationale_private)) BETWEEN 20 AND 8000 AND length(btrim(author_letter)) BETWEEN 20 AND 12000",
            name="ck_pub_decision_text",
        ),
        CheckConstraint(
            "policy_version >= 1 AND payload_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_decision_digest",
        ),
        Index("ix_pub_decision_history", "manuscript_id", "decided_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    step_run_id: Mapped[str] = mapped_column(String(36))
    basis_round_id: Mapped[str] = mapped_column(String(36))
    recommendation_confirmation_id: Mapped[str] = mapped_column(String(36))
    reassessment_confirmation_id: Mapped[str | None] = mapped_column(String(36))
    decision_code: Mapped[str] = mapped_column(String(30))
    revision_kind: Mapped[str | None] = mapped_column(String(20))
    rationale_private: Mapped[str] = mapped_column(Text)
    author_letter: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[int] = mapped_column(Integer)
    chief_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    human_confirmation_id: Mapped[str] = mapped_column(String(36))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    payload_digest: Mapped[str] = mapped_column(String(64))


class DecisionReportRelease(Base):
    __tablename__ = "publishing_decision_report_releases"
    __table_args__ = (
        _same_manuscript(
            "decision_id", "publishing_editorial_decisions", "fk_pub_release_decision"
        ),
        _same_manuscript("report_id", "publishing_review_reports", "fk_pub_release_report"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_release_id_manuscript"),
        UniqueConstraint("decision_id", "report_id", name="uq_pub_release_decision_report"),
        UniqueConstraint("decision_id", "ordinal", name="uq_pub_release_order"),
        CheckConstraint("ordinal >= 1", name="ck_pub_release_order"),
        CheckConstraint(
            "jsonb_typeof(author_snapshot)='object' AND snapshot_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_release_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    decision_id: Mapped[str] = mapped_column(String(36))
    report_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)
    author_snapshot: Mapped[dict] = mapped_column(JSONB)
    snapshot_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RevisionRequest(Base):
    __tablename__ = "publishing_revision_requests"
    __table_args__ = (
        _tenant_manuscript("fk_pub_revision_tenant"),
        _same_manuscript(
            "decision_id", "publishing_editorial_decisions", "fk_pub_revision_decision"
        ),
        _same_manuscript("base_version_id", "publishing_versions", "fk_pub_revision_base"),
        _same_manuscript("draft_version_id", "publishing_versions", "fk_pub_revision_draft"),
        _same_manuscript(
            "submitted_version_id", "publishing_versions", "fk_pub_revision_submitted"
        ),
        _same_manuscript(
            "author_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_revision_confirmation",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_revision_id_manuscript"),
        UniqueConstraint("decision_id", name="uq_pub_revision_decision"),
        UniqueConstraint("manuscript_id", "request_no", name="uq_pub_revision_sequence"),
        CheckConstraint(
            "request_no >= 1 AND kind IN ('minor','major')", name="ck_pub_revision_kind"
        ),
        CheckConstraint("kind <> 'major' OR rereview_required=true", name="ck_pub_revision_major"),
        CheckConstraint(
            "draft_version_id <> base_version_id AND length(btrim(author_instructions))>=20",
            name="ck_pub_revision_material",
        ),
        CheckConstraint(
            "(status='requested' AND submitted_version_id IS NULL AND submitted_at IS NULL AND author_confirmation_id IS NULL) OR (status='submitted' AND submitted_version_id IS NOT NULL AND submitted_version_id=draft_version_id AND submitted_at IS NOT NULL AND author_confirmation_id IS NOT NULL)",
            name="ck_pub_revision_submission",
        ),
        Index(
            "uq_pub_revision_requested",
            "manuscript_id",
            unique=True,
            postgresql_where=text("status='requested'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    decision_id: Mapped[str] = mapped_column(String(36))
    request_no: Mapped[int] = mapped_column(Integer)
    base_version_id: Mapped[str] = mapped_column(String(36))
    draft_version_id: Mapped[str] = mapped_column(String(36))
    submitted_version_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    rereview_required: Mapped[bool] = mapped_column(Boolean)
    author_instructions: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="requested", server_default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_confirmation_id: Mapped[str | None] = mapped_column(String(36))
