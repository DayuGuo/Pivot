"""Internal revision material packets and append-only three-layer human judgements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "28a7c1e09462"
down_revision = "f59230d88725"
branch_labels = None
depends_on = None

GUARDS = r"""
CREATE FUNCTION publishing_dossier_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d publishing_dossiers; b publishing_dossier_versions; v publishing_dossier_versions;
 c publishing_dossier_revision_checks; acting text; prev integer; item jsonb; i integer:=0;
BEGIN
 SELECT * INTO d FROM publishing_dossiers WHERE id=NEW.dossier_id FOR UPDATE;
 IF d.id IS NULL OR d.journal_id IS DISTINCT FROM NEW.journal_id THEN
  RAISE EXCEPTION 'Invalid internal revision tenant' USING ERRCODE='23514';
 END IF;
 IF TG_TABLE_NAME='publishing_dossier_revision_checks' THEN
  acting:=NEW.created_by;
  SELECT * INTO b FROM publishing_dossier_versions WHERE id=NEW.base_version_id;
  SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.revised_version_id;
  IF b.id IS NULL OR v.id IS NULL OR b.dossier_id IS DISTINCT FROM d.id OR v.dossier_id IS DISTINCT FROM d.id
     OR b.journal_id IS DISTINCT FROM d.journal_id OR v.journal_id IS DISTINCT FROM d.journal_id
     OR b.file_object_id IS NULL OR v.file_object_id IS NULL OR b.version_no>=v.version_no
     OR NEW.revision IS DISTINCT FROM d.revision OR v.id IS DISTINCT FROM d.current_version_id
     OR NEW.materials_json->>'base_version_id' IS DISTINCT FROM b.id
     OR NEW.materials_json->>'revised_version_id' IS DISTINCT FROM v.id
     OR NEW.report_json->>'schema' IS DISTINCT FROM 'dossier-revision-comparison.v1'
     OR NEW.report_json->>'dossier_id' IS DISTINCT FROM d.id
     OR NEW.report_json->>'base_version_id' IS DISTINCT FROM b.id
     OR NEW.report_json->>'revised_version_id' IS DISTINCT FROM v.id
     OR NEW.report_json->>'request_id' IS DISTINCT FROM NEW.id
     OR NEW.report_json->>'provider' IS NULL
     OR NEW.report_json->>'provider' NOT IN ('mock','deepseek')
     OR NEW.report_json->'workflow_revision' IS DISTINCT FROM to_jsonb(NEW.revision)
     OR COALESCE(NEW.report_json->>'source_fingerprint' ~ '^[0-9a-f]{64}$',false) IS NOT TRUE THEN
   RAISE EXCEPTION 'Invalid internal revision source' USING ERRCODE='23514';
  END IF;
  IF jsonb_typeof(NEW.materials_json->'requirements') IS DISTINCT FROM 'array'
     OR jsonb_typeof(NEW.report_json->'rows') IS DISTINCT FROM 'array'
     OR jsonb_typeof(NEW.materials_json->'response_text') IS DISTINCT FROM 'string'
     OR length(btrim(NEW.materials_json->>'response_text')) NOT BETWEEN 1 AND 24000
     OR jsonb_typeof(NEW.materials_json->'source_note') IS DISTINCT FROM 'string'
     OR length(btrim(NEW.materials_json->>'source_note')) NOT BETWEEN 5 AND 2000
     OR jsonb_typeof(NEW.materials_json->'base_complete') IS DISTINCT FROM 'boolean'
     OR jsonb_typeof(NEW.materials_json->'revised_complete') IS DISTINCT FROM 'boolean'
     OR jsonb_typeof(NEW.materials_json->'requirements_complete') IS DISTINCT FROM 'boolean'
     OR jsonb_typeof(NEW.materials_json->'response_complete') IS DISTINCT FROM 'boolean' THEN
   RAISE EXCEPTION 'Invalid internal revision material shape' USING ERRCODE='23514';
  END IF;
  IF jsonb_array_length(NEW.materials_json->'requirements') NOT BETWEEN 1 AND 8
     OR jsonb_array_length(NEW.report_json->'rows')<>jsonb_array_length(NEW.materials_json->'requirements') THEN
   RAISE EXCEPTION 'Invalid internal revision coverage' USING ERRCODE='23514';
  END IF;
  FOR item IN SELECT value FROM jsonb_array_elements(NEW.report_json->'rows') LOOP
   IF item->>'point_id' IS DISTINCT FROM ('P0'||(i+1)::text)
      OR item->'point'->'text' IS DISTINCT FROM NEW.materials_json->'requirements'->i->'text'
      OR item->'point'->'original_context' IS DISTINCT FROM NEW.materials_json->'requirements'->i->'original_context'
      OR item->'point'->'complete' IS DISTINCT FROM 'true'::jsonb
      OR COALESCE(item->>'status' IN ('resolved','explained','partial','not_addressed','uncertain','not_applicable'),false) IS NOT TRUE
      OR jsonb_typeof(item->'citations') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Invalid internal revision requirement' USING ERRCODE='23514';
   END IF;
   i:=i+1;
  END LOOP;
 ELSE
  acting:=NEW.reviewed_by;
  SELECT * INTO c FROM publishing_dossier_revision_checks WHERE id=NEW.check_id;
  IF c.id IS NULL OR c.dossier_id IS DISTINCT FROM d.id OR c.journal_id IS DISTINCT FROM d.journal_id
     OR NEW.check_digest IS DISTINCT FROM c.digest
     OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(c.report_json->'rows') r WHERE r->>'point_id'=NEW.point_id) THEN
   RAISE EXCEPTION 'Invalid internal revision judgement source' USING ERRCODE='23514';
  END IF;
  SELECT coalesce(max(review_no),0) INTO prev FROM publishing_dossier_revision_reviews
   WHERE check_id=NEW.check_id AND point_id=NEW.point_id;
  IF NEW.review_no<>prev+1 THEN
   RAISE EXCEPTION 'Invalid internal revision judgement sequence' USING ERRCODE='23514';
  END IF;
 END IF;
 IF acting IS DISTINCT FROM d.created_by
    OR NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=acting AND m.journal_id=d.journal_id AND m.role IN ('editor','chief_editor'))
    OR NOT EXISTS(SELECT 1 FROM login_sessions s WHERE s.token_hash=NEW.session_hash AND s.user_id=acting AND s.expires_at>now()) THEN
  RAISE EXCEPTION 'Invalid internal revision responsible user' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER dossier_revision_insert BEFORE INSERT ON publishing_dossier_revision_checks FOR EACH ROW EXECUTE FUNCTION publishing_dossier_revision_guard();
