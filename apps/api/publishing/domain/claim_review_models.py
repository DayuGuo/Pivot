"""Append-only responsible-editor feedback, never a publication decision."""

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


class ClaimReview(Base):
    __tablename__ = "publishing_claim_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_claim_review_version",
        ),
        UniqueConstraint(
            "answer_id", "claim_bucket", "claim_index", "review_no", name="uq_claim_review_sequence"
        ),
        CheckConstraint(
            "claim_bucket IN ('claims','withheld_claims') AND claim_index BETWEEN 0 AND 5 AND review_no>=1",
            name="ck_claim_review_target",
        ),
        CheckConstraint(
            "verdict IN ('supported','unsupported','uncertain') AND length(btrim(note)) BETWEEN 5 AND 2000",
            name="ck_claim_review_verdict",
        ),
        CheckConstraint(
            "claim_digest ~ '^[0-9a-f]{64}$' AND content_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_claim_review_hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(claim_json)='object' AND octet_length(claim_json::text)<=32768",
            name="ck_claim_review_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("publishing_dossier_answers.id"))
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    claim_bucket: Mapped[str] = mapped_column(String(20))
    claim_index: Mapped[int] = mapped_column(Integer)
    claim_json: Mapped[dict] = mapped_column(JSONB)
    claim_digest: Mapped[str] = mapped_column(String(64))
    content_digest: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(2000))
    review_no: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
