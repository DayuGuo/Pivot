"""Immutable issued packages and responsible-owner confirmed evaluation returns."""

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


class EvaluationPackage(Base):
    __tablename__ = "publishing_evaluation_packages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_evaluation_package_version",
        ),
        UniqueConstraint("answer_id", "evaluator_code", name="uq_evaluation_package_slot"),
        UniqueConstraint(
            "id", "dossier_id", "journal_id", "version_id", name="uq_evaluation_package_scope"
        ),
        CheckConstraint(
            "evaluator_code ~ '^[a-z0-9][a-z0-9_-]{0,39}$'", name="ck_evaluation_package_code"
        ),
        CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND packet_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_evaluation_package_hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(packet_json)='object' AND octet_length(packet_json::text)<=2097152 AND jsonb_typeof(claim_map)='object' AND octet_length(claim_map::text)<=262144",
            name="ck_evaluation_package_json",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("publishing_dossier_answers.id"))
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    content_digest: Mapped[str] = mapped_column(String(64))
    evaluator_code: Mapped[str] = mapped_column(String(40))
    packet_json: Mapped[dict] = mapped_column(JSONB)
    claim_map: Mapped[dict] = mapped_column(JSONB)
    packet_digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvaluationReturn(Base):
    __tablename__ = "publishing_evaluation_returns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "dossier_id", "journal_id", "version_id"],
            [
                "publishing_evaluation_packages.id",
                "publishing_evaluation_packages.dossier_id",
                "publishing_evaluation_packages.journal_id",
                "publishing_evaluation_packages.version_id",
            ],
            name="fk_evaluation_return_package",
        ),
        UniqueConstraint("package_id", "return_no", name="uq_evaluation_return_sequence"),
        CheckConstraint("return_no>=1", name="ck_evaluation_return_sequence"),
        CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND packet_digest ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_evaluation_return_hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(assessments_json)='object' AND octet_length(assessments_json::text)<=131072",
            name="ck_evaluation_return_json",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    package_id: Mapped[str] = mapped_column(String(36))
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    content_digest: Mapped[str] = mapped_column(String(64))
    packet_digest: Mapped[str] = mapped_column(String(64))
    assessments_json: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    return_no: Mapped[int] = mapped_column(Integer)
    submitted_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
