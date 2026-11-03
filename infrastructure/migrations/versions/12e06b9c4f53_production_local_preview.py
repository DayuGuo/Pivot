"""Immutable accepted-version proof packages, author responses and private local previews.

Revision ID: 12e06b9c4f53
Revises: 11d95a8b3e42
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "12e06b9c4f53"
down_revision = "11d95a8b3e42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publishing_proof_packages",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("accepted_version_id", sa.String(36), nullable=False),
        sa.Column("acceptance_decision_id", sa.String(36), nullable=False),
        sa.Column("package_no", sa.Integer(), nullable=False),
        sa.Column("file_object_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("material_digest", sa.String(64), nullable=False),
        sa.Column("production_user_id", sa.String(36), nullable=False),
        sa.Column("human_confirmation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.ForeignKeyConstraint(["production_user_id"], ["users.id"], name=None),
        sa.CheckConstraint(
            "package_no>=1 AND length(btrim(display_name)) BETWEEN 1 AND 255",
            name="ck_pub_proof_package_sequence",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_snapshot)='object' AND material_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_proof_package_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["acceptance_decision_id", "manuscript_id"],
            ["publishing_editorial_decisions.id", "publishing_editorial_decisions.manuscript_id"],
            name="fk_pub_proof_package_acceptance",
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_proof_package_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_proof_package_file_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_proof_package_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_proof_package_version",
        ),
        sa.UniqueConstraint("human_confirmation_id", name="uq_pub_proof_package_confirmation"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_proof_package_id_manuscript"),
        sa.UniqueConstraint("manuscript_id", "package_no", name="uq_pub_proof_package_sequence"),
        sa.UniqueConstraint(
            "id", "manuscript_id", "accepted_version_id", name="uq_pub_proof_package_version"
        ),
    )
    op.create_table(
        "publishing_proof_responses",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("package_id", sa.String(36), nullable=False),
        sa.Column("author_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("human_confirmation_id", sa.String(36), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=None),
        sa.CheckConstraint(
            "outcome<>'request_corrections' OR length(btrim(notes))>=20",
            name="ck_pub_proof_response_notes",
        ),
        sa.CheckConstraint(
            "outcome IN ('approve','request_corrections')", name="ck_pub_proof_response_outcome"
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_proof_response_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["package_id", "manuscript_id"],
            ["publishing_proof_packages.id", "publishing_proof_packages.manuscript_id"],
            name="fk_pub_proof_response_package",
        ),
        sa.UniqueConstraint("human_confirmation_id", name="uq_pub_proof_response_confirmation"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_proof_response_id_manuscript"),
        sa.UniqueConstraint("package_id", name="uq_pub_proof_response_once"),
        sa.UniqueConstraint(
            "id", "manuscript_id", "package_id", name="uq_pub_proof_response_package"
        ),
    )
    op.create_table(
        "publishing_publication_previews",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("accepted_version_id", sa.String(36), nullable=False),
        sa.Column("package_id", sa.String(36), nullable=False),
        sa.Column("proof_response_id", sa.String(36), nullable=False),
        sa.Column("metadata_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("file_object_id", sa.String(36), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("production_user_id", sa.String(36), nullable=False),
        sa.Column("human_confirmation_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.ForeignKeyConstraint(["production_user_id"], ["users.id"], name=None),
        sa.CheckConstraint(
            "jsonb_typeof(metadata_snapshot)='object' AND content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_preview_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_preview_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_preview_file_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["package_id", "manuscript_id", "accepted_version_id"],
            [
                "publishing_proof_packages.id",
                "publishing_proof_packages.manuscript_id",
                "publishing_proof_packages.accepted_version_id",
            ],
            name="fk_pub_preview_package_version",
        ),
        sa.ForeignKeyConstraint(
            ["proof_response_id", "manuscript_id", "package_id"],
            [
                "publishing_proof_responses.id",
                "publishing_proof_responses.manuscript_id",
                "publishing_proof_responses.package_id",
            ],
            name="fk_pub_preview_response_package",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_preview_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_preview_version",
        ),
        sa.UniqueConstraint("human_confirmation_id", name="uq_pub_preview_confirmation"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_preview_id_manuscript"),
        sa.UniqueConstraint("package_id", name="uq_pub_preview_package"),
    )
    _install_guards()


def _install_guards():
    op.execute(r"""
    CREATE FUNCTION publishing_production_metadata(version text) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE source record; authors jsonb;
    BEGIN
      SELECT * INTO source FROM publishing_versions WHERE id=version AND frozen_at IS NOT NULL;
      IF NOT FOUND THEN RAISE EXCEPTION 'production metadata requires frozen accepted version'; END IF;
      SELECT coalesce(jsonb_agg(jsonb_build_object('name',name,'orcid',orcid,
          'affiliations',affiliations,'corresponding',corresponding,'contributions',contributions) ORDER BY ordinal),'[]'::jsonb)
        INTO authors FROM publishing_version_authors WHERE version_id=version;
      RETURN jsonb_build_object('schema_version',1,'title',source.title,'abstract',source.abstract,
        'language',source.language,'article_type',source.article_type,
        'keywords',coalesce(source.metadata_json->'keywords','[]'::jsonb),'authors',authors,
        'funding_statement',coalesce(source.metadata_json->'funding_statement','""'::jsonb));
    END $$;

    CREATE FUNCTION publishing_production_file(blob text, journal text, filename text) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE source record;
    BEGIN
      SELECT * INTO source FROM publishing_file_objects WHERE id=blob AND journal_id=journal;
      IF NOT FOUND OR source.check_method<>'utf8_text_safety' OR source.scan_status<>'validated_text'
         OR source.media_type NOT IN ('text/plain','text/markdown') THEN
        RAISE EXCEPTION 'proof requires actual validated same-journal text file object';
      END IF;
      RETURN jsonb_build_object('id',source.id,'filename',filename,'sha256',source.sha256,
        'byte_size',source.byte_size,'media_type',source.media_type);
    END $$;

    CREATE FUNCTION publishing_production_confirmation(conf text, manu text, journal text,
      version text, action text, stage text) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; flow record; step record;
    BEGIN
      proof:=publishing_review_confirmation(conf,manu,journal,version,ARRAY[action],false);
      SELECT w.revision,w.policy_version,w.accepted_version_id,w.current_step_id,w.stage,m.status
        INTO flow FROM publishing_workflows w JOIN manuscripts m ON m.id=w.manuscript_id
        WHERE w.manuscript_id=manu AND w.journal_id=journal FOR SHARE OF w,m;
      SELECT s.*,t.status AS task_status,t.confirmation_id AS task_confirmation,t.version_id AS task_version,t.kind AS task_kind INTO step
        FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
        WHERE t.id=proof->>'work_item_id';
      IF flow.accepted_version_id IS DISTINCT FROM version OR flow.status<>'accepted'
         OR flow.stage IS DISTINCT FROM stage OR flow.revision::text IS DISTINCT FROM proof->>'base_revision'
         OR flow.policy_version::text IS DISTINCT FROM proof->>'policy_version'
         OR proof#>>'{payload,action}' IS DISTINCT FROM action
         OR proof#>>'{payload,stage}' IS DISTINCT FROM stage
         OR proof#>'{payload,version}' IS DISTINCT FROM 'null'::jsonb
         OR step.id IS DISTINCT FROM flow.current_step_id OR step.step_key IS DISTINCT FROM stage
         OR step.task_kind IS DISTINCT FROM stage
         OR step.version_id IS DISTINCT FROM version OR step.task_version IS DISTINCT FROM version OR step.status<>'completed' OR step.task_status<>'completed'
         OR step.confirmation_id IS DISTINCT FROM conf OR step.task_confirmation IS DISTINCT FROM conf THEN
        RAISE EXCEPTION 'production action requires exact current accepted-version task and null private snapshot';
      END IF;
      RETURN proof||jsonb_build_object('step_run_id',step.id,'step_outcome',step.outcome_json);
    END $$;

    CREATE FUNCTION publishing_production_actor(actor text, manu text, journal text) RETURNS boolean LANGUAGE sql AS $$
      SELECT EXISTS(SELECT 1 FROM memberships WHERE user_id=actor AND journal_id=journal AND role='production_editor')
        AND EXISTS(SELECT 1 FROM publishing_assignments WHERE user_id=actor AND manuscript_id=manu
          AND journal_id=journal AND capability='production' AND starts_at<=clock_timestamp()
          AND (ends_at IS NULL OR ends_at>clock_timestamp()))
        AND NOT EXISTS(SELECT 1 FROM manuscripts WHERE id=manu AND author_id=actor)
        AND NOT EXISTS(SELECT 1 FROM publishing_version_authors a JOIN users u ON u.id=actor
          WHERE a.manuscript_id=manu AND (a.linked_user_id=u.id OR lower(a.email)=lower(u.email)));
    $$;

    CREATE FUNCTION publishing_proof_package_snapshot(package text) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE source record;
    BEGIN
      SELECT * INTO source FROM publishing_proof_packages WHERE id=package;
      IF NOT FOUND THEN RAISE EXCEPTION 'proof package snapshot missing'; END IF;
      RETURN jsonb_build_object('id',source.id,'accepted_version_id',source.accepted_version_id,
        'acceptance_decision_id',source.acceptance_decision_id,'package_no',source.package_no,
        'file',publishing_production_file(source.file_object_id,source.journal_id,source.display_name),
        'metadata_snapshot',source.metadata_snapshot,'material_digest',source.material_digest,
        'production_user_id',source.production_user_id);
    END $$;

    CREATE FUNCTION publishing_guard_proof_package() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; expected jsonb; previous record; maximum integer;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'proof packages are immutable'; END IF;
      proof:=publishing_production_confirmation(NEW.human_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,NEW.accepted_version_id,'send_proof','production');
      expected:=proof#>'{payload,proof_package}';
      IF proof->>'actor' IS DISTINCT FROM NEW.production_user_id
         OR NOT publishing_production_actor(NEW.production_user_id,NEW.manuscript_id,NEW.journal_id)
         OR proof#>>'{step_outcome,package_id}' IS DISTINCT FROM NEW.id
         OR proof#>'{payload,input,declarations}' IS DISTINCT FROM '{"metadata_reviewed": true,"proof_reviewed": true}'::jsonb
         OR NOT EXISTS(SELECT 1 FROM publishing_editorial_decisions WHERE id=NEW.acceptance_decision_id
             AND manuscript_id=NEW.manuscript_id AND journal_id=NEW.journal_id
             AND version_id=NEW.accepted_version_id AND decision_code='accept')
         OR NEW.metadata_snapshot IS DISTINCT FROM publishing_production_metadata(NEW.accepted_version_id)
         OR expected IS DISTINCT FROM jsonb_build_object('id',NEW.id,'accepted_version_id',NEW.accepted_version_id,
             'acceptance_decision_id',NEW.acceptance_decision_id,'package_no',NEW.package_no,
             'file',publishing_production_file(NEW.file_object_id,NEW.journal_id,NEW.display_name),
             'metadata_snapshot',NEW.metadata_snapshot,'material_digest',NEW.material_digest,
             'production_user_id',NEW.production_user_id) THEN
        RAISE EXCEPTION 'send proof requires exact approved public metadata file acceptance and production actor';
      END IF;
      PERFORM 1 FROM manuscripts WHERE id=NEW.manuscript_id FOR UPDATE;
      SELECT coalesce(max(package_no),0) INTO maximum FROM publishing_proof_packages WHERE manuscript_id=NEW.manuscript_id;
      IF NEW.package_no<>maximum+1 THEN RAISE EXCEPTION 'proof package number must be next sequence'; END IF;
      IF NEW.package_no=1 THEN
        IF proof#>'{payload,previous_package_id}' IS DISTINCT FROM 'null'::jsonb
           OR proof#>'{step_outcome,previous_package_id}' IS DISTINCT FROM 'null'::jsonb THEN
          RAISE EXCEPTION 'first proof package cannot have a previous package';
        END IF;
      ELSE
        SELECT p.*,b.sha256,r.outcome INTO previous FROM publishing_proof_packages p
          JOIN publishing_file_objects b ON b.id=p.file_object_id JOIN publishing_proof_responses r ON r.package_id=p.id
          WHERE p.id=proof#>>'{payload,previous_package_id}' AND p.manuscript_id=NEW.manuscript_id
            AND p.accepted_version_id=NEW.accepted_version_id AND p.package_no=NEW.package_no-1;
        IF NOT FOUND OR previous.outcome<>'request_corrections'
           OR proof#>>'{step_outcome,previous_package_id}' IS DISTINCT FROM previous.id
           OR previous.sha256 IS NOT DISTINCT FROM (expected#>>'{file,sha256}') THEN
          RAISE EXCEPTION 'new proof must correct the exact preceding returned package with different bytes';
        END IF;
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_proof_response() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE source record; proof jsonb; expected jsonb; owner text;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'proof responses are immutable'; END IF;
      SELECT * INTO source FROM publishing_proof_packages WHERE id=NEW.package_id AND manuscript_id=NEW.manuscript_id;
      IF NOT FOUND THEN RAISE EXCEPTION 'proof response requires same-manuscript package'; END IF;
      proof:=publishing_production_confirmation(NEW.human_confirmation_id,NEW.manuscript_id,
        source.journal_id,source.accepted_version_id,'confirm_proof','author_proof');
      SELECT author_id INTO owner FROM manuscripts WHERE id=NEW.manuscript_id;
      expected:=proof#>'{payload,proof_response}';
      IF NEW.author_id IS DISTINCT FROM owner OR proof->>'actor' IS DISTINCT FROM NEW.author_id
         OR proof#>>'{step_outcome,package_id}' IS DISTINCT FROM NEW.package_id
         OR proof#>'{payload,proof_package}' IS DISTINCT FROM publishing_proof_package_snapshot(NEW.package_id)
         OR expected IS DISTINCT FROM jsonb_build_object('id',NEW.id,'package_id',NEW.package_id,
             'accepted_version_id',source.accepted_version_id,'outcome',NEW.outcome,'notes',NEW.notes,
             'declarations',jsonb_build_object('proof_reviewed',true),'package_digest',source.material_digest) THEN
        RAISE EXCEPTION 'author response must confirm exact active package metadata bytes digest and explicit review';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_publication_preview() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE source record; approval record; proof jsonb; expected jsonb;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'local publication previews are immutable'; END IF;
      SELECT * INTO source FROM publishing_proof_packages WHERE id=NEW.package_id AND manuscript_id=NEW.manuscript_id
        AND journal_id=NEW.journal_id AND accepted_version_id=NEW.accepted_version_id;
      IF NOT FOUND THEN RAISE EXCEPTION 'local preview requires exact package and accepted version'; END IF;
      SELECT * INTO approval FROM publishing_proof_responses WHERE id=NEW.proof_response_id
        AND manuscript_id=NEW.manuscript_id AND package_id=NEW.package_id AND outcome='approve';
      IF NOT FOUND THEN RAISE EXCEPTION 'local preview requires same-package author approval'; END IF;
      proof:=publishing_production_confirmation(NEW.human_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,NEW.accepted_version_id,'prepare_local_preview','preview_confirmation');
      expected:=proof#>'{payload,preview}';
      IF proof->>'actor' IS DISTINCT FROM NEW.production_user_id
         OR NOT publishing_production_actor(NEW.production_user_id,NEW.manuscript_id,NEW.journal_id)
         OR proof#>>'{step_outcome,package_id}' IS DISTINCT FROM NEW.package_id
         OR proof#>'{payload,input,declarations}' IS DISTINCT FROM '{"metadata_reviewed": true,"approved_proof_reviewed": true}'::jsonb
         OR NEW.metadata_snapshot IS DISTINCT FROM source.metadata_snapshot
         OR NEW.file_object_id IS DISTINCT FROM source.file_object_id OR NEW.display_name IS DISTINCT FROM source.display_name
         OR expected IS DISTINCT FROM jsonb_build_object('id',NEW.id,'accepted_version_id',NEW.accepted_version_id,
             'package_id',NEW.package_id,'proof_response_id',NEW.proof_response_id,'metadata_snapshot',NEW.metadata_snapshot,
             'file',publishing_production_file(NEW.file_object_id,NEW.journal_id,NEW.display_name),
             'content_digest',NEW.content_digest,'production_user_id',NEW.production_user_id,'local_only',true) THEN
        RAISE EXCEPTION 'preview must bind exact approved package public metadata file and local-only confirmation';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_production_reject_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'proof and local preview history cannot truncate'; END $$;
    CREATE TRIGGER publishing_proof_package_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_proof_packages FOR EACH ROW EXECUTE FUNCTION publishing_guard_proof_package();
    CREATE TRIGGER publishing_proof_response_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_proof_responses FOR EACH ROW EXECUTE FUNCTION publishing_guard_proof_response();
    CREATE TRIGGER publishing_publication_preview_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_publication_previews FOR EACH ROW EXECUTE FUNCTION publishing_guard_publication_preview();
    CREATE TRIGGER publishing_proof_package_truncate BEFORE TRUNCATE ON publishing_proof_packages FOR EACH STATEMENT EXECUTE FUNCTION publishing_production_reject_truncate();
    CREATE TRIGGER publishing_proof_response_truncate BEFORE TRUNCATE ON publishing_proof_responses FOR EACH STATEMENT EXECUTE FUNCTION publishing_production_reject_truncate();
    CREATE TRIGGER publishing_publication_preview_truncate BEFORE TRUNCATE ON publishing_publication_previews FOR EACH STATEMENT EXECUTE FUNCTION publishing_production_reject_truncate();
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM publishing_proof_packages) OR EXISTS(SELECT 1 FROM publishing_proof_responses)
           OR EXISTS(SELECT 1 FROM publishing_publication_previews) THEN
          RAISE EXCEPTION 'refusing downgrade: proof or local preview history exists';
        END IF;
      END $$;
    """)
    for table in (
        "publishing_publication_previews",
        "publishing_proof_responses",
        "publishing_proof_packages",
    ):
        op.drop_table(table)
    for function in (
        "publishing_guard_publication_preview",
        "publishing_guard_proof_response",
        "publishing_guard_proof_package",
        "publishing_production_reject_truncate",
    ):
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("DROP FUNCTION publishing_proof_package_snapshot(text)")
    op.execute("DROP FUNCTION publishing_production_actor(text,text,text)")
    op.execute("DROP FUNCTION publishing_production_confirmation(text,text,text,text,text,text)")
    op.execute("DROP FUNCTION publishing_production_file(text,text,text)")
    op.execute("DROP FUNCTION publishing_production_metadata(text)")
