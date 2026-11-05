"""Registered immutable evaluation packages and responsible-owner confirmed returns."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "17d51aeb9408"
down_revision = "16c40fda8397"
branch_labels = None
depends_on = None
GUARDS = """
CREATE FUNCTION publishing_evaluation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p publishing_evaluation_packages; a publishing_dossier_answers; v publishing_dossier_versions;
 owner_id text; prev integer; entry jsonb; target jsonb; assessment jsonb; answered integer:=0;
BEGIN
 SELECT created_by INTO owner_id FROM publishing_dossiers WHERE id=NEW.dossier_id FOR UPDATE;
 IF TG_TABLE_NAME='publishing_evaluation_packages' THEN
  SELECT * INTO a FROM publishing_dossier_answers WHERE id=NEW.answer_id;
  SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
  IF a.id IS NULL OR v.id IS NULL OR a.dossier_id IS DISTINCT FROM NEW.dossier_id OR a.journal_id IS DISTINCT FROM NEW.journal_id
     OR a.version_id IS DISTINCT FROM NEW.version_id OR NEW.created_by IS DISTINCT FROM owner_id OR NEW.content_digest IS DISTINCT FROM v.content_digest
     OR NEW.packet_json->>'schema' IS DISTINCT FROM 'claim-evaluation-package.v2'
     OR NEW.packet_json->>'package_id' IS DISTINCT FROM NEW.id OR NEW.packet_json->>'evaluator_code' IS DISTINCT FROM NEW.evaluator_code
     OR NEW.packet_json->'source'->>'version_id' IS DISTINCT FROM NEW.version_id OR NEW.packet_json->'source'->>'content_digest' IS DISTINCT FROM NEW.content_digest
     OR jsonb_typeof(NEW.packet_json->'claims') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Invalid issued evaluation source' USING ERRCODE='23514';
  END IF;
  IF (SELECT count(*) FROM publishing_evaluation_packages WHERE answer_id=NEW.answer_id)>=10
     OR jsonb_array_length(NEW.packet_json->'claims') NOT BETWEEN 1 AND 12
     OR jsonb_array_length(NEW.packet_json->'claims')<>jsonb_array_length(a.result_json->'claims')+coalesce(jsonb_array_length(a.result_json->'withheld_claims'),0)
     OR (SELECT count(*) FROM jsonb_object_keys(NEW.claim_map))<>jsonb_array_length(NEW.packet_json->'claims')
     OR (SELECT count(DISTINCT value->>'id') FROM jsonb_array_elements(NEW.packet_json->'claims'))<>jsonb_array_length(NEW.packet_json->'claims') THEN
   RAISE EXCEPTION 'Invalid evaluation package capacity' USING ERRCODE='23514';
  END IF;
  FOR entry IN SELECT value FROM jsonb_array_elements(NEW.packet_json->'claims') LOOP
   target:=NEW.claim_map->(entry->>'id');
   IF target IS NULL OR jsonb_typeof(target->'claim') IS DISTINCT FROM 'object'
      OR COALESCE(target->>'bucket' IN ('claims','withheld_claims'),false) IS NOT TRUE
      OR COALESCE(target->>'index' ~ '^[0-5]$',false) IS NOT TRUE THEN
    RAISE EXCEPTION 'Invalid evaluation mapping' USING ERRCODE='23514';
   END IF;
   IF target->'claim' IS DISTINCT FROM (a.result_json->(target->>'bucket')->((target->>'index')::integer))
      OR entry->'text' IS DISTINCT FROM target->'claim'->'text'
      OR entry->'assessment' IS DISTINCT FROM '{"verdict": null,"note": ""}'::jsonb THEN
    RAISE EXCEPTION 'Invalid evaluation claim target' USING ERRCODE='23514';
   END IF;
  END LOOP;
  IF (SELECT count(DISTINCT (value->>'bucket',value->>'index')) FROM jsonb_each(NEW.claim_map))<>(SELECT count(*) FROM jsonb_object_keys(NEW.claim_map)) THEN
   RAISE EXCEPTION 'Duplicate evaluation target' USING ERRCODE='23514';
  END IF;
 ELSE
  SELECT * INTO p FROM publishing_evaluation_packages WHERE id=NEW.package_id;
  SELECT coalesce(max(return_no),0) INTO prev FROM publishing_evaluation_returns WHERE package_id=NEW.package_id;
  IF p.id IS NULL OR p.dossier_id IS DISTINCT FROM NEW.dossier_id OR p.journal_id IS DISTINCT FROM NEW.journal_id
     OR p.version_id IS DISTINCT FROM NEW.version_id OR p.content_digest IS DISTINCT FROM NEW.content_digest
     OR p.packet_digest IS DISTINCT FROM NEW.packet_digest OR NEW.submitted_by IS DISTINCT FROM owner_id OR NEW.return_no<>prev+1
     OR (SELECT count(*) FROM jsonb_object_keys(NEW.assessments_json))<>(SELECT count(*) FROM jsonb_object_keys(p.claim_map)) THEN
   RAISE EXCEPTION 'Invalid evaluation return source' USING ERRCODE='23514';
  END IF;
  FOR entry IN SELECT to_jsonb(e) FROM jsonb_each(NEW.assessments_json) e LOOP
   assessment:=entry->'value';
   IF NOT(p.claim_map ? (entry->>'key')) OR jsonb_typeof(assessment) IS DISTINCT FROM 'object'
      OR (SELECT count(*) FROM jsonb_object_keys(assessment))<>2 OR NOT(assessment ?& ARRAY['verdict','note'])
      OR jsonb_typeof(assessment->'note') IS DISTINCT FROM 'string' THEN
    RAISE EXCEPTION 'Invalid evaluation assessment' USING ERRCODE='23514';
   END IF;
   IF assessment->'verdict'='null'::jsonb THEN
    IF assessment->>'note'<>'' THEN RAISE EXCEPTION 'Unanswered assessment has note' USING ERRCODE='23514'; END IF;
   ELSIF COALESCE(assessment->>'verdict' IN ('supported','unsupported','uncertain') AND length(btrim(assessment->>'note')) BETWEEN 5 AND 2000,false) THEN
    answered:=answered+1;
   ELSE RAISE EXCEPTION 'Invalid evaluation verdict' USING ERRCODE='23514'; END IF;
  END LOOP;
  IF answered=0 THEN RAISE EXCEPTION 'Empty evaluation return' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
