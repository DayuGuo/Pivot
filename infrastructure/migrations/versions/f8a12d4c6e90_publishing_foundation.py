"""Normalized publishing intake, responsibility and human-confirmation foundation.

Revision ID: f8a12d4c6e90
Revises: e7b24c91a603

Legacy backfill preserves known facts only. No invented files, checks, or approvals.
"""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8a12d4c6e90"
down_revision = "e7b24c91a603"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE SEQUENCE publishing_submission_number_seq AS bigint START WITH 1 INCREMENT BY 1 NO CYCLE"
    )
    op.add_column(
        "manuscripts",
        sa.Column("workflow_kind", sa.String(20), server_default="legacy", nullable=False),
    )
    op.alter_column("manuscripts", "editor_id", existing_type=sa.String(36), nullable=True)
    op.alter_column(
        "manuscripts",
        "title",
        existing_type=sa.String(240),
        type_=sa.String(500),
        existing_nullable=False,
    )
    op.create_unique_constraint("uq_manuscript_id_journal", "manuscripts", ["id", "journal_id"])
    op.create_check_constraint(
        "ck_manuscript_workflow_kind", "manuscripts", "workflow_kind IN ('legacy','publishing')"
    )
    op.create_table(
        "publishing_action_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "journal_id", "request_id", name="uq_pub_receipt_actor_request"
        ),
    )
    op.create_table(
        "publishing_file_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "scan_status", sa.String(length=30), server_default="validated_text", nullable=False
        ),
        sa.Column(
            "check_method", sa.String(length=60), server_default="utf8_text_safety", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size BETWEEN 1 AND 1048576", name="ck_pub_file_size"),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "journal_id", name="uq_pub_file_id_journal"),
        sa.UniqueConstraint("journal_id", "sha256", name="uq_pub_file_journal_hash"),
    )
    op.create_table(
        "publishing_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "capability IN ('author','precheck','handling_editor','chief','production')",
            name="ck_pub_assignment_capability",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_assignment_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_assignment_id_manuscript"),
    )
    op.create_index(
        "ix_pub_assignment_user", "publishing_assignments", ["user_id", "ends_at"], unique=False
    )
    op.create_index(
        "uq_pub_assignment_active_capability",
        "publishing_assignments",
        ["manuscript_id", "user_id", "capability"],
        unique=True,
        postgresql_where=sa.text("ends_at IS NULL"),
    )
    op.create_index(
        "uq_pub_assignment_active_editor",
        "publishing_assignments",
        ["manuscript_id"],
        unique=True,
        postgresql_where=sa.text("capability = 'handling_editor' AND ends_at IS NULL"),
    )
    op.create_table(
        "publishing_chat_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "journal_id", "request_id", name="uq_pub_chat_actor_request"
        ),
    )
    op.create_index(
        "ix_pub_chat_history",
        "publishing_chat_turns",
        ["user_id", "journal_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "publishing_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), server_default="", nullable=False),
        sa.Column("abstract", sa.Text(), server_default="", nullable=False),
        sa.Column("language", sa.String(length=20), server_default="zh", nullable=False),
        sa.Column(
            "article_type", sa.String(length=60), server_default="research_article", nullable=False
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_digest", sa.String(length=64), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("provenance", sa.String(length=30), server_default="authored", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_no >= 1", name="ck_pub_version_sequence"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_version_id_manuscript"),
        sa.UniqueConstraint("manuscript_id", "version_no", name="uq_pub_version_sequence"),
    )
    op.create_table(
        "publishing_workflows",
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.String(length=80), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("policy_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("draft_version_id", sa.String(length=36), nullable=True),
        sa.Column("accepted_version_id", sa.String(length=36), nullable=True),
        sa.Column("current_step_id", sa.String(length=36), nullable=True),
        sa.Column("chief_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_editor_id", sa.String(length=36), nullable=True),
        sa.Column("production_editor_id", sa.String(length=36), nullable=True),
        sa.Column("required_reports", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_legacy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('author_draft','precheck_completeness','similarity_review','technical_screening','chief_scope','assign_editor','editor_quality','reviewer_selection','peer_review','editor_recommendation','chief_decision','author_revision','revision_assessment','production','author_proof','preview_confirmation','preview_ready','legacy_screening','rejected')",
            name="ck_pub_workflow_stage",
        ),
        sa.CheckConstraint(
            "required_reports BETWEEN 1 AND 3", name="ck_pub_workflow_report_target"
        ),
        sa.CheckConstraint("revision >= 0", name="ck_pub_workflow_revision"),
        sa.ForeignKeyConstraint(
            ["assigned_editor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["chief_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_workflow_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["production_editor_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("manuscript_id"),
        sa.UniqueConstraint("journal_id", "number", name="uq_pub_workflow_journal_number"),
    )
    op.create_index(
        "ix_pub_workflow_queue",
        "publishing_workflows",
        ["journal_id", "stage", "updated_at"],
        unique=False,
    )
    op.create_table(
        "publishing_form_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("schema_key", sa.String(length=60), server_default="intake", nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column(
            "data_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sources_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_pub_form_revision"),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_form_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "version_id", "schema_key", "owner_id", name="uq_pub_form_version_owner"
        ),
    )
    op.create_table(
        "publishing_step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("step_key", sa.String(length=50), nullable=False),
        sa.Column("cycle_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("policy_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("confirmation_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','completed','cancelled')", name="ck_pub_step_status"
        ),
        sa.CheckConstraint("cycle_no >= 1", name="ck_pub_step_cycle"),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_step_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_step_id_manuscript"),
        sa.UniqueConstraint("manuscript_id", "step_key", "cycle_no", name="uq_pub_step_cycle"),
    )
    op.create_table(
        "publishing_version_authors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("orcid", sa.String(length=32), nullable=True),
        sa.Column(
            "affiliations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("corresponding", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "contributions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("linked_user_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint("ordinal >= 0", name="ck_pub_author_order"),
        sa.ForeignKeyConstraint(
            ["linked_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_author_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_author_id_manuscript"),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_pub_author_order"),
    )
    op.create_index(
        "uq_pub_author_corresponding",
        "publishing_version_authors",
        ["version_id"],
        unique=True,
        postgresql_where=sa.text("corresponding = true"),
    )
    op.create_table(
        "publishing_version_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("file_object_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("visibility", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('manuscript','blinded_manuscript','response','similarity_report','proof')",
            name="ck_pub_version_file_purpose",
        ),
        sa.CheckConstraint(
            "visibility IN ('author_editor','reviewer','production')",
            name="ck_pub_version_file_visibility",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_version_file_object_journal",
        ),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_version_file_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_version_file_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_version_file_id_manuscript"),
        sa.UniqueConstraint("version_id", "purpose", name="uq_pub_version_file_purpose"),
    )
    op.create_table(
        "publishing_work_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("step_run_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("assignee_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blocking", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','waiting','completed','cancelled')",
            name="ck_pub_work_item_status",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_work_item_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id", "manuscript_id"],
            ["publishing_step_runs.id", "publishing_step_runs.manuscript_id"],
            name="fk_pub_work_item_step",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_work_item_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_work_item_id_manuscript"),
        sa.UniqueConstraint(
            "step_run_id", "kind", "assignee_id", name="uq_pub_work_item_step_assignee"
        ),
    )
    op.create_index(
        "ix_pub_work_item_assignee",
        "publishing_work_items",
        ["assignee_id", "status", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_pub_work_item_journal",
        "publishing_work_items",
        ["journal_id", "status", "due_at"],
        unique=False,
    )
    op.create_table(
        "publishing_action_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("work_item_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("prepared_by", sa.String(length=36), nullable=False),
        sa.Column("responsible_user_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("payload_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_digests", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["journal_id"],
            ["journals.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_proposal_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["prepared_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_proposal_version",
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id", "manuscript_id"],
            ["publishing_work_items.id", "publishing_work_items.manuscript_id"],
            name="fk_pub_proposal_work_item",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_proposal_id_manuscript"),
    )
    op.create_index(
        "ix_pub_proposal_responsible",
        "publishing_action_proposals",
        ["responsible_user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "publishing_human_confirmations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("responsible_user_id", sa.String(length=36), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('confirm','return')", name="ck_pub_confirmation_outcome"),
        sa.ForeignKeyConstraint(
            ["manuscript_id"],
            ["manuscripts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id", "manuscript_id"],
            ["publishing_action_proposals.id", "publishing_action_proposals.manuscript_id"],
            name="fk_pub_confirmation_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["responsible_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_confirmation_id_manuscript"),
        sa.UniqueConstraint("proposal_id", name="uq_pub_confirmation_proposal"),
    )
    op.create_foreign_key(
        "fk_pub_workflow_accepted_version",
        "publishing_workflows",
        "publishing_versions",
        ["accepted_version_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_workflow_current_step",
        "publishing_workflows",
        "publishing_step_runs",
        ["current_step_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_workflow_current_version",
        "publishing_workflows",
        "publishing_versions",
        ["current_version_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_workflow_draft_version",
        "publishing_workflows",
        "publishing_versions",
        ["draft_version_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_step_confirmation",
        "publishing_step_runs",
        "publishing_human_confirmations",
        ["confirmation_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_work_item_confirmation",
        "publishing_work_items",
        "publishing_human_confirmations",
        ["confirmation_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    _backfill_legacy()
    _install_guards()


def _legacy_id(kind, source_id):
    return str(uuid5(NAMESPACE_URL, f"publishing-os:legacy-foundation:{kind}:{source_id}"))


def _backfill_legacy():
    """Import existing facts, explicitly leaving unknown publication data missing."""
    bind = op.get_bind()
    metadata = sa.MetaData()
    names = [
        "manuscripts",
        "users",
        "editorial_tasks",
        "audit_events",
        "publishing_versions",
        "publishing_version_authors",
        "publishing_assignments",
        "publishing_step_runs",
        "publishing_work_items",
        "publishing_workflows",
    ]
    tables = {name: sa.Table(name, metadata, autoload_with=bind) for name in names}
    manuscripts, users, tasks, audit = (tables[name] for name in names[:4])
    timestamp = bind.scalar(sa.select(sa.func.now()))
    for row in bind.execute(sa.select(manuscripts).order_by(manuscripts.c.id)).mappings():
        manuscript_id = row["id"]
        if row["workflow_kind"] != "legacy":
            continue
        if bind.scalar(
            sa.select(tables["publishing_workflows"].c.manuscript_id).where(
                tables["publishing_workflows"].c.manuscript_id == manuscript_id
            )
        ):
            continue
        author = (
            bind.execute(sa.select(users).where(users.c.id == row["author_id"])).mappings().one()
        )
        legacy_tasks = list(
            bind.execute(
                sa.select(tasks).where(tasks.c.manuscript_id == manuscript_id).order_by(tasks.c.id)
            ).mappings()
        )
        actor = bind.scalar(
            sa.select(audit.c.actor_id)
            .where(
                audit.c.action == "manuscript.created",
                audit.c.entity_id == manuscript_id,
                audit.c.journal_id == row["journal_id"],
            )
            .order_by(audit.c.created_at, audit.c.id)
            .limit(1)
        )
        snapshot_actor = actor or row["editor_id"] or row["author_id"]
        version_id = _legacy_id("version", manuscript_id)
        step_id = _legacy_id("step", manuscript_id)
        details = {
            "legacy": True,
            "source_table": "manuscripts",
            "source_id": manuscript_id,
            "original_status": row["status"],
            "original_created_at": row["created_at"].isoformat(),
            "snapshot_actor_basis": "creation_audit"
            if actor
            else "legacy_editor_or_owner_attribution",
            "snapshot_actor_is_original_creator_known": bool(actor),
            "authorship_complete": False,
            "corresponding_author_known": False,
            "missing_fields": [
                "abstract",
                "language",
                "article_type",
                "author_order",
                "affiliations",
                "declarations",
                "files",
                "human_confirmations",
            ],
            "not_evidence_of_completed_checks": True,
        }
        digest = hashlib.sha256(
            json.dumps(
                {
                    "title": row["title"],
                    "author": {
                        "id": author["id"],
                        "name": author["name"],
                        "email": author["email"],
                    },
                    "legacy_metadata": details,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        # Empty abstract and explicit unknown language/type are truthful legacy gaps,
        # rather than applying new-intake zh/research defaults to old records.
        bind.execute(
            tables["publishing_versions"]
            .insert()
            .values(
                id=version_id,
                manuscript_id=manuscript_id,
                version_no=1,
                title=row["title"],
                abstract="",
                language="und",
                article_type="",
                metadata_json=details,
                content_digest=digest,
                frozen_at=timestamp,
                created_by=snapshot_actor,
                provenance="legacy",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        bind.execute(
            tables["publishing_version_authors"]
            .insert()
            .values(
                id=_legacy_id("author", manuscript_id),
                manuscript_id=manuscript_id,
                version_id=version_id,
                ordinal=0,
                name=author["name"],
                email=author["email"],
                orcid=None,
                affiliations=[],
                corresponding=False,
                contributions=[],
                linked_user_id=author["id"],
            )
        )
        for capability, user_id in (
            ("author", row["author_id"]),
            ("handling_editor", row["editor_id"]),
        ):
            if user_id:
                bind.execute(
                    tables["publishing_assignments"]
                    .insert()
                    .values(
                        id=_legacy_id(f"assignment-{capability}", manuscript_id),
                        manuscript_id=manuscript_id,
                        journal_id=row["journal_id"],
                        user_id=user_id,
                        capability=capability,
                        assigned_by=None,
                        starts_at=timestamp,
                        ends_at=None,
                        reason=f"Legacy snapshot from manuscripts.{'author_id' if capability == 'author' else 'editor_id'}; original assignment time/assigner unknown",
                    )
                )
        bind.execute(
            tables["publishing_step_runs"]
            .insert()
            .values(
                id=step_id,
                manuscript_id=manuscript_id,
                version_id=version_id,
                step_key="legacy_" + row["status"],
                cycle_no=1,
                status="pending",
                policy_version=1,
                entered_at=timestamp,
                completed_at=None,
                outcome_json={
                    "provenance": "legacy_snapshot",
                    "original_status": row["status"],
                    "original_created_at": row["created_at"].isoformat(),
                    "entered_at_basis": "backfill_time_not_original_stage_time",
                    "legacy_tasks": [
                        {
                            "id": task["id"],
                            "kind": task["kind"],
                            "status": task["status"],
                            "assignee_id": task["assignee_id"],
                        }
                        for task in legacy_tasks
                    ],
                    "no_checks_or_human_confirmations_inferred": True,
                },
                confirmation_id=None,
            )
        )
        for task in legacy_tasks:
            bind.execute(
                tables["publishing_work_items"]
                .insert()
                .values(
                    id=_legacy_id("task", task["id"]),
                    manuscript_id=manuscript_id,
                    journal_id=row["journal_id"],
                    step_run_id=step_id,
                    version_id=version_id,
                    kind=task["kind"],
                    assignee_id=task["assignee_id"],
                    status=task["status"]
                    if task["status"] in {"pending", "waiting", "completed", "cancelled"}
                    else "pending",
                    due_at=None,
                    priority=0,
                    blocking=True,
                    created_at=timestamp,
                    completed_at=None,
                    confirmation_id=None,
                )
            )
        bind.execute(
            tables["publishing_workflows"]
            .insert()
            .values(
                manuscript_id=manuscript_id,
                journal_id=row["journal_id"],
                number="LEGACY-" + manuscript_id,
                stage="legacy_screening",
                revision=0,
                policy_version=1,
                current_version_id=version_id,
                draft_version_id=None,
                accepted_version_id=None,
                current_step_id=step_id,
                chief_id=None,
                assigned_editor_id=row["editor_id"],
                production_editor_id=None,
                required_reports=1,
                is_legacy=True,
                submitted_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )


def _install_guards():
    op.execute("""
      CREATE FUNCTION publishing_reject_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
      END;
      $$;
      CREATE TRIGGER publishing_file_immutable BEFORE UPDATE OR DELETE ON publishing_file_objects
      FOR EACH ROW EXECUTE FUNCTION publishing_reject_immutable();
      CREATE TRIGGER publishing_confirmation_immutable BEFORE UPDATE OR DELETE ON publishing_human_confirmations
      FOR EACH ROW EXECUTE FUNCTION publishing_reject_immutable();

      CREATE FUNCTION publishing_guard_frozen_version() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.frozen_at IS NOT NULL THEN
          RAISE EXCEPTION 'frozen publishing version is immutable';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER publishing_version_frozen BEFORE UPDATE OR DELETE ON publishing_versions
      FOR EACH ROW EXECUTE FUNCTION publishing_guard_frozen_version();

      CREATE FUNCTION publishing_guard_version_child() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE old_version text; new_version text; target record;
      BEGIN
        IF TG_OP <> 'INSERT' THEN old_version := OLD.version_id; END IF;
        IF TG_OP <> 'DELETE' THEN new_version := NEW.version_id; END IF;
        -- SHARE serializes against the parent's freeze UPDATE. Checking without a
        -- row lock would allow a concurrent insert to arrive after the freeze.
        FOR target IN SELECT id, frozen_at FROM publishing_versions
          WHERE id IN (old_version, new_version) ORDER BY id FOR SHARE
        LOOP
          IF target.frozen_at IS NOT NULL THEN
            RAISE EXCEPTION 'children of frozen publishing versions are immutable';
          END IF;
        END LOOP;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER publishing_author_frozen BEFORE INSERT OR UPDATE OR DELETE ON publishing_version_authors
      FOR EACH ROW EXECUTE FUNCTION publishing_guard_version_child();
      CREATE TRIGGER publishing_version_file_frozen BEFORE INSERT OR UPDATE OR DELETE ON publishing_version_files
      FOR EACH ROW EXECUTE FUNCTION publishing_guard_version_child();

      CREATE FUNCTION publishing_guard_proposal() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'publishing proposals are immutable'; END IF;
        IF (to_jsonb(NEW) - 'superseded_at') IS DISTINCT FROM (to_jsonb(OLD) - 'superseded_at') THEN
          RAISE EXCEPTION 'publishing proposal body is immutable';
        END IF;
        IF OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS DISTINCT FROM OLD.superseded_at THEN
          RAISE EXCEPTION 'superseded publishing proposal cannot be reactivated or rewritten';
        END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER publishing_proposal_immutable BEFORE UPDATE OR DELETE ON publishing_action_proposals
      FOR EACH ROW EXECUTE FUNCTION publishing_guard_proposal();

      CREATE FUNCTION publishing_guard_completed_step() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF OLD.status = 'completed' THEN RAISE EXCEPTION 'completed publishing steps are immutable'; END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER publishing_step_completed BEFORE UPDATE OR DELETE ON publishing_step_runs
      FOR EACH ROW EXECUTE FUNCTION publishing_guard_completed_step();
    """)


def downgrade():
    # Never contract a database containing new domain work or uploaded objects.
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM manuscripts WHERE workflow_kind = 'publishing')
           OR EXISTS (SELECT 1 FROM publishing_file_objects)
           OR EXISTS (SELECT 1 FROM publishing_action_proposals)
           OR EXISTS (SELECT 1 FROM publishing_human_confirmations)
           OR EXISTS (SELECT 1 FROM publishing_action_receipts)
           OR EXISTS (SELECT 1 FROM publishing_chat_turns) THEN
          RAISE EXCEPTION 'refusing downgrade: non-legacy publishing data exists';
        END IF;
        IF EXISTS (SELECT 1 FROM manuscripts WHERE length(title) > 240) THEN
          RAISE EXCEPTION 'refusing downgrade: manuscript title exceeds legacy length';
        END IF;
      END $$;
    """)
    op.drop_constraint(
        "fk_pub_workflow_current_version", "publishing_workflows", type_="foreignkey"
    )
    op.drop_constraint("fk_pub_workflow_draft_version", "publishing_workflows", type_="foreignkey")
    op.drop_constraint(
        "fk_pub_workflow_accepted_version", "publishing_workflows", type_="foreignkey"
    )
    op.drop_constraint("fk_pub_workflow_current_step", "publishing_workflows", type_="foreignkey")
    op.drop_constraint("fk_pub_step_confirmation", "publishing_step_runs", type_="foreignkey")
    op.drop_constraint("fk_pub_work_item_confirmation", "publishing_work_items", type_="foreignkey")
    for name in (
        "publishing_human_confirmations",
        "publishing_action_proposals",
        "publishing_work_items",
        "publishing_version_files",
        "publishing_version_authors",
        "publishing_step_runs",
        "publishing_form_drafts",
        "publishing_workflows",
        "publishing_versions",
        "publishing_chat_turns",
        "publishing_assignments",
        "publishing_file_objects",
        "publishing_action_receipts",
    ):
        op.drop_table(name)
    for name in (
        "publishing_guard_completed_step",
        "publishing_guard_proposal",
        "publishing_guard_version_child",
        "publishing_guard_frozen_version",
        "publishing_reject_immutable",
    ):
        op.execute(f"DROP FUNCTION {name}()")
    op.execute("DROP SEQUENCE publishing_submission_number_seq")
    op.drop_constraint("ck_manuscript_workflow_kind", "manuscripts", type_="check")
    op.drop_constraint("uq_manuscript_id_journal", "manuscripts", type_="unique")
    op.alter_column(
        "manuscripts",
        "title",
        existing_type=sa.String(500),
        type_=sa.String(240),
        existing_nullable=False,
    )
    op.alter_column("manuscripts", "editor_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("manuscripts", "workflow_kind")
