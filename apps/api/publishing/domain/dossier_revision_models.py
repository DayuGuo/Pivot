"""Immutable internal revision evidence and append-only human judgements."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid


class DossierRevisionCheck(Base):
    __tablename__ = "publishing_dossier_revision_checks"
    __table_args__ = (
        UniqueConstraint("id", "dossier_id", "journal_id", name="uq_dossier_revision_check_scope"),
        ForeignKeyConstraint(
            ["base_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_revision_base",
        ),
        ForeignKeyConstraint(
            ["revised_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_revision_revised",
        ),
        CheckConstraint(
            "revision>=2 AND base_version_id<>revised_version_id AND digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_dossier_revision_check_shape",
        ),
        CheckConstraint(
            "jsonb_typeof(materials_json)='object' AND octet_length(materials_json::text)<=262144 AND jsonb_typeof(report_json)='object' AND octet_length(report_json::text)<=262144",
            name="ck_dossier_revision_check_json",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    base_version_id: Mapped[str] = mapped_column(String(36))
    revised_version_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    materials_json: Mapped[dict] = mapped_column(JSONB)
    report_json: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierRevisionReview(Base):
    __tablename__ = "publishing_dossier_revision_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["check_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_revision_checks.id",
                "publishing_dossier_revision_checks.dossier_id",
                "publishing_dossier_revision_checks.journal_id",
            ],
            name="fk_dossier_revision_review_check",
        ),
        UniqueConstraint("check_id", "point_id", "review_no", name="uq_dossier_revision_review_no"),
        CheckConstraint(
            "point_id ~ '^P0[1-8]$' AND review_no>=1 AND check_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_dossier_revision_review_shape",
        ),
        CheckConstraint(
            "response_verdict IN ('addressed','not_addressed','uncertain') AND implementation_verdict IN ('changed','partial','unchanged','not_located','uncertain') AND editor_verdict IN ('sufficient','follow_up','needs_judgment') AND length(btrim(reason)) BETWEEN 5 AND 2000",
            name="ck_dossier_revision_review_verdicts",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    check_id: Mapped[str] = mapped_column(String(36))
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    point_id: Mapped[str] = mapped_column(String(8))
    check_digest: Mapped[str] = mapped_column(String(64))
    response_verdict: Mapped[str] = mapped_column(String(20))
    implementation_verdict: Mapped[str] = mapped_column(String(20))
    editor_verdict: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(2000))
    review_no: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
