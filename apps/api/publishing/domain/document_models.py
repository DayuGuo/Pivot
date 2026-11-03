"""Original/extraction proposals, human import approval and explicit version provenance."""

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


class DocumentImport(Base):
    __tablename__ = "publishing_document_imports"
    __table_args__ = (
        UniqueConstraint("id", "dossier_id", "journal_id", name="uq_document_import_tenant"),
        ForeignKeyConstraint(
            ["base_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_import_base",
        ),
        CheckConstraint(
            "base_revision>=1 AND byte_size BETWEEN 1 AND 5242880 AND sha256 ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$'",
            name="ck_document_import_shape",
        ),
        CheckConstraint(
            "media_type IN ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document') AND jsonb_typeof(extraction_json)='object' AND jsonb_typeof(proposed_data)='object' AND jsonb_typeof(field_sources)='array' AND metadata_provider IN ('mock','deepseek')",
            name="ck_document_import_content",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    base_version_id: Mapped[str] = mapped_column(String(36))
    base_revision: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(80))
    extraction_json: Mapped[dict] = mapped_column(JSONB)
    proposed_data: Mapped[dict] = mapped_column(JSONB)
    field_sources: Mapped[list] = mapped_column(JSONB)
    metadata_provider: Mapped[str] = mapped_column(String(20))
    metadata_model: Mapped[str] = mapped_column(String(100))
    telemetry_json: Mapped[list] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentApproval(Base):
    __tablename__ = "publishing_document_approvals"
    __table_args__ = (
        UniqueConstraint("import_id", name="uq_document_approved_import"),
        UniqueConstraint("version_id", name="uq_document_approved_version"),
        UniqueConstraint(
            "id", "import_id", "dossier_id", "journal_id", name="uq_document_approval_tenant"
        ),
        ForeignKeyConstraint(
            ["import_id", "dossier_id", "journal_id"],
            [
                "publishing_document_imports.id",
                "publishing_document_imports.dossier_id",
                "publishing_document_imports.journal_id",
            ],
            name="fk_document_approval_import",
        ),
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_approval_version",
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(reviewed_data)='object'",
            name="ck_document_approval_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    import_id: Mapped[str] = mapped_column(String(36))
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    reviewed_data: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentSource(Base):
    __tablename__ = "publishing_document_sources"
    __table_args__ = (
        CheckConstraint("origin_digest ~ '^[0-9a-f]{64}$'", name="ck_document_source_digest"),
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_source_version",
        ),
        ForeignKeyConstraint(
            ["approval_id", "import_id", "dossier_id", "journal_id"],
            [
                "publishing_document_approvals.id",
                "publishing_document_approvals.import_id",
                "publishing_document_approvals.dossier_id",
                "publishing_document_approvals.journal_id",
            ],
            name="fk_document_source_approval",
        ),
    )
    version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    import_id: Mapped[str] = mapped_column(String(36))
    approval_id: Mapped[str] = mapped_column(String(36))
    origin_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
