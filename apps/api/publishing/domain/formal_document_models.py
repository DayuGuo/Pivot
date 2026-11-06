"""Immutable formal file import proposals and confirmed/inherited source bindings.

A binding is archival evidence. Its file_id is checked on insert, not an FK to
mutable draft links: replacing a draft file must preserve the original approval.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid
from .models import _same_manuscript, _tenant_manuscript


class FormalDocumentImport(Base):
    __tablename__ = "publishing_formal_document_imports"
    __table_args__ = (
        _tenant_manuscript("fk_formal_import_manuscript"),
        _same_manuscript("version_id", "publishing_versions", "fk_formal_import_version"),
        UniqueConstraint("id", "manuscript_id", "journal_id", name="uq_formal_import_tenant"),
        Index(
            "ix_formal_import_pending",
            "journal_id",
            "manuscript_id",
            "version_id",
            "created_at",
            "id",
        ),
        CheckConstraint(
            "purpose IN ('manuscript','blinded_manuscript','response')",
            name="ck_formal_import_purpose",
        ),
        CheckConstraint(
            "source_kind IN ('synthetic','public_authorized') AND length(source_note) BETWEEN 5 AND 2000",
            name="ck_formal_import_authorization",
        ),
        CheckConstraint(
            "base_revision>=0 AND byte_size BETWEEN 1 AND 5242880 AND sha256 ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$'",
            name="ck_formal_import_evidence",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    base_revision: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(100))
    extraction_json: Mapped[dict] = mapped_column(JSONB)
    source_kind: Mapped[str] = mapped_column(String(30))
    source_note: Mapped[str] = mapped_column(String(2000))
    digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FormalDocumentBinding(Base):
    __tablename__ = "publishing_formal_document_bindings"
    __table_args__ = (
        _tenant_manuscript("fk_formal_binding_manuscript"),
        _same_manuscript("version_id", "publishing_versions", "fk_formal_binding_version"),
        ForeignKeyConstraint(
            ["import_id", "manuscript_id", "journal_id"],
            [
                "publishing_formal_document_imports.id",
                "publishing_formal_document_imports.manuscript_id",
                "publishing_formal_document_imports.journal_id",
            ],
            name="fk_formal_binding_import",
        ),
        ForeignKeyConstraint(
            ["parent_id", "import_id", "manuscript_id", "journal_id"],
            [
                "publishing_formal_document_bindings.id",
                "publishing_formal_document_bindings.import_id",
                "publishing_formal_document_bindings.manuscript_id",
                "publishing_formal_document_bindings.journal_id",
            ],
            name="fk_formal_binding_parent",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_formal_binding_blob",
        ),
        UniqueConstraint(
            "id", "import_id", "manuscript_id", "journal_id", name="uq_formal_binding_identity"
        ),
        CheckConstraint(
            "selection_start>=0 AND selection_end>selection_start",
            name="ck_formal_binding_selection",
        ),
        UniqueConstraint("file_id", name="uq_formal_binding_file"),
        Index(
            "uq_formal_import_confirmation",
            "import_id",
            unique=True,
            postgresql_where=text("kind='confirmed'"),
        ),
        CheckConstraint(
            "(kind='confirmed' AND parent_id IS NULL AND confirmed_by IS NOT NULL AND session_hash IS NOT NULL) OR (kind='inherited' AND parent_id IS NOT NULL AND confirmed_by IS NULL AND session_hash IS NULL)",
            name="ck_formal_binding_kind",
        ),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$' AND (session_hash IS NULL OR session_hash ~ '^[0-9a-f]{64}$')",
            name="ck_formal_binding_digest",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    file_id: Mapped[str] = mapped_column(String(36))
    manuscript_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    file_object_id: Mapped[str] = mapped_column(String(36))
    import_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    parent_id: Mapped[str | None] = mapped_column(String(36))
    confirmed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    selection_start: Mapped[int] = mapped_column(Integer)
    selection_end: Mapped[int] = mapped_column(Integer)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
