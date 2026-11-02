"""Normalized publishing foundation: identity, versions, responsibilities and confirmation.

No fixture IDs or provider capabilities live here. Frozen historical content is also
protected by PostgreSQL triggers in the matching migration.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid

STAGES = (
    "author_draft",
    "precheck_completeness",
    "similarity_review",
    "technical_screening",
    "chief_scope",
    "assign_editor",
    "editor_quality",
    "reviewer_selection",
    "peer_review",
    "editor_recommendation",
    "chief_decision",
    "author_revision",
    "revision_assessment",
    "production",
    "author_proof",
    "preview_confirmation",
    "preview_ready",
    "legacy_screening",
    "rejected",
)


def _same_manuscript(column: str, table: str, name: str, *, use_alter: bool = False):
    return ForeignKeyConstraint(
        [column, "manuscript_id"],
        [f"{table}.id", f"{table}.manuscript_id"],
        name=name,
        use_alter=use_alter,
    )


def _tenant_manuscript(name: str):
    return ForeignKeyConstraint(
        ["manuscript_id", "journal_id"],
        ["manuscripts.id", "manuscripts.journal_id"],
        name=name,
    )


class SubmissionWorkflow(Base):
    __tablename__ = "publishing_workflows"
    __table_args__ = (
        _tenant_manuscript("fk_pub_workflow_manuscript_journal"),
        UniqueConstraint("journal_id", "number", name="uq_pub_workflow_journal_number"),
        CheckConstraint("revision >= 0", name="ck_pub_workflow_revision"),
        CheckConstraint("required_reports BETWEEN 1 AND 3", name="ck_pub_workflow_report_target"),
        CheckConstraint(
            "stage IN (" + ",".join(repr(stage) for stage in STAGES) + ")",
            name="ck_pub_workflow_stage",
        ),
        _same_manuscript(
            "current_version_id",
            "publishing_versions",
            "fk_pub_workflow_current_version",
            use_alter=True,
        ),
        _same_manuscript(
            "draft_version_id",
            "publishing_versions",
            "fk_pub_workflow_draft_version",
            use_alter=True,
        ),
        _same_manuscript(
            "accepted_version_id",
            "publishing_versions",
            "fk_pub_workflow_accepted_version",
            use_alter=True,
        ),
        _same_manuscript(
            "current_step_id",
            "publishing_step_runs",
            "fk_pub_workflow_current_step",
            use_alter=True,
        ),
        Index("ix_pub_workflow_queue", "journal_id", "stage", "updated_at"),
    )
    manuscript_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("manuscripts.id"), primary_key=True
    )
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    number: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(50))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    policy_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    draft_version_id: Mapped[str | None] = mapped_column(String(36))
    accepted_version_id: Mapped[str | None] = mapped_column(String(36))
    current_step_id: Mapped[str | None] = mapped_column(String(36))
    chief_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    assigned_editor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    production_editor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    required_reports: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_legacy: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManuscriptVersion(Base):
    __tablename__ = "publishing_versions"
    __table_args__ = (
        UniqueConstraint("id", "manuscript_id", name="uq_pub_version_id_manuscript"),
        UniqueConstraint("manuscript_id", "version_no", name="uq_pub_version_sequence"),
        CheckConstraint("version_no >= 1", name="ck_pub_version_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500), default="", server_default="")
    abstract: Mapped[str] = mapped_column(Text, default="", server_default="")
    language: Mapped[str] = mapped_column(String(20), default="zh", server_default="zh")
    article_type: Mapped[str] = mapped_column(
        String(60), default="research_article", server_default="research_article"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    content_digest: Mapped[str | None] = mapped_column(String(64))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    provenance: Mapped[str] = mapped_column(
        String(30), default="authored", server_default="authored"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VersionAuthor(Base):
    __tablename__ = "publishing_version_authors"
    __table_args__ = (
        _same_manuscript("version_id", "publishing_versions", "fk_pub_author_version"),
        UniqueConstraint("version_id", "ordinal", name="uq_pub_author_order"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_author_id_manuscript"),
        CheckConstraint("ordinal >= 0", name="ck_pub_author_order"),
        Index(
            "uq_pub_author_corresponding",
            "version_id",
            unique=True,
            postgresql_where=text("corresponding = true"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    orcid: Mapped[str | None] = mapped_column(String(32))
    affiliations: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    corresponding: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    contributions: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    linked_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))


class FileObject(Base):
    __tablename__ = "publishing_file_objects"
    __table_args__ = (
        UniqueConstraint("journal_id", "sha256", name="uq_pub_file_journal_hash"),
        UniqueConstraint("id", "journal_id", name="uq_pub_file_id_journal"),
        CheckConstraint("byte_size BETWEEN 1 AND 1048576", name="ck_pub_file_size"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str] = mapped_column(String(255))
    scan_status: Mapped[str] = mapped_column(
        String(30), default="validated_text", server_default="validated_text"
    )
    check_method: Mapped[str] = mapped_column(
        String(60), default="utf8_text_safety", server_default="utf8_text_safety"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VersionFile(Base):
    __tablename__ = "publishing_version_files"
    __table_args__ = (
        _tenant_manuscript("fk_pub_version_file_manuscript_journal"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_version_file_version"),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_version_file_object_journal",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_version_file_id_manuscript"),
        UniqueConstraint("version_id", "purpose", name="uq_pub_version_file_purpose"),
        CheckConstraint(
            "purpose IN ('manuscript','blinded_manuscript','response','similarity_report','proof')",
            name="ck_pub_version_file_purpose",
        ),
        CheckConstraint(
            "visibility IN ('author_editor','reviewer','production')",
            name="ck_pub_version_file_visibility",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    file_object_id: Mapped[str] = mapped_column(String(36))
    purpose: Mapped[str] = mapped_column(String(40))
    visibility: Mapped[str] = mapped_column(String(30))
    display_name: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Assignment(Base):
    __tablename__ = "publishing_assignments"
    __table_args__ = (
        _tenant_manuscript("fk_pub_assignment_manuscript_journal"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_assignment_id_manuscript"),
        CheckConstraint(
            "capability IN ('author','precheck','handling_editor','chief','production')",
            name="ck_pub_assignment_capability",
        ),
        Index(
            "uq_pub_assignment_active_capability",
            "manuscript_id",
            "user_id",
            "capability",
            unique=True,
            postgresql_where=text("ends_at IS NULL"),
        ),
        Index(
            "uq_pub_assignment_active_editor",
            "manuscript_id",
            unique=True,
            postgresql_where=text("capability = 'handling_editor' AND ends_at IS NULL"),
        ),
        Index("ix_pub_assignment_user", "user_id", "ends_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    capability: Mapped[str] = mapped_column(String(40))
    assigned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")


class StepRun(Base):
    __tablename__ = "publishing_step_runs"
    __table_args__ = (
        _same_manuscript("version_id", "publishing_versions", "fk_pub_step_version"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_step_id_manuscript"),
        UniqueConstraint("manuscript_id", "step_key", "cycle_no", name="uq_pub_step_cycle"),
        CheckConstraint("cycle_no >= 1", name="ck_pub_step_cycle"),
        CheckConstraint("status IN ('pending','completed','cancelled')", name="ck_pub_step_status"),
        ForeignKeyConstraint(
            ["confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_step_confirmation",
            use_alter=True,
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    version_id: Mapped[str | None] = mapped_column(String(36))
    step_key: Mapped[str] = mapped_column(String(50))
    cycle_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    policy_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    confirmation_id: Mapped[str | None] = mapped_column(String(36))


class WorkItem(Base):
    __tablename__ = "publishing_work_items"
    __table_args__ = (
        _tenant_manuscript("fk_pub_work_item_manuscript_journal"),
        _same_manuscript("step_run_id", "publishing_step_runs", "fk_pub_work_item_step"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_work_item_version"),
        ForeignKeyConstraint(
            ["confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_work_item_confirmation",
            use_alter=True,
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_work_item_id_manuscript"),
        UniqueConstraint(
            "step_run_id", "kind", "assignee_id", name="uq_pub_work_item_step_assignee"
        ),
        CheckConstraint(
            "status IN ('pending','waiting','completed','cancelled')",
            name="ck_pub_work_item_status",
        ),
        Index("ix_pub_work_item_assignee", "assignee_id", "status", "due_at"),
        Index("ix_pub_work_item_journal", "journal_id", "status", "due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    step_run_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(60))
    assignee_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_id: Mapped[str | None] = mapped_column(String(36))


class FormDraft(Base):
    __tablename__ = "publishing_form_drafts"
    __table_args__ = (
        _same_manuscript("version_id", "publishing_versions", "fk_pub_form_version"),
        UniqueConstraint("version_id", "schema_key", "owner_id", name="uq_pub_form_version_owner"),
        CheckConstraint("revision >= 0", name="ck_pub_form_revision"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    schema_key: Mapped[str] = mapped_column(String(60), default="intake", server_default="intake")
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    base_revision: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    sources_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActionProposal(Base):
    __tablename__ = "publishing_action_proposals"
    __table_args__ = (
        _tenant_manuscript("fk_pub_proposal_manuscript_journal"),
        _same_manuscript("work_item_id", "publishing_work_items", "fk_pub_proposal_work_item"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_proposal_version"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_proposal_id_manuscript"),
        Index("ix_pub_proposal_responsible", "responsible_user_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    work_item_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    action_type: Mapped[str] = mapped_column(String(60))
    prepared_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    responsible_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    base_revision: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[int] = mapped_column(Integer)
    payload_snapshot: Mapped[dict] = mapped_column(JSONB)
    evidence_digests: Mapped[dict] = mapped_column(JSONB)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HumanConfirmation(Base):
    __tablename__ = "publishing_human_confirmations"
    __table_args__ = (
        _same_manuscript(
            "proposal_id", "publishing_action_proposals", "fk_pub_confirmation_proposal"
        ),
        UniqueConstraint("proposal_id", name="uq_pub_confirmation_proposal"),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_confirmation_id_manuscript"),
        CheckConstraint("outcome IN ('confirm','return')", name="ck_pub_confirmation_outcome"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    proposal_id: Mapped[str] = mapped_column(String(36))
    responsible_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    # Evidence survives logout/session revocation; it is intentionally not an FK.
    session_hash: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ActionReceipt(Base):
    __tablename__ = "publishing_action_receipts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "journal_id", "request_id", name="uq_pub_receipt_actor_request"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    action_type: Mapped[str] = mapped_column(String(60))
    input_digest: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PublishingChatTurn(Base):
    __tablename__ = "publishing_chat_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "journal_id", "request_id", name="uq_pub_chat_actor_request"),
        Index("ix_pub_chat_history", "user_id", "journal_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    manuscript_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    input_digest: Mapped[str] = mapped_column(String(64))
    context_snapshot: Mapped[dict] = mapped_column(JSONB)
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
