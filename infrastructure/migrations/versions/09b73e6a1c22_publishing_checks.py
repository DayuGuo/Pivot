"""Persist human-reviewed checks without modifying frozen submission material.

Revision ID: 09b73e6a1c22
Revises: f8a12d4c6e90
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "09b73e6a1c22"
down_revision = "f8a12d4c6e90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publishing_check_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manuscript_id", sa.String(36), sa.ForeignKey("manuscripts.id"), nullable=False),
        sa.Column("journal_id", sa.String(36), sa.ForeignKey("journals.id"), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("step_run_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("check_method", sa.String(60), nullable=False, server_default="manual_review"),
        sa.Column("file_object_id", sa.String(36), nullable=True),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("prepared_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("human_confirmation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_check_manuscript_journal",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_check_version",
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id", "manuscript_id"],
            ["publishing_step_runs.id", "publishing_step_runs.manuscript_id"],
            name="fk_pub_check_step",
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_check_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_check_file_journal",
        ),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_check_id_manuscript"),
        sa.UniqueConstraint("human_confirmation_id", name="uq_pub_check_confirmation"),
        sa.CheckConstraint(
            "kind IN ('precheck_completeness','similarity_review','technical_screening','chief_scope','editor_quality')",
            name="ck_pub_check_kind",
        ),
        sa.CheckConstraint("outcome IN ('pass','return')", name="ck_pub_check_outcome"),
        sa.CheckConstraint("check_method = 'manual_review'", name="ck_pub_check_method"),
        sa.CheckConstraint("length(btrim(notes)) > 0", name="ck_pub_check_notes"),
        sa.CheckConstraint(
            "outcome <> 'return' OR length(btrim(reason)) > 0", name="ck_pub_check_return_reason"
        ),
        sa.CheckConstraint(
            "(human_confirmation_id IS NULL) = (finalized_at IS NULL)",
            name="ck_pub_check_finalization",
        ),
        sa.CheckConstraint(
            "kind <> 'similarity_review' OR file_object_id IS NOT NULL",
            name="ck_pub_check_similarity_report",
        ),
    )
    op.create_index(
        "uq_pub_check_finalized_step",
        "publishing_check_runs",
        ["step_run_id"],
        unique=True,
        postgresql_where=sa.text("finalized_at IS NOT NULL"),
    )
    op.create_index(
        "ix_pub_check_manuscript_kind",
        "publishing_check_runs",
        ["manuscript_id", "kind", "created_at"],
    )
    op.execute("""
      CREATE FUNCTION publishing_guard_check() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE selected_step record; selected_version record; confirmed record;
      BEGIN
        IF TG_OP = 'TRUNCATE' THEN
          IF EXISTS (SELECT 1 FROM publishing_check_runs WHERE finalized_at IS NOT NULL) THEN
            RAISE EXCEPTION 'finalized publishing checks are immutable';
          END IF;
          RETURN NULL;
        END IF;
        IF TG_OP <> 'INSERT' AND OLD.finalized_at IS NOT NULL THEN
          RAISE EXCEPTION 'finalized publishing checks are immutable';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        SELECT manuscript_id, version_id, step_key INTO selected_step
          FROM publishing_step_runs WHERE id = NEW.step_run_id FOR SHARE;
        IF NOT FOUND OR selected_step.manuscript_id IS DISTINCT FROM NEW.manuscript_id
           OR selected_step.version_id IS DISTINCT FROM NEW.version_id
           OR selected_step.step_key IS DISTINCT FROM NEW.kind THEN
          RAISE EXCEPTION 'check step must match manuscript, version and kind';
        END IF;
        IF NEW.finalized_at IS NOT NULL THEN
          SELECT frozen_at INTO selected_version FROM publishing_versions
            WHERE id = NEW.version_id AND manuscript_id = NEW.manuscript_id FOR SHARE;
          IF NOT FOUND OR selected_version.frozen_at IS NULL THEN
            RAISE EXCEPTION 'finalized checks require a frozen submission version';
          END IF;
          SELECT c.outcome, c.digest, p.digest AS proposal_digest,
                 p.version_id, p.manuscript_id, t.step_run_id,
                 c.responsible_user_id, t.assignee_id,
                 p.responsible_user_id AS proposal_responsible_user_id,
                 p.prepared_by AS proposal_prepared_by
            INTO confirmed
            FROM publishing_human_confirmations c
            JOIN publishing_action_proposals p ON p.id = c.proposal_id
            JOIN publishing_work_items t ON t.id = p.work_item_id
            WHERE c.id = NEW.human_confirmation_id;
          IF NOT FOUND OR confirmed.outcome <> 'confirm'
             OR confirmed.digest IS DISTINCT FROM confirmed.proposal_digest
             OR confirmed.manuscript_id IS DISTINCT FROM NEW.manuscript_id
             OR confirmed.version_id IS DISTINCT FROM NEW.version_id
             OR confirmed.step_run_id IS DISTINCT FROM NEW.step_run_id
             OR confirmed.responsible_user_id IS DISTINCT FROM confirmed.assignee_id
             OR confirmed.responsible_user_id IS DISTINCT FROM confirmed.proposal_responsible_user_id
             OR confirmed.proposal_prepared_by IS DISTINCT FROM NEW.prepared_by THEN
            RAISE EXCEPTION 'check requires a matching responsible human confirmation';
          END IF;
        END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER publishing_check_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_check_runs
        FOR EACH ROW EXECUTE FUNCTION publishing_guard_check();
      CREATE TRIGGER publishing_check_truncate_guard BEFORE TRUNCATE ON publishing_check_runs
        FOR EACH STATEMENT EXECUTE FUNCTION publishing_guard_check();
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM publishing_check_runs) THEN
          RAISE EXCEPTION 'refusing downgrade: publishing check evidence exists';
        END IF;
      END $$;
    """)
    op.drop_table("publishing_check_runs")
    op.execute("DROP FUNCTION publishing_guard_check()")
