"""Immutable private-dossier persistence models; no routes or model-provider imports."""

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


class Dossier(Base):
    __tablename__ = "publishing_dossiers"
    __table_args__ = (
        UniqueConstraint("id", "journal_id", name="uq_dossier_tenant"),
        CheckConstraint("revision >= 1", name="ck_dossier_revision"),
        ForeignKeyConstraint(
            ["current_version_id", "id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_current",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer)
    current_version_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierVersion(Base):
    __tablename__ = "publishing_dossier_versions"
    __table_args__ = (
        UniqueConstraint("id", "dossier_id", "journal_id", name="uq_dossier_version_tenant"),
        UniqueConstraint("dossier_id", "version_no", name="uq_dossier_version_number"),
        ForeignKeyConstraint(
            ["dossier_id", "journal_id"],
            ["publishing_dossiers.id", "publishing_dossiers.journal_id"],
            name="fk_dossier_version_parent",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_dossier_version_file",
        ),
        CheckConstraint("version_no >= 1", name="ck_dossier_version_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_no: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[dict] = mapped_column(JSONB)
    file_object_id: Mapped[str | None] = mapped_column(String(36))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_media_type: Mapped[str | None] = mapped_column(String(100))
    content_digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierCheck(Base):
    __tablename__ = "publishing_dossier_checks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_check_version",
        ),
        UniqueConstraint("version_id", name="uq_dossier_checked_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    content_digest: Mapped[str] = mapped_column(String(64))
    checked_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierTurn(Base):
    __tablename__ = "publishing_dossier_turns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_turn_version",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(String(2000))
    answer: Mapped[str] = mapped_column(String(6000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
