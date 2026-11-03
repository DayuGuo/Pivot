"""Version-bound model evidence does not constitute a human dossier check."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "14a28dbe6175"
down_revision = "13f17cad5064"
branch_labels = None
depends_on = None

GUARDS = r"""
CREATE FUNCTION publishing_dossier_answer_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v publishing_dossier_versions%ROWTYPE; citation jsonb; claim jsonb;
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM publishing_dossier_turns t JOIN publishing_dossiers d ON d.id=t.dossier_id
   JOIN memberships m ON m.user_id=d.created_by AND m.journal_id=d.journal_id
   WHERE t.id=NEW.id AND t.dossier_id=NEW.dossier_id AND t.journal_id=NEW.journal_id
     AND t.version_id=NEW.version_id AND t.user_id=d.created_by
     AND d.current_version_id=NEW.version_id AND m.role IN ('editor','chief_editor')
 ) THEN
   RAISE EXCEPTION 'Invalid dossier answer binding' USING ERRCODE='23514';
 END IF;
 SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
 FOR claim IN SELECT value FROM jsonb_array_elements(NEW.result_json->'claims') LOOP
   IF jsonb_typeof(claim->'citations') IS DISTINCT FROM 'array' OR jsonb_array_length(claim->'citations')<1 THEN
     RAISE EXCEPTION 'Missing dossier answer evidence' USING ERRCODE='23514';
   END IF;
   FOR citation IN SELECT value FROM jsonb_array_elements(claim->'citations') LOOP
     IF citation->>'version_id' IS DISTINCT FROM v.id OR citation->>'content_digest' IS DISTINCT FROM v.content_digest
        OR citation->>'kind' IS NULL OR citation->>'kind' NOT IN ('text','metadata') OR coalesce(length(btrim(citation->>'quote')),0)<1 THEN
       RAISE EXCEPTION 'Invalid dossier answer evidence' USING ERRCODE='23514';
     END IF;
     IF citation->>'kind'='text' AND NOT EXISTS(
       SELECT 1 FROM publishing_file_objects f WHERE f.id=v.file_object_id AND f.journal_id=v.journal_id
       AND f.sha256=citation->>'file_sha256'
     ) THEN
       RAISE EXCEPTION 'Invalid dossier answer file' USING ERRCODE='23514';
     END IF;
   END LOOP;
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER dossier_answer_insert BEFORE INSERT ON publishing_dossier_answers FOR EACH ROW EXECUTE FUNCTION publishing_dossier_answer_guard();
CREATE TRIGGER dossier_answer_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_answers FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_answer_truncate BEFORE TRUNCATE ON publishing_dossier_answers FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
"""


def upgrade():
    op.create_table(
        "publishing_dossier_answers",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["publishing_dossier_turns.id"]),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_answer_version",
        ),
        sa.CheckConstraint(
            "COALESCE(jsonb_typeof(result_json)='object' AND "
            "result_json->>'schema'='dossier_answer.v1' AND "
            "result_json->>'provider' IN ('mock','deepseek') AND "
            "jsonb_typeof(result_json->'claims')='array' AND "
            "jsonb_typeof(result_json->'coverage')='object', false) AND "
            "octet_length(result_json::text)<=131072",
            name="ck_dossier_answer_result",
        ),
    )
    op.execute(GUARDS)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM publishing_dossier_answers)")):
        raise RuntimeError("Refusing to remove grounded dossier answer history")
    op.drop_table("publishing_dossier_answers")
    op.execute("DROP FUNCTION publishing_dossier_answer_guard()")
