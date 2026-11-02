"""Append-only audit and immutable email approval snapshots.

Revision ID: 0002_audit_guards
Revises: 3984270ae78e
"""

from alembic import op

revision = "0002_audit_guards"
down_revision = "3984270ae78e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION prevent_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'audit_events is append-only'; END;
      $$;
      CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events
      FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
      CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_events
      FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_mutation();
      CREATE FUNCTION prevent_approval_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'approval snapshots are immutable'; END IF;
        IF NEW.snapshot::jsonb IS DISTINCT FROM OLD.snapshot::jsonb OR NEW.digest <> OLD.digest
           OR NEW.approver_id <> OLD.approver_id OR NEW.draft_id <> OLD.draft_id THEN
          RAISE EXCEPTION 'approval snapshots are immutable';
        END IF;
        IF NOT OLD.valid AND NEW.valid THEN RAISE EXCEPTION 'approval cannot be reactivated'; END IF;
        RETURN NEW;
      END;
      $$;
      CREATE TRIGGER approval_immutable BEFORE UPDATE OR DELETE ON email_approvals
      FOR EACH ROW EXECUTE FUNCTION prevent_approval_snapshot_mutation();
    """)


def downgrade():
    op.execute("""
      DROP TRIGGER approval_immutable ON email_approvals;
      DROP FUNCTION prevent_approval_snapshot_mutation();
      DROP TRIGGER audit_no_truncate ON audit_events;
      DROP TRIGGER audit_no_mutation ON audit_events;
      DROP FUNCTION prevent_audit_mutation();
    """)
