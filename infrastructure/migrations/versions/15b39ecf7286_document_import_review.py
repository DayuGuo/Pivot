"""Private document proposals, exact human approvals and immutable source manifests."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "15b39ecf7286"
down_revision = "14a28dbe6175"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publishing_document_imports",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False),
        sa.Column("extraction_json", postgresql.JSONB(), nullable=False),
        sa.Column("proposed_data", postgresql.JSONB(), nullable=False),
        sa.Column("field_sources", postgresql.JSONB(), nullable=False),
        sa.Column("metadata_provider", sa.String(20), nullable=False),
        sa.Column("metadata_model", sa.String(100), nullable=False),
        sa.Column("telemetry_json", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=None),
        sa.CheckConstraint(
            "media_type IN ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document') AND jsonb_typeof(extraction_json)='object' AND jsonb_typeof(proposed_data)='object' AND jsonb_typeof(field_sources)='array' AND metadata_provider IN ('mock','deepseek')",
            name="ck_document_import_content",
        ),
        sa.CheckConstraint(
            "base_revision>=1 AND byte_size BETWEEN 1 AND 5242880 AND sha256 ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$'",
            name="ck_document_import_shape",
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_import_base",
        ),
        sa.UniqueConstraint("id", "dossier_id", "journal_id", name="uq_document_import_tenant"),
    )
    op.create_table(
        "publishing_document_approvals",
        sa.Column("id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("import_id", sa.String(36), nullable=False),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("reviewed_data", postgresql.JSONB(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("reviewer_id", sa.String(36), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name=None),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(reviewed_data)='object'",
            name="ck_document_approval_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["import_id", "dossier_id", "journal_id"],
            [
                "publishing_document_imports.id",
                "publishing_document_imports.dossier_id",
                "publishing_document_imports.journal_id",
            ],
            name="fk_document_approval_import",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_approval_version",
        ),
        sa.UniqueConstraint(
            "id", "import_id", "dossier_id", "journal_id", name="uq_document_approval_tenant"
        ),
        sa.UniqueConstraint("import_id", name="uq_document_approved_import"),
        sa.UniqueConstraint("version_id", name="uq_document_approved_version"),
    )
    op.create_table(
        "publishing_document_sources",
        sa.Column("version_id", sa.String(36), nullable=False, primary_key=True),
        sa.Column("dossier_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("import_id", sa.String(36), nullable=False),
        sa.Column("approval_id", sa.String(36), nullable=False),
        sa.Column("origin_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("origin_digest ~ '^[0-9a-f]{64}$'", name="ck_document_source_digest"),
        sa.ForeignKeyConstraint(
            ["approval_id", "import_id", "dossier_id", "journal_id"],
            [
                "publishing_document_approvals.id",
                "publishing_document_approvals.import_id",
                "publishing_document_approvals.dossier_id",
                "publishing_document_approvals.journal_id",
            ],
            name="fk_document_source_approval",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_document_source_version",
        ),
    )
    op.execute(GUARDS)


GUARDS = r"""
CREATE FUNCTION publishing_document_insert_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE d publishing_dossiers%ROWTYPE; i publishing_document_imports%ROWTYPE; v publishing_dossier_versions%ROWTYPE; actor text;
BEGIN
 SELECT * INTO d FROM publishing_dossiers WHERE id=NEW.dossier_id;
 IF d.id IS NULL OR d.journal_id<>NEW.journal_id THEN RAISE EXCEPTION 'Invalid document tenant' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='publishing_document_imports' THEN
   actor:=NEW.created_by;
   IF NEW.base_version_id<>d.current_version_id OR NEW.base_revision<>d.revision OR jsonb_typeof(NEW.extraction_json->'segments') IS DISTINCT FROM 'array' OR coalesce(length(NEW.extraction_json->>'text'),0)<1 THEN
     RAISE EXCEPTION 'Invalid document import base' USING ERRCODE='23514';
   END IF;
 ELSIF TG_TABLE_NAME='publishing_document_approvals' THEN
   actor:=NEW.reviewer_id;
   SELECT * INTO i FROM publishing_document_imports WHERE id=NEW.import_id;
   SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
   IF i.id IS NULL OR i.dossier_id<>d.id OR i.journal_id<>d.journal_id OR v.id IS NULL OR v.id<>d.current_version_id OR v.version_no<>i.base_revision+1 OR v.dossier_id<>d.id OR v.journal_id<>d.journal_id OR v.data_json IS DISTINCT FROM NEW.reviewed_data
      OR NOT EXISTS(SELECT 1 FROM publishing_file_objects f WHERE f.id=v.file_object_id AND f.journal_id=d.journal_id AND f.sha256=i.extraction_json->>'sha256')
      OR NOT EXISTS(SELECT 1 FROM login_sessions s WHERE s.token_hash=NEW.session_hash AND s.user_id=actor AND s.expires_at>now()) THEN
      RAISE EXCEPTION 'Invalid document human approval' USING ERRCODE='23514';
   END IF;
 ELSE
   actor:=d.created_by;
   SELECT * INTO i FROM publishing_document_imports WHERE id=NEW.import_id;
   SELECT * INTO v FROM publishing_dossier_versions WHERE id=NEW.version_id;
   IF i.id IS NULL OR i.dossier_id<>d.id OR i.journal_id<>d.journal_id OR v.id IS NULL OR v.id<>d.current_version_id OR v.created_by<>actor
      OR NOT EXISTS(SELECT 1 FROM publishing_document_approvals a WHERE a.id=NEW.approval_id AND a.import_id=i.id AND a.dossier_id=d.id AND a.journal_id=d.journal_id)
      OR NOT EXISTS(SELECT 1 FROM publishing_file_objects f WHERE f.id=v.file_object_id AND f.journal_id=d.journal_id AND f.sha256=i.extraction_json->>'sha256') THEN
      RAISE EXCEPTION 'Invalid document version source' USING ERRCODE='23514';
   END IF;
 END IF;
 IF actor<>d.created_by OR NOT EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=actor AND m.journal_id=d.journal_id AND m.role IN ('editor','chief_editor')) THEN
    RAISE EXCEPTION 'Invalid document responsible user' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER document_import_insert BEFORE INSERT ON publishing_document_imports FOR EACH ROW EXECUTE FUNCTION publishing_document_insert_guard();
