"""Fixed in-app review rounds, invitations, reports and typed reviewer tasks.

Revision ID: 10c84f7a2d31
Revises: 09b73e6a1c22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "10c84f7a2d31"
down_revision = "09b73e6a1c22"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_pub_version_file_id_manuscript_version",
        "publishing_version_files",
        ["id", "manuscript_id", "version_id"],
    )
    op.create_table(
        "publishing_review_rounds",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="initializing"),
        sa.Column("material_sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("required_reports", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "review_method", sa.String(30), nullable=False, server_default="double_anonymous"
        ),
        sa.Column("form_key", sa.String(60), nullable=False, server_default="basic_peer_review"),
        sa.Column("form_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("form_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("form_digest", sa.String(64), nullable=False),
        sa.Column("material_digest", sa.String(64), nullable=False),
        sa.Column("opened_by", sa.String(36), nullable=False),
        sa.Column("opening_confirmation_id", sa.String(36), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closure_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("closing_confirmation_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(
            ["closing_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_round_closing_confirmation",
        ),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.ForeignKeyConstraint(["opened_by"], ["users.id"], name=None),
        sa.CheckConstraint(
            "form_digest ~ '^[0-9a-f]{64}$' AND material_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_review_round_digests",
        ),
        sa.CheckConstraint(
            "review_method = 'double_anonymous' AND form_key = 'basic_peer_review' AND form_version = 1",
            name="ck_pub_review_round_form",
        ),
        sa.CheckConstraint(
            "(status='initializing' AND material_sealed_at IS NULL AND closed_at IS NULL) OR (status='open' AND material_sealed_at IS NOT NULL AND closed_at IS NULL) OR (status IN ('closed','cancelled') AND material_sealed_at IS NOT NULL AND closed_at IS NOT NULL AND closing_confirmation_id IS NOT NULL AND length(btrim(closure_reason))>0)",
            name="ck_pub_review_round_lifecycle",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(form_snapshot) = 'object'", name="ck_pub_review_round_schema"
        ),
        sa.CheckConstraint(
            "round_no >= 1 AND policy_version >= 1", name="ck_pub_review_round_sequence"
        ),
        sa.CheckConstraint(
            "status IN ('initializing','open','closed','cancelled')",
            name="ck_pub_review_round_status",
        ),
        sa.CheckConstraint("required_reports BETWEEN 1 AND 3", name="ck_pub_review_round_target"),
        sa.ForeignKeyConstraint(
            ["opening_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_round_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_review_round_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_review_round_version",
        ),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_review_round_id_manuscript"),
        sa.UniqueConstraint("manuscript_id", "round_no", name="uq_pub_review_round_sequence"),
        sa.UniqueConstraint(
            "id", "manuscript_id", "version_id", name="uq_pub_review_round_version"
        ),
    )
    op.create_index(
        "uq_pub_review_round_open",
        "publishing_review_rounds",
        ["manuscript_id"],
        unique=True,
        postgresql_where=sa.text("status='open'"),
    )
    op.create_table(
        "publishing_review_round_files",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("round_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("version_file_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="blinded_manuscript"),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint(
            "display_name IN ('review-manuscript.txt','review-manuscript.md')",
            name="ck_pub_review_round_file_name",
        ),
        sa.CheckConstraint("role='blinded_manuscript'", name="ck_pub_review_round_file_role"),
        sa.ForeignKeyConstraint(
            ["round_id", "manuscript_id", "version_id"],
            [
                "publishing_review_rounds.id",
                "publishing_review_rounds.manuscript_id",
                "publishing_review_rounds.version_id",
            ],
            name="fk_pub_review_round_file_round",
        ),
        sa.ForeignKeyConstraint(
            ["version_file_id", "manuscript_id", "version_id"],
            [
                "publishing_version_files.id",
                "publishing_version_files.manuscript_id",
                "publishing_version_files.version_id",
            ],
            name="fk_pub_review_round_file_version_file",
        ),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_review_round_file_id_manuscript"),
        sa.UniqueConstraint("round_id", "version_file_id", name="uq_pub_review_round_file_link"),
    )
    op.create_table(
        "publishing_review_invitations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("round_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("reviewer_id", sa.String(36), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", sa.String(36), nullable=False),
        sa.Column("invitation_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_status", sa.String(20), nullable=False, server_default="unanswered"),
        sa.Column("response_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("invitation_confirmation_id", sa.String(36), nullable=False),
        sa.Column("response_confirmation_id", sa.String(36), nullable=True),
        sa.Column("terminal_confirmation_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint(
            "attempt_no >= 1 AND policy_version >= 1", name="ck_pub_review_invitation_attempt"
        ),
        sa.CheckConstraint(
            "conflict_status IN ('unanswered','none','declared')",
            name="ck_pub_review_invitation_conflict",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(invitation_snapshot)='object'",
            name="ck_pub_review_invitation_content",
        ),
        sa.CheckConstraint(
            "report_due_at > response_due_at AND response_due_at > invited_at",
            name="ck_pub_review_invitation_deadlines",
        ),
        sa.CheckConstraint(
            "(status='pending' AND responded_at IS NULL AND accepted_at IS NULL AND declined_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND conflict_status='unanswered' AND response_confirmation_id IS NULL AND terminal_confirmation_id IS NULL) OR (status IN ('accepted','submitted') AND responded_at IS NOT NULL AND accepted_at IS NOT NULL AND declined_at IS NULL AND cancelled_at IS NULL AND conflict_status='none' AND response_confirmation_id IS NOT NULL AND ((status='accepted' AND completed_at IS NULL) OR (status='submitted' AND completed_at IS NOT NULL))) OR (status='declined' AND responded_at IS NOT NULL AND declined_at IS NOT NULL AND accepted_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND response_confirmation_id IS NOT NULL) OR (status='cancelled' AND cancelled_at IS NOT NULL AND completed_at IS NULL AND terminal_confirmation_id IS NOT NULL) OR (status='expired' AND responded_at IS NULL AND accepted_at IS NULL AND declined_at IS NULL AND cancelled_at IS NULL AND completed_at IS NULL AND response_confirmation_id IS NULL AND terminal_confirmation_id IS NULL)",
            name="ck_pub_review_invitation_lifecycle",
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','cancelled','expired','submitted')",
            name="ck_pub_review_invitation_status",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_invitation_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["response_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_invitation_response",
        ),
        sa.ForeignKeyConstraint(
            ["round_id", "manuscript_id", "version_id"],
            [
                "publishing_review_rounds.id",
                "publishing_review_rounds.manuscript_id",
                "publishing_review_rounds.version_id",
            ],
            name="fk_pub_review_invitation_round",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_review_invitation_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["terminal_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_invitation_terminal",
        ),
        sa.UniqueConstraint(
            "round_id", "reviewer_id", "attempt_no", name="uq_pub_review_invitation_attempt"
        ),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_review_invitation_id_manuscript"),
        sa.UniqueConstraint(
            "id",
            "manuscript_id",
            "version_id",
            "reviewer_id",
            name="uq_pub_review_invitation_target",
        ),
    )
    op.create_index(
        "ix_pub_review_invitation_reviewer",
        "publishing_review_invitations",
        ["reviewer_id", "status", "response_due_at"],
        unique=False,
    )
    op.create_index(
        "uq_pub_review_invitation_effective",
        "publishing_review_invitations",
        ["round_id", "reviewer_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','accepted','submitted')"),
    )
    op.create_table(
        "publishing_review_reports",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("invitation_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("form_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("form_digest", sa.String(64), nullable=False),
        sa.Column("author_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("editor_private_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "answers_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("recommendation", sa.String(30), nullable=False, server_default="unanswered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_confirmation_id", sa.String(36), nullable=True),
        sa.Column("content_digest", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint(
            "recommendation IN ('unanswered','accept','minor_revision','major_revision','reject')",
            name="ck_pub_review_report_recommendation",
        ),
        sa.CheckConstraint(
            "form_digest ~ '^[0-9a-f]{64}$' AND jsonb_typeof(form_snapshot)='object' AND jsonb_typeof(answers_json)='object'",
            name="ck_pub_review_report_schema",
        ),
        sa.CheckConstraint(
            "status IN ('draft','submitted','withdrawn') AND revision >= 0",
            name="ck_pub_review_report_status",
        ),
        sa.CheckConstraint(
            "(status='submitted' AND submitted_at IS NOT NULL AND human_confirmation_id IS NOT NULL AND content_digest IS NOT NULL AND content_digest ~ '^[0-9a-f]{64}$' AND recommendation <> 'unanswered') OR (status IN ('draft','withdrawn') AND submitted_at IS NULL AND human_confirmation_id IS NULL AND content_digest IS NULL)",
            name="ck_pub_review_report_submission",
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_review_report_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id", "manuscript_id"],
            ["publishing_review_invitations.id", "publishing_review_invitations.manuscript_id"],
            name="fk_pub_review_report_invitation",
        ),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_review_report_id_manuscript"),
        sa.UniqueConstraint("invitation_id", name="uq_pub_review_report_invitation"),
    )
    _extend_foundation()
    _install_guards()


def _extend_foundation():
    op.add_column(
        "publishing_assignments", sa.Column("review_invitation_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_pub_assignment_review_invitation",
        "publishing_assignments",
        "publishing_review_invitations",
        ["review_invitation_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.drop_constraint("ck_pub_assignment_capability", "publishing_assignments", type_="check")
    op.create_check_constraint(
        "ck_pub_assignment_capability",
        "publishing_assignments",
        "capability IN ('author','precheck','handling_editor','chief','production','reviewer')",
    )
    op.create_check_constraint(
        "ck_pub_assignment_review_target",
        "publishing_assignments",
        "(capability='reviewer') = (review_invitation_id IS NOT NULL)",
    )
    op.drop_index("uq_pub_assignment_active_capability", table_name="publishing_assignments")
    op.create_index(
        "uq_pub_assignment_active_capability",
        "publishing_assignments",
        ["manuscript_id", "user_id", "capability"],
        unique=True,
        postgresql_where=sa.text("ends_at IS NULL AND capability <> 'reviewer'"),
    )
    op.create_index(
        "uq_pub_assignment_active_reviewer",
        "publishing_assignments",
        ["review_invitation_id", "user_id", "capability"],
        unique=True,
        postgresql_where=sa.text("ends_at IS NULL AND capability='reviewer'"),
    )
    op.add_column(
        "publishing_work_items", sa.Column("review_invitation_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "publishing_work_items", sa.Column("review_report_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_pub_work_item_review_invitation",
        "publishing_work_items",
        "publishing_review_invitations",
        ["review_invitation_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_foreign_key(
        "fk_pub_work_item_review_report",
        "publishing_work_items",
        "publishing_review_reports",
        ["review_report_id", "manuscript_id"],
        ["id", "manuscript_id"],
        use_alter=True,
    )
    op.create_check_constraint(
        "ck_pub_work_item_review_target",
        "publishing_work_items",
        "review_invitation_id IS NULL OR review_report_id IS NULL",
    )
    op.drop_constraint("uq_pub_work_item_step_assignee", "publishing_work_items", type_="unique")
    op.create_index(
        "uq_pub_work_item_step_assignee",
        "publishing_work_items",
        ["step_run_id", "kind", "assignee_id"],
        unique=True,
        postgresql_where=sa.text("review_invitation_id IS NULL AND review_report_id IS NULL"),
    )
    op.create_index(
        "uq_pub_work_item_review_invitation",
        "publishing_work_items",
        ["review_invitation_id", "kind", "assignee_id"],
        unique=True,
        postgresql_where=sa.text("review_invitation_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pub_work_item_review_report",
        "publishing_work_items",
        ["review_report_id", "kind", "assignee_id"],
        unique=True,
        postgresql_where=sa.text("review_report_id IS NOT NULL"),
    )


def _install_guards():
    op.execute(r"""
    CREATE FUNCTION publishing_review_confirmation(conf text, manu text, journal text,
      version text, actions text[], fresh boolean DEFAULT true) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE answer record; flow record;
    BEGIN
      SELECT c.responsible_user_id AS actor, p.prepared_by, p.payload_snapshot AS payload,
             p.work_item_id, p.action_type, p.policy_version, p.base_revision
        INTO answer FROM publishing_human_confirmations c
        JOIN publishing_action_proposals p ON p.id=c.proposal_id
        JOIN publishing_work_items t ON t.id=p.work_item_id
        WHERE c.id=conf AND c.manuscript_id=manu AND p.manuscript_id=manu
          AND p.journal_id=journal AND p.version_id=version
          AND t.manuscript_id=manu AND t.journal_id=journal
          AND c.outcome='confirm' AND c.digest=p.digest
          AND c.responsible_user_id=p.responsible_user_id
          AND c.responsible_user_id=t.assignee_id AND p.action_type=ANY(actions)
          AND p.superseded_at IS NULL AND c.confirmed_at < p.expires_at;
      IF NOT FOUND THEN RAISE EXCEPTION 'review requires exact responsible human confirmation'; END IF;
      IF fresh THEN
        SELECT revision, policy_version, current_version_id INTO flow
          FROM publishing_workflows WHERE manuscript_id=manu AND journal_id=journal FOR SHARE;
        IF NOT FOUND OR flow.revision IS DISTINCT FROM answer.base_revision
           OR flow.policy_version IS DISTINCT FROM answer.policy_version
           OR flow.current_version_id IS DISTINCT FROM version THEN
          RAISE EXCEPTION 'stale review confirmation version or policy';
        END IF;
      END IF;
      RETURN to_jsonb(answer);
    END $$;

    CREATE FUNCTION publishing_review_handling(actor text, manu text, journal text) RETURNS boolean
    LANGUAGE sql AS $$
      SELECT EXISTS (SELECT 1 FROM publishing_assignments a
        WHERE a.user_id=actor AND a.manuscript_id=manu AND a.journal_id=journal
          AND a.capability='handling_editor' AND a.starts_at<=clock_timestamp()
          AND (a.ends_at IS NULL OR a.ends_at>clock_timestamp()))
        AND NOT EXISTS (SELECT 1 FROM manuscripts m WHERE m.id=manu AND m.author_id=actor)
        AND NOT EXISTS (SELECT 1 FROM publishing_version_authors a
          JOIN publishing_workflows w ON w.current_version_id=a.version_id
          WHERE w.manuscript_id=manu AND a.linked_user_id=actor);
    $$;

    CREATE FUNCTION publishing_review_report_ids(target text) RETURNS jsonb LANGUAGE sql AS $$
      SELECT coalesce(jsonb_agg(r.id ORDER BY r.id),'[]'::jsonb)
        FROM publishing_review_reports r JOIN publishing_review_invitations i ON i.id=r.invitation_id
        WHERE i.round_id=target AND r.status='submitted';
    $$;

    CREATE FUNCTION publishing_review_material(target text) RETURNS jsonb LANGUAGE sql AS $$
      SELECT coalesce(jsonb_agg(jsonb_build_object('version_file_id',f.version_file_id,
        'sha256',b.sha256,'role',f.role,'display_name',f.display_name) ORDER BY f.version_file_id),'[]'::jsonb)
      FROM publishing_review_round_files f JOIN publishing_version_files v ON v.id=f.version_file_id
      JOIN publishing_file_objects b ON b.id=v.file_object_id WHERE f.round_id=target;
    $$;

    CREATE FUNCTION publishing_review_sorted_ids(items jsonb) RETURNS jsonb LANGUAGE sql AS $$
      SELECT coalesce(jsonb_agg(value ORDER BY value),'[]'::jsonb) FROM jsonb_array_elements(items);
    $$;

    CREATE FUNCTION publishing_guard_review_round() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; expected jsonb; actual jsonb; submitted jsonb; cancelled jsonb;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'review round history is immutable'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'initializing' OR NEW.material_sealed_at IS NOT NULL
           OR NEW.closed_at IS NOT NULL OR NEW.closing_confirmation_id IS NOT NULL
           OR NEW.closure_reason<>'' THEN RAISE EXCEPTION 'review round must atomically initialize'; END IF;
        PERFORM 1 FROM publishing_versions WHERE id=NEW.version_id AND manuscript_id=NEW.manuscript_id
          AND frozen_at IS NOT NULL FOR SHARE;
        IF NOT FOUND THEN RAISE EXCEPTION 'review round requires frozen version'; END IF;
        proof:=publishing_review_confirmation(NEW.opening_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['open_review']);
        expected:=proof#>'{payload,review}';
        IF proof->>'actor' IS DISTINCT FROM NEW.opened_by
           OR NOT publishing_review_handling(NEW.opened_by,NEW.manuscript_id,NEW.journal_id)
           OR proof->>'policy_version' IS DISTINCT FROM NEW.policy_version::text
           OR expected->>'round_id' IS DISTINCT FROM NEW.id
           OR expected->>'round_no' IS DISTINCT FROM NEW.round_no::text
           OR expected->>'version_id' IS DISTINCT FROM NEW.version_id
           OR expected->>'required_reports' IS DISTINCT FROM NEW.required_reports::text
           OR expected->'form_snapshot' IS DISTINCT FROM NEW.form_snapshot
           OR expected->>'form_digest' IS DISTINCT FROM NEW.form_digest
           OR expected->>'material_digest' IS DISTINCT FROM NEW.material_digest
           OR jsonb_typeof(expected->'files') IS DISTINCT FROM 'array'
           OR jsonb_typeof(expected->'invitations') IS DISTINCT FROM 'array'
           OR jsonb_array_length(expected->'files')<>1
           OR NOT EXISTS (SELECT 1 FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id AND stage='reviewer_selection') THEN
          RAISE EXCEPTION 'review opening facts do not match confirmed snapshot';
        END IF;
        RETURN NEW;
      END IF;
      IF OLD.status IN ('closed','cancelled') THEN RAISE EXCEPTION 'closed review round is immutable'; END IF;
      IF (to_jsonb(NEW)-ARRAY['status','material_sealed_at','closed_at','closure_reason','closing_confirmation_id'])
         IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','material_sealed_at','closed_at','closure_reason','closing_confirmation_id']) THEN
        RAISE EXCEPTION 'review material form and policy are immutable';
      END IF;
      IF OLD.status='initializing' AND NEW.status='open' THEN
        IF NEW.material_sealed_at IS NULL OR NEW.closed_at IS NOT NULL OR NEW.closure_reason<>''
           OR NEW.closing_confirmation_id IS NOT NULL THEN RAISE EXCEPTION 'invalid round seal'; END IF;
        proof:=publishing_review_confirmation(NEW.opening_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['open_review']);
        SELECT coalesce(jsonb_agg(jsonb_build_object('version_file_id',f.version_file_id,
          'sha256',b.sha256,'role',f.role,'display_name',f.display_name) ORDER BY f.version_file_id),'[]'::jsonb)
          INTO actual FROM publishing_review_round_files f
          JOIN publishing_version_files v ON v.id=f.version_file_id
          JOIN publishing_file_objects b ON b.id=v.file_object_id WHERE f.round_id=NEW.id;
        SELECT coalesce(jsonb_agg(value ORDER BY value->>'version_file_id'),'[]'::jsonb) INTO expected
          FROM jsonb_array_elements(proof#>'{payload,review,files}');
        IF actual IS DISTINCT FROM expected OR jsonb_array_length(actual)<>1 THEN
          RAISE EXCEPTION 'sealed round files do not match confirmed fixed material';
        END IF;
      ELSIF OLD.status='open' AND NEW.status='closed' THEN
        IF NEW.material_sealed_at IS DISTINCT FROM OLD.material_sealed_at OR NEW.closed_at IS NULL
           OR NEW.closing_confirmation_id IS NULL OR length(btrim(NEW.closure_reason))=0 THEN
          RAISE EXCEPTION 'invalid round closure';
        END IF;
        proof:=publishing_review_confirmation(NEW.closing_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['finish_review']);
        expected:=proof#>'{payload,review_closure}';
        submitted:=publishing_review_report_ids(NEW.id);
        SELECT coalesce(jsonb_agg(id ORDER BY id),'[]'::jsonb) INTO cancelled
          FROM publishing_review_invitations WHERE round_id=NEW.id AND status='cancelled'
            AND terminal_confirmation_id=NEW.closing_confirmation_id;
        IF NOT publishing_review_handling(proof->>'actor',NEW.manuscript_id,NEW.journal_id)
           OR expected->>'round_id' IS DISTINCT FROM NEW.id
           OR expected->>'reason' IS DISTINCT FROM NEW.closure_reason
           OR jsonb_typeof(expected->'submitted_report_ids') IS DISTINCT FROM 'array'
           OR jsonb_typeof(expected->'cancel_invitation_ids') IS DISTINCT FROM 'array' 
           OR publishing_review_sorted_ids(expected->'submitted_report_ids') IS DISTINCT FROM submitted
           OR publishing_review_sorted_ids(expected->'cancel_invitation_ids') IS DISTINCT FROM cancelled
           OR jsonb_array_length(submitted)<NEW.required_reports
           OR EXISTS (SELECT 1 FROM publishing_review_invitations WHERE round_id=NEW.id AND status IN ('pending','accepted'))
           OR EXISTS (SELECT 1 FROM publishing_assignments a JOIN publishing_review_invitations i ON i.id=a.review_invitation_id
             WHERE i.round_id=NEW.id AND a.ends_at IS NULL)
           OR EXISTS (SELECT 1 FROM publishing_review_reports r JOIN publishing_review_invitations i ON i.id=r.invitation_id
             WHERE i.round_id=NEW.id AND r.status='draft') THEN
          RAISE EXCEPTION 'round closure must confirm all reports and outstanding work';
        END IF;
      ELSE RAISE EXCEPTION 'invalid review round transition';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_require_sealed_round() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; expected jsonb; actual jsonb;
    BEGIN
      IF EXISTS (SELECT 1 FROM publishing_review_rounds WHERE id=NEW.id AND status='initializing') THEN
        RAISE EXCEPTION 'initializing review round cannot commit';
      END IF;
      proof:=publishing_review_confirmation(NEW.opening_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,NEW.version_id,ARRAY['open_review'],false);
      SELECT coalesce(jsonb_agg(value->'id' ORDER BY value->>'id'),'[]'::jsonb) INTO expected
        FROM jsonb_array_elements(proof#>'{payload,review,invitations}');
      SELECT coalesce(jsonb_agg(id ORDER BY id),'[]'::jsonb) INTO actual FROM publishing_review_invitations
        WHERE round_id=NEW.id AND invitation_confirmation_id=NEW.opening_confirmation_id;
      IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'opening invitations must all commit atomically'; END IF;
      RETURN NULL;
    END $$;

    CREATE FUNCTION publishing_guard_review_round_file() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent record; proof jsonb; link record; wanted jsonb;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'review round files are immutable'; END IF;
      SELECT * INTO parent FROM publishing_review_rounds WHERE id=NEW.round_id FOR UPDATE;
      IF NOT FOUND OR parent.status<>'initializing' OR parent.material_sealed_at IS NOT NULL
         OR parent.manuscript_id IS DISTINCT FROM NEW.manuscript_id
         OR parent.version_id IS DISTINCT FROM NEW.version_id THEN
        RAISE EXCEPTION 'review round files may only be inserted before atomic seal';
      END IF;
      proof:=publishing_review_confirmation(parent.opening_confirmation_id,parent.manuscript_id,
        parent.journal_id,parent.version_id,ARRAY['open_review']);
      SELECT v.purpose,v.visibility,b.sha256 INTO link FROM publishing_version_files v
        JOIN publishing_file_objects b ON b.id=v.file_object_id
        JOIN publishing_versions mv ON mv.id=v.version_id
        WHERE v.id=NEW.version_file_id AND v.manuscript_id=NEW.manuscript_id
          AND v.version_id=NEW.version_id AND mv.frozen_at IS NOT NULL;
      IF NOT FOUND OR link.purpose<>'blinded_manuscript' OR link.visibility<>'reviewer' THEN
        RAISE EXCEPTION 'review material must be frozen same-version blinded file';
      END IF;
      SELECT value INTO wanted FROM jsonb_array_elements(proof#>'{payload,review,files}')
        WHERE value->>'version_file_id'=NEW.version_file_id;
      IF NOT FOUND OR wanted->>'sha256' IS DISTINCT FROM link.sha256
         OR wanted->>'role' IS DISTINCT FROM NEW.role OR wanted->>'display_name' IS DISTINCT FROM NEW.display_name THEN
        RAISE EXCEPTION 'review material is absent from confirmed snapshot';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_review_invitation() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent record; proof jsonb; expected jsonb; report record;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'review invitation history is immutable'; END IF;
      SELECT * INTO parent FROM publishing_review_rounds WHERE id=NEW.round_id FOR UPDATE;
      IF NOT FOUND OR parent.status<>'open' OR parent.manuscript_id IS DISTINCT FROM NEW.manuscript_id
         OR parent.journal_id IS DISTINCT FROM NEW.journal_id OR parent.version_id IS DISTINCT FROM NEW.version_id THEN
        RAISE EXCEPTION 'invitation requires matching open fixed round';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'pending' THEN RAISE EXCEPTION 'review invitations must begin pending'; END IF;
        proof:=publishing_review_confirmation(NEW.invitation_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['open_review','invite_reviewers']);
        SELECT value INTO expected FROM jsonb_array_elements(proof#>'{payload,review,invitations}')
          WHERE value->>'id'=NEW.id;
        IF NOT FOUND OR proof->>'actor' IS DISTINCT FROM NEW.invited_by
           OR NOT publishing_review_handling(NEW.invited_by,NEW.manuscript_id,NEW.journal_id)
           OR proof->>'policy_version' IS DISTINCT FROM NEW.policy_version::text
           OR proof#>>'{payload,review,round_id}' IS DISTINCT FROM NEW.round_id
           OR proof#>>'{payload,review,version_id}' IS DISTINCT FROM NEW.version_id
           OR proof#>>'{payload,review,round_no}' IS DISTINCT FROM parent.round_no::text
           OR proof#>>'{payload,review,required_reports}' IS DISTINCT FROM parent.required_reports::text
           OR proof#>'{payload,review,form_snapshot}' IS DISTINCT FROM parent.form_snapshot
           OR proof#>>'{payload,review,form_digest}' IS DISTINCT FROM parent.form_digest
           OR proof#>>'{payload,review,material_digest}' IS DISTINCT FROM parent.material_digest
           OR (SELECT coalesce(jsonb_agg(value ORDER BY value->>'version_file_id'),'[]'::jsonb)
             FROM jsonb_array_elements(proof#>'{payload,review,files}')) IS DISTINCT FROM publishing_review_material(NEW.round_id)
           OR expected->>'reviewer_id' IS DISTINCT FROM NEW.reviewer_id
           OR expected->>'attempt_no' IS DISTINCT FROM NEW.attempt_no::text
           OR expected->'invitation_snapshot' IS DISTINCT FROM NEW.invitation_snapshot
           OR expected->>'content_digest' IS DISTINCT FROM NEW.content_digest
           OR (expected->>'response_due_at')::timestamptz IS DISTINCT FROM NEW.response_due_at
           OR (expected->>'report_due_at')::timestamptz IS DISTINCT FROM NEW.report_due_at THEN
          RAISE EXCEPTION 'invitation does not match confirmed target and content';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM memberships WHERE user_id=NEW.reviewer_id AND journal_id=NEW.journal_id AND role='reviewer') THEN
          RAISE EXCEPTION 'invitee must be current journal reviewer';
        END IF;
        RETURN NEW;
      END IF;
      IF OLD.status IN ('declined','cancelled','expired','submitted') THEN RAISE EXCEPTION 'terminal review invitation is immutable'; END IF;
      IF (to_jsonb(NEW)-ARRAY['status','responded_at','accepted_at','declined_at','cancelled_at','completed_at','conflict_status','response_notes','response_confirmation_id','terminal_confirmation_id'])
         IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','responded_at','accepted_at','declined_at','cancelled_at','completed_at','conflict_status','response_notes','response_confirmation_id','terminal_confirmation_id']) THEN
        RAISE EXCEPTION 'invitation identity material and deadlines are immutable';
      END IF;
      IF OLD.status='pending' AND NEW.status IN ('accepted','declined') THEN
        proof:=publishing_review_confirmation(NEW.response_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['respond_review_invitation']);
        expected:=proof#>'{payload,response}';
        IF proof->>'actor' IS DISTINCT FROM NEW.reviewer_id
           OR expected->>'invitation_id' IS DISTINCT FROM NEW.id
           OR expected->>'outcome' IS DISTINCT FROM (CASE NEW.status WHEN 'accepted' THEN 'accept' ELSE 'decline' END)
           OR expected->>'conflict_status' IS DISTINCT FROM NEW.conflict_status
           OR expected->>'notes' IS DISTINCT FROM NEW.response_notes
           OR (NEW.status='accepted' AND NEW.response_due_at<=clock_timestamp())
           OR NOT EXISTS (SELECT 1 FROM publishing_work_items WHERE id=proof->>'work_item_id' AND review_invitation_id=NEW.id)
           OR NEW.terminal_confirmation_id IS NOT NULL THEN
          RAISE EXCEPTION 'review response requires exact own current confirmation';
        END IF;
        IF NEW.status='accepted' AND (NEW.conflict_status<>'none'
           OR NOT EXISTS (SELECT 1 FROM memberships WHERE user_id=NEW.reviewer_id AND journal_id=NEW.journal_id AND role='reviewer')
           OR EXISTS (SELECT 1 FROM manuscripts WHERE id=NEW.manuscript_id AND author_id=NEW.reviewer_id)
           OR EXISTS (SELECT 1 FROM publishing_version_authors WHERE version_id=NEW.version_id AND linked_user_id=NEW.reviewer_id)) THEN
          RAISE EXCEPTION 'review acceptance requires independent no-conflict reviewer';
        END IF;
      ELSIF OLD.status IN ('pending','accepted') AND NEW.status='cancelled' THEN
        proof:=publishing_review_confirmation(NEW.terminal_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['finish_review','cancel_review_invitation']);
        expected:=proof#>'{payload,review_closure}';
        IF NOT publishing_review_handling(proof->>'actor',NEW.manuscript_id,NEW.journal_id)
           OR expected->>'round_id' IS DISTINCT FROM NEW.round_id OR NOT (expected->'cancel_invitation_ids' ? NEW.id)
           OR jsonb_typeof(expected->'cancel_invitation_ids') IS DISTINCT FROM 'array'
           OR jsonb_typeof(expected->'submitted_report_ids') IS DISTINCT FROM 'array'
           OR length(btrim(coalesce(expected->>'reason','')))=0
           OR publishing_review_sorted_ids(expected->'submitted_report_ids') IS DISTINCT FROM publishing_review_report_ids(NEW.round_id)
           OR (proof->>'action_type'='cancel_review_invitation' AND jsonb_array_length(expected->'cancel_invitation_ids')<>1)
           OR (to_jsonb(NEW)-ARRAY['status','cancelled_at','terminal_confirmation_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','cancelled_at','terminal_confirmation_id']) THEN
          RAISE EXCEPTION 'cancellation requires explicit confirmed closure list';
        END IF;
      ELSIF OLD.status='pending' AND NEW.status='expired' THEN
        IF NEW.response_due_at>clock_timestamp() OR (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
          RAISE EXCEPTION 'only unanswered overdue invitations expire deterministically';
        END IF;
      ELSIF OLD.status='accepted' AND NEW.status='submitted' THEN
        SELECT * INTO report FROM publishing_review_reports WHERE invitation_id=NEW.id AND status='submitted';
        IF NOT FOUND OR (NEW.terminal_confirmation_id IS NOT NULL AND NEW.terminal_confirmation_id IS DISTINCT FROM report.human_confirmation_id)
           OR (to_jsonb(NEW)-ARRAY['status','completed_at','terminal_confirmation_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','completed_at','terminal_confirmation_id']) THEN
          RAISE EXCEPTION 'submitted invitation requires its immutable submitted report';
        END IF;
      ELSE RAISE EXCEPTION 'invalid invitation transition';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_review_assignment() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target record; proof jsonb;
    BEGIN
      IF TG_OP='UPDATE' AND OLD.capability='reviewer' THEN
        IF OLD.ends_at IS NOT NULL OR NEW.ends_at IS NULL OR NEW.ends_at<OLD.starts_at
           OR (to_jsonb(NEW)-'ends_at') IS DISTINCT FROM (to_jsonb(OLD)-'ends_at') THEN
          RAISE EXCEPTION 'reviewer grant creation provenance is immutable and cannot reactivate';
        END IF;
        RETURN NEW;
      END IF;
      IF TG_OP='DELETE' THEN
        IF OLD.capability='reviewer' THEN RAISE EXCEPTION 'reviewer grant history is immutable'; END IF;
        RETURN OLD;
      END IF;
      IF TG_OP='UPDATE' AND NEW.capability='reviewer' THEN RAISE EXCEPTION 'cannot repurpose assignment as reviewer'; END IF;
      IF NEW.capability<>'reviewer' THEN RETURN NEW; END IF;
      SELECT i.*,r.status AS round_status INTO target FROM publishing_review_invitations i
        JOIN publishing_review_rounds r ON r.id=i.round_id WHERE i.id=NEW.review_invitation_id FOR UPDATE OF i;
      IF NOT FOUND OR target.status NOT IN ('accepted','submitted') OR target.round_status<>'open'
         OR target.manuscript_id IS DISTINCT FROM NEW.manuscript_id OR target.journal_id IS DISTINCT FROM NEW.journal_id
         OR target.reviewer_id IS DISTINCT FROM NEW.user_id OR target.conflict_status<>'none'
         OR NOT EXISTS (SELECT 1 FROM memberships WHERE user_id=NEW.user_id AND journal_id=NEW.journal_id AND role='reviewer')
         OR EXISTS (SELECT 1 FROM manuscripts WHERE id=NEW.manuscript_id AND author_id=NEW.user_id)
         OR EXISTS (SELECT 1 FROM publishing_version_authors WHERE version_id=target.version_id AND linked_user_id=NEW.user_id) THEN
        RAISE EXCEPTION 'reviewer grant requires own accepted no-conflict invitation';
      END IF;
      IF EXISTS (SELECT 1 FROM publishing_assignments WHERE review_invitation_id=NEW.review_invitation_id AND capability='reviewer') THEN
        RAISE EXCEPTION 'reviewer grant cannot be recreated after ending';
      END IF;
      proof:=publishing_review_confirmation(target.response_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,target.version_id,ARRAY['respond_review_invitation'],false);
      IF proof->>'actor' IS DISTINCT FROM NEW.user_id OR proof#>>'{payload,response,invitation_id}' IS DISTINCT FROM target.id
         OR proof#>>'{payload,response,outcome}' IS DISTINCT FROM 'accept'
         OR proof#>>'{payload,response,conflict_status}' IS DISTINCT FROM 'none' THEN
        RAISE EXCEPTION 'reviewer grant acceptance confirmation mismatches';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_review_report() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target record; proof jsonb; expected jsonb;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'review report history is immutable'; END IF;
      IF TG_OP='UPDATE' AND OLD.status IN ('submitted','withdrawn') THEN RAISE EXCEPTION 'final review report is immutable'; END IF;
      SELECT i.*,r.status AS round_status,r.form_snapshot AS round_form,r.form_digest AS round_digest
        INTO target FROM publishing_review_invitations i JOIN publishing_review_rounds r ON r.id=i.round_id
        WHERE i.id=NEW.invitation_id FOR UPDATE OF i;
      IF NOT FOUND OR target.manuscript_id IS DISTINCT FROM NEW.manuscript_id
         OR NEW.form_snapshot IS DISTINCT FROM target.round_form OR NEW.form_digest IS DISTINCT FROM target.round_digest THEN
        RAISE EXCEPTION 'report target and fixed form must match invitation round';
      END IF;
      IF TG_OP='UPDATE' AND (to_jsonb(NEW)-ARRAY['status','revision','author_text','editor_private_text','answers_json','recommendation','updated_at','submitted_at','human_confirmation_id','content_digest'])
         IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','revision','author_text','editor_private_text','answers_json','recommendation','updated_at','submitted_at','human_confirmation_id','content_digest']) THEN
        RAISE EXCEPTION 'report invitation and form are immutable';
      END IF;
      IF TG_OP='UPDATE' AND NEW.status='withdrawn' THEN
        IF target.status<>'cancelled' OR target.terminal_confirmation_id IS NULL
           OR NEW.revision<>OLD.revision+1
           OR (to_jsonb(NEW)-ARRAY['status','updated_at','revision']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','updated_at','revision']) THEN
          RAISE EXCEPTION 'withdrawal requires explicit invitation cancellation and preserves draft';
        END IF;
        RETURN NEW;
      END IF;
      IF target.status<>'accepted' OR target.conflict_status<>'none' OR target.round_status<>'open'
         OR NOT EXISTS (SELECT 1 FROM publishing_assignments WHERE review_invitation_id=target.id
             AND user_id=target.reviewer_id AND capability='reviewer' AND starts_at<=clock_timestamp() AND ends_at IS NULL) THEN
        RAISE EXCEPTION 'report requires active accepted reviewer grant';
      END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'draft' THEN RAISE EXCEPTION 'report must start as a draft'; END IF;
      ELSIF NEW.revision<>OLD.revision+1 THEN RAISE EXCEPTION 'report save requires next revision';
      END IF;
      IF TG_OP='UPDATE' AND NEW.status='submitted' THEN
        proof:=publishing_review_confirmation(NEW.human_confirmation_id,NEW.manuscript_id,
          target.journal_id,target.version_id,ARRAY['submit_review']);
        expected:=proof#>'{payload,review_report}';
        IF proof->>'actor' IS DISTINCT FROM target.reviewer_id
           OR expected->>'id' IS DISTINCT FROM NEW.id OR expected->>'invitation_id' IS DISTINCT FROM NEW.invitation_id
           OR expected->>'form_digest' IS DISTINCT FROM NEW.form_digest
           OR expected->>'content_digest' IS DISTINCT FROM NEW.content_digest
           OR expected->'data' IS DISTINCT FROM jsonb_build_object('author_text',NEW.author_text,
                'editor_private_text',NEW.editor_private_text,'answers_json',NEW.answers_json,'recommendation',NEW.recommendation)
           OR NOT EXISTS (SELECT 1 FROM publishing_work_items WHERE id=proof->>'work_item_id' AND review_report_id=NEW.id) THEN
          RAISE EXCEPTION 'submitted report requires exact own full-content confirmation';
        END IF;
      ELSIF TG_OP='UPDATE' AND NEW.status<>'draft' THEN RAISE EXCEPTION 'invalid report transition';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_review_work_item() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target record; expected_confirmation text; target_report record;
    BEGIN
      IF TG_OP<>'INSERT' AND (OLD.review_invitation_id IS NOT NULL OR OLD.review_report_id IS NOT NULL) THEN
        IF TG_OP='DELETE' OR OLD.status IN ('completed','cancelled')
           OR (to_jsonb(NEW)-ARRAY['status','completed_at','confirmation_id']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','completed_at','confirmation_id']) THEN
          RAISE EXCEPTION 'typed review task history and target are immutable';
        END IF;
      ELSIF TG_OP='DELETE' THEN RETURN OLD;
      ELSIF TG_OP='UPDATE' AND (NEW.review_invitation_id IS NOT NULL OR NEW.review_report_id IS NOT NULL) THEN
        RAISE EXCEPTION 'cannot repurpose existing task as review target';
      END IF;
      IF NEW.review_invitation_id IS NOT NULL THEN
        SELECT * INTO target FROM publishing_review_invitations WHERE id=NEW.review_invitation_id;
        IF NOT FOUND OR NEW.kind<>'respond_review_invitation' THEN RAISE EXCEPTION 'invalid invitation response task'; END IF;
        expected_confirmation:=target.response_confirmation_id;
        IF NEW.status='completed' AND target.status NOT IN ('accepted','declined','submitted','cancelled') THEN
          RAISE EXCEPTION 'response task cannot complete before real response';
        END IF;
        IF TG_OP='INSERT' AND target.status<>'pending' THEN RAISE EXCEPTION 'response task requires pending invitation'; END IF;
      ELSIF NEW.review_report_id IS NOT NULL THEN
        SELECT i.* INTO target FROM publishing_review_reports p JOIN publishing_review_invitations i ON i.id=p.invitation_id
          WHERE p.id=NEW.review_report_id;
        IF NOT FOUND OR NEW.kind<>'submit_review' THEN RAISE EXCEPTION 'invalid report submission task'; END IF;
        SELECT * INTO target_report FROM publishing_review_reports WHERE id=NEW.review_report_id;
        expected_confirmation:=target_report.human_confirmation_id;
        IF NEW.status='completed' AND target_report.status<>'submitted' THEN RAISE EXCEPTION 'report task cannot complete before real submission'; END IF;
        IF TG_OP='INSERT' AND (target.status<>'accepted' OR target_report.status<>'draft') THEN
          RAISE EXCEPTION 'report task requires accepted draft target';
        END IF;
      ELSE RETURN NEW;
      END IF;
      IF TG_OP='INSERT' AND NEW.status<>'pending' THEN RAISE EXCEPTION 'review task must start pending'; END IF;
      IF NEW.status='completed' AND (NEW.completed_at IS NULL OR NEW.confirmation_id IS NULL
          OR NEW.confirmation_id IS DISTINCT FROM expected_confirmation) THEN
        RAISE EXCEPTION 'completed review task must bind exact target confirmation';
      END IF;
      IF NEW.status='cancelled' AND (target.status NOT IN ('cancelled','expired')
          OR (NEW.confirmation_id IS NOT NULL AND NEW.confirmation_id IS DISTINCT FROM target.terminal_confirmation_id)) THEN
        RAISE EXCEPTION 'cancelled review task must bind real target cancellation';
      END IF;
      IF target.manuscript_id IS DISTINCT FROM NEW.manuscript_id OR target.journal_id IS DISTINCT FROM NEW.journal_id
         OR target.version_id IS DISTINCT FROM NEW.version_id OR target.reviewer_id IS DISTINCT FROM NEW.assignee_id
         OR NOT EXISTS (SELECT 1 FROM publishing_step_runs WHERE id=NEW.step_run_id
             AND manuscript_id=NEW.manuscript_id AND version_id=NEW.version_id AND step_key=NEW.kind) THEN
        RAISE EXCEPTION 'typed review task must match target reviewer version and own step';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_require_review_consistency() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE invitation text; actual record;
    BEGIN
      IF TG_TABLE_NAME='publishing_review_invitations' THEN invitation:=NEW.id;
      ELSIF TG_TABLE_NAME='publishing_assignments' THEN invitation:=NEW.review_invitation_id;
      ELSE invitation:=NEW.invitation_id;
      END IF;
      IF invitation IS NULL THEN RETURN NULL; END IF;
      SELECT i.*,r.status AS round_status INTO actual FROM publishing_review_invitations i
        JOIN publishing_review_rounds r ON r.id=i.round_id WHERE i.id=invitation;
      IF NOT FOUND THEN RAISE EXCEPTION 'review invitation history missing'; END IF;
      IF actual.status IN ('accepted','submitted') THEN
        IF NOT EXISTS (SELECT 1 FROM publishing_review_reports WHERE invitation_id=invitation
            AND status=(CASE actual.status WHEN 'accepted' THEN 'draft' ELSE 'submitted' END))
           OR NOT EXISTS (SELECT 1 FROM publishing_assignments WHERE review_invitation_id=invitation
                AND capability='reviewer' AND user_id=actual.reviewer_id)
           OR (actual.round_status='open' AND NOT EXISTS (SELECT 1 FROM publishing_assignments
                WHERE review_invitation_id=invitation AND user_id=actual.reviewer_id
                  AND capability='reviewer' AND ends_at IS NULL)) THEN
          RAISE EXCEPTION 'accepted review requires atomic grant and matching report state';
        END IF;
      END IF;
      IF actual.status IN ('cancelled','declined','expired') OR actual.round_status<>'open' THEN
        IF EXISTS (SELECT 1 FROM publishing_assignments WHERE review_invitation_id=invitation AND ends_at IS NULL)
           OR EXISTS (SELECT 1 FROM publishing_review_reports WHERE invitation_id=invitation AND status='draft') THEN
          RAISE EXCEPTION 'closed review cannot retain active grant or draft work';
        END IF;
      END IF;
      RETURN NULL;
    END $$;

    CREATE FUNCTION publishing_review_guard_parent_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME='publishing_assignments' AND EXISTS(SELECT 1 FROM publishing_assignments WHERE review_invitation_id IS NOT NULL) THEN
        RAISE EXCEPTION 'reviewer grant history cannot truncate';
      END IF;
      IF TG_TABLE_NAME='publishing_work_items' AND EXISTS(SELECT 1 FROM publishing_work_items WHERE review_invitation_id IS NOT NULL OR review_report_id IS NOT NULL) THEN
        RAISE EXCEPTION 'typed review task history cannot truncate';
      END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER publishing_review_invitation_consistent AFTER INSERT OR UPDATE ON publishing_review_invitations DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_review_consistency();
    CREATE CONSTRAINT TRIGGER publishing_review_grant_consistent AFTER INSERT OR UPDATE ON publishing_assignments DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_review_consistency();
    CREATE CONSTRAINT TRIGGER publishing_review_report_consistent AFTER INSERT OR UPDATE ON publishing_review_reports DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_review_consistency();
    CREATE TRIGGER publishing_review_assignment_truncate BEFORE TRUNCATE ON publishing_assignments FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_guard_parent_truncate();
    CREATE TRIGGER publishing_review_work_item_truncate BEFORE TRUNCATE ON publishing_work_items FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_guard_parent_truncate();

    CREATE FUNCTION publishing_review_reject_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'review history cannot truncate'; END $$;
    CREATE TRIGGER publishing_review_round_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_review_rounds FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_round();
    CREATE CONSTRAINT TRIGGER publishing_review_round_sealed AFTER INSERT OR UPDATE ON publishing_review_rounds DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_sealed_round();
    CREATE TRIGGER publishing_review_round_file_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_review_round_files FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_round_file();
    CREATE TRIGGER publishing_review_invitation_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_review_invitations FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_invitation();
    CREATE TRIGGER publishing_review_report_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_review_reports FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_report();
    CREATE TRIGGER publishing_review_assignment_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_assignments FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_assignment();
    CREATE TRIGGER publishing_review_work_item_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_work_items FOR EACH ROW EXECUTE FUNCTION publishing_guard_review_work_item();
    CREATE TRIGGER publishing_review_round_truncate BEFORE TRUNCATE ON publishing_review_rounds FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_reject_truncate();
    CREATE TRIGGER publishing_review_round_file_truncate BEFORE TRUNCATE ON publishing_review_round_files FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_reject_truncate();
    CREATE TRIGGER publishing_review_invitation_truncate BEFORE TRUNCATE ON publishing_review_invitations FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_reject_truncate();
    CREATE TRIGGER publishing_review_report_truncate BEFORE TRUNCATE ON publishing_review_reports FOR EACH STATEMENT EXECUTE FUNCTION publishing_review_reject_truncate();
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM publishing_review_rounds) OR EXISTS(SELECT 1 FROM publishing_review_round_files)
          OR EXISTS(SELECT 1 FROM publishing_review_invitations) OR EXISTS(SELECT 1 FROM publishing_review_reports)
          OR EXISTS(SELECT 1 FROM publishing_assignments WHERE review_invitation_id IS NOT NULL)
          OR EXISTS(SELECT 1 FROM publishing_work_items WHERE review_invitation_id IS NOT NULL OR review_report_id IS NOT NULL) THEN
          RAISE EXCEPTION 'refusing downgrade: peer review history exists';
        END IF;
      END $$;
      DROP TRIGGER publishing_review_assignment_guard ON publishing_assignments;
      DROP TRIGGER publishing_review_work_item_guard ON publishing_work_items;
      DROP TRIGGER publishing_review_grant_consistent ON publishing_assignments;
      DROP TRIGGER publishing_review_assignment_truncate ON publishing_assignments;
      DROP TRIGGER publishing_review_work_item_truncate ON publishing_work_items;
    """)
    for name in ("fk_pub_work_item_review_invitation", "fk_pub_work_item_review_report"):
        op.drop_constraint(name, "publishing_work_items", type_="foreignkey")
    op.drop_constraint("ck_pub_work_item_review_target", "publishing_work_items", type_="check")
    for name in (
        "uq_pub_work_item_step_assignee",
        "uq_pub_work_item_review_invitation",
        "uq_pub_work_item_review_report",
    ):
        op.drop_index(name, table_name="publishing_work_items")
    op.create_unique_constraint(
        "uq_pub_work_item_step_assignee",
        "publishing_work_items",
        ["step_run_id", "kind", "assignee_id"],
    )
    op.drop_column("publishing_work_items", "review_report_id")
    op.drop_column("publishing_work_items", "review_invitation_id")
    op.drop_constraint(
        "fk_pub_assignment_review_invitation", "publishing_assignments", type_="foreignkey"
    )
    op.drop_constraint("ck_pub_assignment_review_target", "publishing_assignments", type_="check")
    op.drop_constraint("ck_pub_assignment_capability", "publishing_assignments", type_="check")
    op.create_check_constraint(
        "ck_pub_assignment_capability",
        "publishing_assignments",
        "capability IN ('author','precheck','handling_editor','chief','production')",
    )
    op.drop_index("uq_pub_assignment_active_capability", table_name="publishing_assignments")
    op.drop_index("uq_pub_assignment_active_reviewer", table_name="publishing_assignments")
    op.create_index(
        "uq_pub_assignment_active_capability",
        "publishing_assignments",
        ["manuscript_id", "user_id", "capability"],
        unique=True,
        postgresql_where=sa.text("ends_at IS NULL"),
    )
    op.drop_column("publishing_assignments", "review_invitation_id")
    for name in (
        "publishing_review_reports",
        "publishing_review_invitations",
        "publishing_review_round_files",
        "publishing_review_rounds",
    ):
        op.drop_table(name)
    for name in (
        "publishing_require_review_consistency",
        "publishing_review_guard_parent_truncate",
        "publishing_guard_review_work_item",
        "publishing_guard_review_report",
        "publishing_guard_review_assignment",
        "publishing_guard_review_invitation",
        "publishing_guard_review_round_file",
        "publishing_require_sealed_round",
        "publishing_guard_review_round",
        "publishing_review_reject_truncate",
    ):
        op.execute(f"DROP FUNCTION {name}()")
    op.execute("DROP FUNCTION publishing_review_sorted_ids(jsonb)")
    op.execute("DROP FUNCTION publishing_review_report_ids(text)")
    op.execute("DROP FUNCTION publishing_review_material(text)")
    op.execute("DROP FUNCTION publishing_review_handling(text,text,text)")
    op.execute("DROP FUNCTION publishing_review_confirmation(text,text,text,text,text[],boolean)")
    op.drop_constraint(
        "uq_pub_version_file_id_manuscript_version", "publishing_version_files", type_="unique"
    )
