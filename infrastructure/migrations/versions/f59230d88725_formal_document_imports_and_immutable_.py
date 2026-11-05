"""formal document imports and immutable reviewed source bindings

Revision ID: f59230d88725
Revises: 17d51aeb9408
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f59230d88725"
down_revision = "17d51aeb9408"
branch_labels = None
depends_on = None

GUARDS = """
CREATE FUNCTION publishing_formal_document_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE i publishing_formal_document_imports; f publishing_version_files; v publishing_versions; p publishing_formal_document_bindings; pv publishing_versions; w publishing_workflows; owner_id text;
BEGIN
 SELECT author_id INTO owner_id FROM manuscripts WHERE id=NEW.manuscript_id;
 SELECT * INTO v FROM publishing_versions WHERE id=NEW.version_id;
 IF v.id IS NULL OR v.manuscript_id<>NEW.manuscript_id OR v.frozen_at IS NOT NULL THEN RAISE EXCEPTION 'Invalid editable formal document version' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='publishing_formal_document_imports' THEN
  SELECT * INTO w FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id FOR UPDATE;
  IF NEW.created_by IS DISTINCT FROM owner_id OR w.draft_version_id IS DISTINCT FROM NEW.version_id OR w.revision<>NEW.base_revision OR w.stage NOT IN ('author_draft','author_revision') OR jsonb_typeof(NEW.extraction_json->'segments') IS DISTINCT FROM 'array' OR jsonb_typeof(NEW.extraction_json->'text') IS DISTINCT FROM 'string' OR NEW.extraction_json->>'sha256' !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'Invalid formal document proposal' USING ERRCODE='23514'; END IF;
 ELSE
  SELECT * INTO i FROM publishing_formal_document_imports WHERE id=NEW.import_id;
  SELECT * INTO f FROM publishing_version_files WHERE id=NEW.file_id;
  IF f.id IS NULL OR f.manuscript_id IS DISTINCT FROM NEW.manuscript_id OR f.journal_id IS DISTINCT FROM NEW.journal_id OR f.version_id IS DISTINCT FROM NEW.version_id OR f.file_object_id IS DISTINCT FROM NEW.file_object_id OR i.purpose IS DISTINCT FROM f.purpose OR NEW.selection_end>length(i.extraction_json->>'text') OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(i.extraction_json->'segments') s WHERE (s->>'start')::integer=NEW.selection_start) OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(i.extraction_json->'segments') s WHERE (s->>'end')::integer=NEW.selection_end) THEN RAISE EXCEPTION 'Invalid formal document file/scope binding' USING ERRCODE='23514'; END IF;
  IF NOT EXISTS(SELECT 1 FROM publishing_file_objects b WHERE b.id=NEW.file_object_id AND b.sha256=encode(sha256(convert_to(substring(i.extraction_json->>'text' from NEW.selection_start+1 for NEW.selection_end-NEW.selection_start),'UTF8')),'hex') AND b.byte_size=octet_length(convert_to(substring(i.extraction_json->>'text' from NEW.selection_start+1 for NEW.selection_end-NEW.selection_start),'UTF8'))) THEN RAISE EXCEPTION 'Formal extracted bytes do not match source selection' USING ERRCODE='23514'; END IF;
  IF NEW.kind='confirmed' THEN
   SELECT * INTO w FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id FOR UPDATE;
   IF NOT EXISTS(SELECT 1 FROM login_sessions s WHERE s.token_hash=NEW.session_hash AND s.user_id=owner_id AND s.expires_at>CURRENT_TIMESTAMP) OR NEW.confirmed_by IS DISTINCT FROM owner_id OR i.created_by IS DISTINCT FROM owner_id OR i.version_id IS DISTINCT FROM NEW.version_id OR w.draft_version_id IS DISTINCT FROM NEW.version_id OR w.revision<>i.base_revision+1 OR w.stage NOT IN ('author_draft','author_revision') THEN RAISE EXCEPTION 'Invalid formal document human confirmation' USING ERRCODE='23514'; END IF;
  ELSE
   SELECT * INTO p FROM publishing_formal_document_bindings WHERE id=NEW.parent_id;
   SELECT * INTO pv FROM publishing_versions WHERE id=p.version_id;
   IF p.id IS NULL OR p.file_object_id IS DISTINCT FROM NEW.file_object_id OR p.selection_start<>NEW.selection_start OR p.selection_end<>NEW.selection_end OR v.version_no<=pv.version_no OR pv.frozen_at IS NULL OR v.provenance<>'author_revision' THEN RAISE EXCEPTION 'Invalid inherited formal document source' USING ERRCODE='23514'; END IF;
  END IF;
 END IF;
 RETURN NEW;