CREATE TRIGGER document_approval_insert BEFORE INSERT ON publishing_document_approvals FOR EACH ROW EXECUTE FUNCTION publishing_document_insert_guard();
CREATE TRIGGER document_source_insert BEFORE INSERT ON publishing_document_sources FOR EACH ROW EXECUTE FUNCTION publishing_document_insert_guard();
CREATE TRIGGER document_import_immutable BEFORE UPDATE OR DELETE ON publishing_document_imports FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER document_approval_immutable BEFORE UPDATE OR DELETE ON publishing_document_approvals FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER document_source_immutable BEFORE UPDATE OR DELETE ON publishing_document_sources FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER document_import_truncate BEFORE TRUNCATE ON publishing_document_imports FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER document_approval_truncate BEFORE TRUNCATE ON publishing_document_approvals FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE TRIGGER document_source_truncate BEFORE TRUNCATE ON publishing_document_sources FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable();
CREATE FUNCTION publishing_document_answer_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s publishing_document_sources%ROWTYPE; i publishing_document_imports%ROWTYPE; claim jsonb; citation jsonb;
BEGIN
 SELECT * INTO s FROM publishing_document_sources WHERE version_id=NEW.version_id;
 IF s.version_id IS NOT NULL THEN SELECT * INTO i FROM publishing_document_imports WHERE id=s.import_id; END IF;
 FOR claim IN SELECT value FROM jsonb_array_elements(NEW.result_json->'claims') LOOP
  FOR citation IN SELECT value FROM jsonb_array_elements(claim->'citations') LOOP
   IF (s.version_id IS NOT NULL AND citation->>'kind'='text') OR citation ? 'document' THEN
    IF s.version_id IS NULL OR citation->'document'->>'origin_digest' IS DISTINCT FROM s.origin_digest OR citation->'document'->>'sha256' IS DISTINCT FROM i.sha256 THEN
      RAISE EXCEPTION 'Invalid document answer origin' USING ERRCODE='23514';
    END IF;
   END IF;
  END LOOP;
 END LOOP;
 RETURN NEW;
END $$;
CREATE TRIGGER document_answer_origin BEFORE INSERT ON publishing_dossier_answers FOR EACH ROW EXECUTE FUNCTION publishing_document_answer_guard();
"""


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM publishing_document_imports)")):
        raise RuntimeError("Refusing to remove document import history")
    op.execute("DROP TRIGGER document_answer_origin ON publishing_dossier_answers")
    op.execute("DROP FUNCTION publishing_document_answer_guard()")
    for table in (
        "publishing_document_sources",
        "publishing_document_approvals",
        "publishing_document_imports",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION publishing_document_insert_guard()")