CREATE TRIGGER dossier_revision_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_revision_checks FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_revision_truncate BEFORE TRUNCATE ON publishing_dossier_revision_checks FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_revision_insert BEFORE INSERT ON publishing_dossier_revision_reviews FOR EACH ROW EXECUTE FUNCTION publishing_dossier_revision_guard();
CREATE TRIGGER dossier_revision_immutable BEFORE UPDATE OR DELETE ON publishing_dossier_revision_reviews FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER dossier_revision_truncate BEFORE TRUNCATE ON publishing_dossier_revision_reviews FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
"""


def upgrade():
    op.create_table(
        "publishing_dossier_revision_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=False),
        sa.Column("revised_version_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("materials_json", postgresql.JSONB(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id", "dossier_id", "journal_id", name="uq_dossier_revision_check_scope"
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_revision_base",
        ),
        sa.ForeignKeyConstraint(
            ["revised_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_revision_revised",
        ),
        sa.CheckConstraint(
            "revision>=2 AND base_version_id<>revised_version_id AND digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_dossier_revision_check_shape",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(materials_json)='object' AND octet_length(materials_json::text)<=262144 AND jsonb_typeof(report_json)='object' AND octet_length(report_json::text)<=262144",
            name="ck_dossier_revision_check_json",
        ),
    )
    op.create_table(
        "publishing_dossier_revision_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("check_id", sa.String(36), nullable=False),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("point_id", sa.String(8), nullable=False),
        sa.Column("check_digest", sa.String(64), nullable=False),
        sa.Column("response_verdict", sa.String(20), nullable=False),
        sa.Column("implementation_verdict", sa.String(20), nullable=False),
        sa.Column("editor_verdict", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("review_no", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["check_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_revision_checks.id",
                "publishing_dossier_revision_checks.dossier_id",
                "publishing_dossier_revision_checks.journal_id",
            ],
            name="fk_dossier_revision_review_check",
        ),
        sa.UniqueConstraint(
            "check_id", "point_id", "review_no", name="uq_dossier_revision_review_no"
        ),
        sa.CheckConstraint(
            "point_id ~ '^P0[1-8]$' AND review_no>=1 AND check_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_dossier_revision_review_shape",
        ),
        sa.CheckConstraint(
            "response_verdict IN ('addressed','not_addressed','uncertain') AND implementation_verdict IN ('changed','partial','unchanged','not_located','uncertain') AND editor_verdict IN ('sufficient','follow_up','needs_judgment') AND length(btrim(reason)) BETWEEN 5 AND 2000",
            name="ck_dossier_revision_review_verdicts",
        ),
    )
    op.execute(GUARDS)


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM publishing_dossier_revision_checks) OR EXISTS(SELECT 1 FROM publishing_dossier_revision_reviews)"
        )
    ):
        raise RuntimeError("Refusing to remove internal revision review history")
    op.drop_table("publishing_dossier_revision_reviews")
    op.drop_table("publishing_dossier_revision_checks")
    op.execute("DROP FUNCTION publishing_dossier_revision_guard()")