"""


def upgrade():
    op.create_table(
        "publishing_evaluation_packages",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column(
            "answer_id",
            sa.String(36),
            sa.ForeignKey("publishing_dossier_answers.id"),
            nullable=False,
        ),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("evaluator_code", sa.String(40), nullable=False),
        sa.Column("packet_json", postgresql.JSONB(), nullable=False),
        sa.Column("claim_map", postgresql.JSONB(), nullable=False),
        sa.Column("packet_digest", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_evaluation_package_version",
        ),
        sa.UniqueConstraint("answer_id", "evaluator_code", name="uq_evaluation_package_slot"),
        sa.UniqueConstraint(
            "id", "dossier_id", "journal_id", "version_id", name="uq_evaluation_package_scope"
        ),
        sa.CheckConstraint(
            "evaluator_code ~ '^[a-z0-9][a-z0-9_-]{0,39}$'", name="ck_evaluation_package_code"
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND packet_digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_evaluation_package_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(packet_json)='object' AND octet_length(packet_json::text)<=2097152 AND jsonb_typeof(claim_map)='object' AND octet_length(claim_map::text)<=262144",
            name="ck_evaluation_package_json",
        ),
    )
    op.create_table(
        "publishing_evaluation_returns",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("package_id", sa.String(36), nullable=False),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("packet_digest", sa.String(64), nullable=False),
        sa.Column("assessments_json", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("return_no", sa.Integer, nullable=False),
        sa.Column("submitted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id", "dossier_id", "journal_id", "version_id"],
            [
                "publishing_evaluation_packages.id",
                "publishing_evaluation_packages.dossier_id",
                "publishing_evaluation_packages.journal_id",
                "publishing_evaluation_packages.version_id",
            ],
            name="fk_evaluation_return_package",
        ),
        sa.UniqueConstraint("package_id", "return_no", name="uq_evaluation_return_sequence"),
        sa.CheckConstraint("return_no>=1", name="ck_evaluation_return_sequence"),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND packet_digest ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$' AND session_hash ~ '^[0-9a-f]{64}$'",
            name="ck_evaluation_return_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(assessments_json)='object' AND octet_length(assessments_json::text)<=131072",
            name="ck_evaluation_return_json",
        ),
    )
    op.execute(GUARDS)
    op.execute(
        "CREATE TRIGGER evaluation_insert BEFORE INSERT ON publishing_evaluation_packages FOR EACH ROW EXECUTE FUNCTION publishing_evaluation_guard()"
    )
    op.execute(
        "CREATE TRIGGER evaluation_immutable BEFORE UPDATE OR DELETE ON publishing_evaluation_packages FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER evaluation_truncate BEFORE TRUNCATE ON publishing_evaluation_packages FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER evaluation_insert BEFORE INSERT ON publishing_evaluation_returns FOR EACH ROW EXECUTE FUNCTION publishing_evaluation_guard()"
    )
    op.execute(
        "CREATE TRIGGER evaluation_immutable BEFORE UPDATE OR DELETE ON publishing_evaluation_returns FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER evaluation_truncate BEFORE TRUNCATE ON publishing_evaluation_returns FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable()"
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM publishing_evaluation_packages) OR EXISTS(SELECT 1 FROM publishing_evaluation_returns)"
        )
    ):
        raise RuntimeError("Refusing to remove independent evaluation history")
    op.drop_table("publishing_evaluation_returns")
    op.drop_table("publishing_evaluation_packages")
    op.execute("DROP FUNCTION publishing_evaluation_guard()")
