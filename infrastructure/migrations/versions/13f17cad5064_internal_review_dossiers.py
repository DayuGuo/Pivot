"""Private internal editorial dossier snapshots, not formal submissions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "13f17cad5064"
down_revision = "12e06b9c4f53"
branch_labels = None
depends_on = None

GUARDS = r"""
CREATE FUNCTION publishing_dossier_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Internal dossier history is immutable' USING ERRCODE='23514';
END $$;
CREATE TRIGGER dossier_version_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_versions FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_check_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_checks FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_turn_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_turns FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_version_truncate BEFORE TRUNCATE ON publishing_dossier_versions FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_check_truncate BEFORE TRUNCATE ON publishing_dossier_checks FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_turn_truncate BEFORE TRUNCATE ON publishing_dossier_turns FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE FUNCTION publishing_dossier_current_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d publishing_dossiers%ROWTYPE; v publishing_dossier_versions%ROWTYPE;
BEGIN
 SELECT * INTO d FROM publishing_dossiers WHERE id=NEW.id;
 SELECT * INTO v FROM publishing_dossier_versions WHERE id=d.current_version_id;
 IF v.id IS NULL OR v.dossier_id<>d.id OR v.journal_id<>d.journal_id OR v.version_no<>d.revision OR v.created_by<>d.created_by THEN
   RAISE EXCEPTION 'Invalid internal dossier current version' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER dossier_current_consistent AFTER INSERT OR UPDATE ON publishing_dossiers DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_dossier_current_guard();
CREATE FUNCTION publishing_dossier_master_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.id<>OLD.id OR NEW.journal_id<>OLD.journal_id OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at OR NEW.revision<>OLD.revision+1 OR NEW.current_version_id=OLD.current_version_id THEN
   RAISE EXCEPTION 'Invalid internal dossier revision' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER dossier_master_update BEFORE UPDATE ON publishing_dossiers FOR EACH ROW EXECUTE FUNCTION publishing_dossier_master_guard();
CREATE FUNCTION publishing_dossier_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d publishing_dossiers%ROWTYPE; v publishing_dossier_versions%ROWTYPE; actor text;
BEGIN
 SELECT * INTO d FROM publishing_dossiers WHERE id=NEW.dossier_id;
 IF d.id IS NULL OR d.journal_id<>NEW.journal_id THEN
   RAISE EXCEPTION 'Invalid internal dossier tenant' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='publishing_dossier_versions' THEN
   actor:=NEW.created_by;
   IF NEW.version_no NOT IN (d.revision,d.revision+1) OR NEW.data_json->>'source_kind' NOT IN ('synthetic','public_authorized') OR jsonb_typeof(NEW.data_json->'authors') IS DISTINCT FROM 'array' THEN
     RAISE EXCEPTION 'Invalid internal dossier snapshot' USING ERRCODE='23514';
   END IF;
 ELSE
   SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
   IF v.id IS NULL OR v.id<>d.current_version_id OR v.dossier_id<>d.id OR v.journal_id<>d.journal_id THEN
     RAISE EXCEPTION 'Invalid internal dossier evidence version' USING ERRCODE='23514';
   END IF;
   IF TG_TABLE_NAME='publishing_dossier_checks' THEN
     actor:=NEW.checked_by;
     IF NEW.content_digest<>v.content_digest OR v.file_object_id IS NULL OR NOT EXISTS(SELECT 1 FROM login_sessions s WHERE s.token_hash=NEW.session_hash AND s.user_id=actor AND s.expires_at>now()) THEN
       RAISE EXCEPTION 'Invalid internal dossier check' USING ERRCODE='23514';
     END IF;
   ELSE
     actor:=NEW.user_id;
   END IF;
 END IF;
 IF actor<>d.created_by OR NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=actor AND m.journal_id=d.journal_id AND m.role IN ('editor','chief_editor')) THEN
   RAISE EXCEPTION 'Invalid internal dossier responsible user' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER dossier_version_insert BEFORE INSERT ON publishing_dossier_versions FOR EACH ROW EXECUTE FUNCTION publishing_dossier_insert_guard();
CREATE TRIGGER dossier_check_insert BEFORE INSERT ON publishing_dossier_checks FOR EACH ROW EXECUTE FUNCTION publishing_dossier_insert_guard();
CREATE TRIGGER dossier_turn_insert BEFORE INSERT ON publishing_dossier_turns FOR EACH ROW EXECUTE FUNCTION publishing_dossier_insert_guard();
"""


def upgrade():
    op.create_table(
        "publishing_dossiers",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("current_version_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.CheckConstraint("revision >= 1", name="ck_dossier_revision"),
        sa.UniqueConstraint("id", "journal_id", name="uq_dossier_tenant"),
    )
    op.create_table(
        "publishing_dossier_versions",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("data_json", postgresql.JSONB(), nullable=False),
        sa.Column("file_object_id", sa.String(36), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_media_type", sa.String(100), nullable=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=None),
        sa.CheckConstraint("version_no >= 1", name="ck_dossier_version_number"),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_dossier_version_file",
        ),
        sa.ForeignKeyConstraint(
            ["dossier_id", "journal_id"],
            ["publishing_dossiers.id", "publishing_dossiers.journal_id"],
            name="fk_dossier_version_parent",
        ),
        sa.UniqueConstraint("dossier_id", "version_no", name="uq_dossier_version_number"),
        sa.UniqueConstraint("id", "dossier_id", "journal_id", name="uq_dossier_version_tenant"),
    )
    op.create_table(
        "publishing_dossier_checks",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("checked_by", sa.String(36), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["checked_by"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_check_version",
        ),
        sa.UniqueConstraint("version_id", name="uq_dossier_checked_version"),
    )
    op.create_table(
        "publishing_dossier_turns",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("question", sa.String(2000), nullable=False),
        sa.Column("answer", sa.String(6000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_turn_version",
        ),
    )
    op.create_foreign_key(
        "fk_dossier_current",
        "publishing_dossiers",
        "publishing_dossier_versions",
        ["current_version_id", "id", "journal_id"],
        ["id", "dossier_id", "journal_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.execute(GUARDS)


def downgrade():
    if op.get_bind().scalar(text("SELECT EXISTS(SELECT 1 FROM publishing_dossiers)")):
        raise RuntimeError("Refusing to remove internal dossier history")
    op.execute("ALTER TABLE publishing_dossiers DROP CONSTRAINT fk_dossier_current")
    for table in (
        "publishing_dossier_turns",
        "publishing_dossier_checks",
        "publishing_dossier_versions",
        "publishing_dossiers",
    ):
        op.drop_table(table)
    for function in (
        "publishing_dossier_insert_guard",
        "publishing_dossier_master_guard",
        "publishing_dossier_current_guard",
        "publishing_dossier_immutable",
    ):
        op.execute(f"DROP FUNCTION {function}()")
