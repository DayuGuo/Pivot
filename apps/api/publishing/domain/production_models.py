"""Immutable proof packages, author responses and authenticated local preview facts.

These relations do not create a public Publication, register DOI or send mail. Proof
FileObjects remain separate from the frozen accepted version's VersionFile set.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid
from . import decision_models as decision_models  # register immutable acceptance parents
from .models import _same_manuscript, _tenant_manuscript


class ProofPackage(Base):
    __tablename__ = "publishing_proof_packages"
    __table_args__ = (
        _tenant_manuscript("fk_pub_proof_package_tenant"),
        _same_manuscript(
            "accepted_version_id", "publishing_versions", "fk_pub_proof_package_version"
        ),
        _same_manuscript(
            "acceptance_decision_id",
            "publishing_editorial_decisions",
            "fk_pub_proof_package_acceptance",
        ),
        _same_manuscript(
            "human_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_proof_package_confirmation",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_proof_package_file_tenant",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_proof_package_id_manuscript"),
        UniqueConstraint(
            "id", "manuscript_id", "accepted_version_id", name="uq_pub_proof_package_version"
        ),
        UniqueConstraint("manuscript_id", "package_no", name="uq_pub_proof_package_sequence"),
        UniqueConstraint("human_confirmation_id", name="uq_pub_proof_package_confirmation"),
        CheckConstraint(
            "package_no>=1 AND length(btrim(display_name)) BETWEEN 1 AND 255",
            name="ck_pub_proof_package_sequence",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata_snapshot)='object' AND material_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_proof_package_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    accepted_version_id: Mapped[str] = mapped_column(String(36))
    acceptance_decision_id: Mapped[str] = mapped_column(String(36))
    package_no: Mapped[int] = mapped_column(Integer)
    file_object_id: Mapped[str] = mapped_column(String(36))
    display_name: Mapped[str] = mapped_column(String(255))
    metadata_snapshot: Mapped[dict] = mapped_column(JSONB)
    material_digest: Mapped[str] = mapped_column(String(64))
    production_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    human_confirmation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProofResponse(Base):
    __tablename__ = "publishing_proof_responses"
    __table_args__ = (
        _same_manuscript(
            "package_id", "publishing_proof_packages", "fk_pub_proof_response_package"
        ),
        _same_manuscript(
            "human_confirmation_id",
            "publishing_human_confirmations",
            "fk_pub_proof_response_confirmation",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_proof_response_id_manuscript"),
        UniqueConstraint("id", "manuscript_id", "package_id", name="uq_pub_proof_response_package"),
        UniqueConstraint("package_id", name="uq_pub_proof_response_once"),
        UniqueConstraint("human_confirmation_id", name="uq_pub_proof_response_confirmation"),
        CheckConstraint(
            "outcome IN ('approve','request_corrections')", name="ck_pub_proof_response_outcome"
        ),
        CheckConstraint(
            "outcome<>'request_corrections' OR length(btrim(notes))>=20",
            name="ck_pub_proof_response_notes",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    package_id: Mapped[str] = mapped_column(String(36))
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    human_confirmation_id: Mapped[str] = mapped_column(String(36))
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PublicationPreview(Base):
    __tablename__ = "publishing_publication_previews"
    __table_args__ = (
        _tenant_manuscript("fk_pub_preview_tenant"),
        _same_manuscript("accepted_version_id", "publishing_versions", "fk_pub_preview_version"),
        ForeignKeyConstraint(
            ["package_id", "manuscript_id", "accepted_version_id"],
            [
                "publishing_proof_packages.id",
                "publishing_proof_packages.manuscript_id",
                "publishing_proof_packages.accepted_version_id",
            ],
            name="fk_pub_preview_package_version",
        ),
        ForeignKeyConstraint(
            ["proof_response_id", "manuscript_id", "package_id"],
            [
                "publishing_proof_responses.id",
                "publishing_proof_responses.manuscript_id",
                "publishing_proof_responses.package_id",
            ],
            name="fk_pub_preview_response_package",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_preview_file_tenant",
        ),
        _same_manuscript(
            "human_confirmation_id", "publishing_human_confirmations", "fk_pub_preview_confirmation"
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_preview_id_manuscript"),
        UniqueConstraint("package_id", name="uq_pub_preview_package"),
        UniqueConstraint("human_confirmation_id", name="uq_pub_preview_confirmation"),
        CheckConstraint(
            "jsonb_typeof(metadata_snapshot)='object' AND content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_preview_snapshot",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    accepted_version_id: Mapped[str] = mapped_column(String(36))
    package_id: Mapped[str] = mapped_column(String(36))
    proof_response_id: Mapped[str] = mapped_column(String(36))
    metadata_snapshot: Mapped[dict] = mapped_column(JSONB)
    file_object_id: Mapped[str] = mapped_column(String(36))
    display_name: Mapped[str] = mapped_column(String(255))
    content_digest: Mapped[str] = mapped_column(String(64))
    production_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    human_confirmation_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