END $$;
"""


def upgrade():
    op.create_table(
        "publishing_formal_document_imports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=100), nullable=False),
        sa.Column("extraction_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("source_note", sa.String(length=2000), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "base_revision>=0 AND byte_size BETWEEN 1 AND 5242880 AND sha256 ~ '^[0-9a-f]{64}$' AND digest ~ '^[0-9a-f]{64}$'",
            name="ck_formal_import_evidence",
        ),
        sa.CheckConstraint(
            "purpose IN ('manuscript','blinded_manuscript','response')",
            name="ck_formal_import_purpose",
        ),
        sa.CheckConstraint(
            "source_kind IN ('synthetic','public_authorized') AND length(source_note) BETWEEN 5 AND 2000",
            name="ck_formal_import_authorization",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_formal_import_manuscript",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_formal_import_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "manuscript_id", "journal_id", name="uq_formal_import_tenant"),
    )
    op.create_index(
        "ix_formal_import_pending",
        "publishing_formal_document_imports",
        ["journal_id", "manuscript_id", "version_id", "created_at", "id"],
    )
    op.create_table(
        "publishing_formal_document_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("manuscript_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("file_object_id", sa.String(length=36), nullable=False),
        sa.Column("import_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_by", sa.String(length=36), nullable=True),
        sa.Column("session_hash", sa.String(length=64), nullable=True),
        sa.Column("selection_start", sa.Integer(), nullable=False),
        sa.Column("selection_end", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(kind='confirmed' AND parent_id IS NULL AND confirmed_by IS NOT NULL AND session_hash IS NOT NULL) OR (kind='inherited' AND parent_id IS NOT NULL AND confirmed_by IS NULL AND session_hash IS NULL)",
            name="ck_formal_binding_kind",
        ),
        sa.CheckConstraint(
            "selection_start>=0 AND selection_end>selection_start",
            name="ck_formal_binding_selection",
        ),
        sa.CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$' AND (session_hash IS NULL OR session_hash ~ '^[0-9a-f]{64}$')",
            name="ck_formal_binding_digest",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_formal_binding_blob",
        ),
        sa.ForeignKeyConstraint(
            ["import_id", "manuscript_id", "journal_id"],
            [
                "publishing_formal_document_imports.id",
                "publishing_formal_document_imports.manuscript_id",
                "publishing_formal_document_imports.journal_id",
            ],
            name="fk_formal_binding_import",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_formal_binding_manuscript",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "import_id", "manuscript_id", "journal_id"],
            [
                "publishing_formal_document_bindings.id",
                "publishing_formal_document_bindings.import_id",
                "publishing_formal_document_bindings.manuscript_id",
                "publishing_formal_document_bindings.journal_id",
            ],
            name="fk_formal_binding_parent",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_formal_binding_version",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_formal_binding_file"),
        sa.UniqueConstraint(
            "id", "import_id", "manuscript_id", "journal_id", name="uq_formal_binding_identity"
        ),
    )
    op.create_index(
        "uq_formal_import_confirmation",
        "publishing_formal_document_bindings",
        ["import_id"],
        unique=True,
        postgresql_where=sa.text("kind='confirmed'"),
    )
    op.execute(GUARDS)
    op.execute(
        "CREATE TRIGGER formal_document_insert BEFORE INSERT ON publishing_formal_document_imports FOR EACH ROW EXECUTE FUNCTION publishing_formal_document_guard()"
    )
    op.execute(
        "CREATE TRIGGER formal_document_immutable BEFORE UPDATE OR DELETE ON publishing_formal_document_imports FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER formal_document_truncate BEFORE TRUNCATE ON publishing_formal_document_imports FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER formal_document_insert BEFORE INSERT ON publishing_formal_document_bindings FOR EACH ROW EXECUTE FUNCTION publishing_formal_document_guard()"
    )
    op.execute(
        "CREATE TRIGGER formal_document_immutable BEFORE UPDATE OR DELETE ON publishing_formal_document_bindings FOR EACH ROW EXECUTE FUNCTION publishing_dossier_immutable()"
    )
    op.execute(
        "CREATE TRIGGER formal_document_truncate BEFORE TRUNCATE ON publishing_formal_document_bindings FOR EACH STATEMENT EXECUTE FUNCTION publishing_dossier_immutable()"
    )


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM publishing_formal_document_imports) OR EXISTS(SELECT 1 FROM publishing_formal_document_bindings) THEN RAISE EXCEPTION 'Cannot remove formal document evidence'; END IF; END $$"
    )
    op.execute("DROP FUNCTION publishing_formal_document_guard() CASCADE")
    op.drop_index(
        "uq_formal_import_confirmation",
        table_name="publishing_formal_document_bindings",
        postgresql_where=sa.text("kind='confirmed'"),
    )
    op.drop_table("publishing_formal_document_bindings")
    op.drop_index("ix_formal_import_pending", table_name="publishing_formal_document_imports")
    op.drop_table("publishing_formal_document_imports")
