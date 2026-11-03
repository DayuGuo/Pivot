"""Confirmed editorial decisions, anonymous report releases and formal revision lineage.

Revision ID: 11d95a8b3e42
Revises: 10c84f7a2d31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "11d95a8b3e42"
down_revision = "10c84f7a2d31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "publishing_editorial_decisions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("step_run_id", sa.String(36), nullable=False),
        sa.Column("basis_round_id", sa.String(36), nullable=False),
        sa.Column("recommendation_confirmation_id", sa.String(36), nullable=False),
        sa.Column("reassessment_confirmation_id", sa.String(36), nullable=True),
        sa.Column("decision_code", sa.String(30), nullable=False),
        sa.Column("revision_kind", sa.String(20), nullable=True),
        sa.Column("rationale_private", sa.Text(), nullable=False),
        sa.Column("author_letter", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("chief_id", sa.String(36), nullable=False),
        sa.Column("human_confirmation_id", sa.String(36), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["chief_id"], ["users.id"], name=None),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint(
            "decision_code IN ('request_revision','accept','reject')", name="ck_pub_decision_code"
        ),
        sa.CheckConstraint(
            "policy_version >= 1 AND payload_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_decision_digest",
        ),
        sa.CheckConstraint(
            "(decision_code='request_revision' AND revision_kind IS NOT NULL AND revision_kind IN ('minor','major')) OR (decision_code IN ('accept','reject') AND revision_kind IS NULL)",
            name="ck_pub_decision_revision_kind",
        ),
        sa.CheckConstraint(
            "length(btrim(rationale_private)) BETWEEN 20 AND 8000 AND length(btrim(author_letter)) BETWEEN 20 AND 12000",
            name="ck_pub_decision_text",
        ),
        sa.ForeignKeyConstraint(
            ["basis_round_id", "manuscript_id"],
            ["publishing_review_rounds.id", "publishing_review_rounds.manuscript_id"],
            name="fk_pub_decision_basis_round",
        ),
        sa.ForeignKeyConstraint(
            ["human_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_decision_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["reassessment_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_decision_reassessment",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_decision_recommendation",
        ),
        sa.ForeignKeyConstraint(
            ["step_run_id", "manuscript_id"],
            ["publishing_step_runs.id", "publishing_step_runs.manuscript_id"],
            name="fk_pub_decision_step",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_decision_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_decision_version",
        ),
        sa.UniqueConstraint("human_confirmation_id", name="uq_pub_decision_confirmation"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_decision_id_manuscript"),
        sa.UniqueConstraint("step_run_id", name="uq_pub_decision_step"),
    )
    op.create_index(
        "ix_pub_decision_history",
        "publishing_editorial_decisions",
        ["manuscript_id", "decided_at"],
        unique=False,
    )
    op.create_table(
        "publishing_decision_report_releases",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("decision_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("author_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint("ordinal >= 1", name="ck_pub_release_order"),
        sa.CheckConstraint(
            "jsonb_typeof(author_snapshot)='object' AND snapshot_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pub_release_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id", "manuscript_id"],
            ["publishing_editorial_decisions.id", "publishing_editorial_decisions.manuscript_id"],
            name="fk_pub_release_decision",
        ),
        sa.ForeignKeyConstraint(
            ["report_id", "manuscript_id"],
            ["publishing_review_reports.id", "publishing_review_reports.manuscript_id"],
            name="fk_pub_release_report",
        ),
        sa.UniqueConstraint("decision_id", "report_id", name="uq_pub_release_decision_report"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_release_id_manuscript"),
        sa.UniqueConstraint("decision_id", "ordinal", name="uq_pub_release_order"),
    )
    op.create_table(
        "publishing_revision_requests",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("manuscript_id", sa.String(36), nullable=False),
        sa.Column("journal_id", sa.String(36), nullable=False),
        sa.Column("decision_id", sa.String(36), nullable=False),
        sa.Column("request_no", sa.Integer(), nullable=False),
        sa.Column("base_version_id", sa.String(36), nullable=False),
        sa.Column("draft_version_id", sa.String(36), nullable=False),
        sa.Column("submitted_version_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("rereview_required", sa.Boolean(), nullable=False),
        sa.Column("author_instructions", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author_confirmation_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["journal_id"], ["journals.id"], name=None),
        sa.ForeignKeyConstraint(["manuscript_id"], ["manuscripts.id"], name=None),
        sa.CheckConstraint(
            "request_no >= 1 AND kind IN ('minor','major')", name="ck_pub_revision_kind"
        ),
        sa.CheckConstraint(
            "kind <> 'major' OR rereview_required=true", name="ck_pub_revision_major"
        ),
        sa.CheckConstraint(
            "draft_version_id <> base_version_id AND length(btrim(author_instructions))>=20",
            name="ck_pub_revision_material",
        ),
        sa.CheckConstraint(
            "(status='requested' AND submitted_version_id IS NULL AND submitted_at IS NULL AND author_confirmation_id IS NULL) OR (status='submitted' AND submitted_version_id IS NOT NULL AND submitted_version_id=draft_version_id AND submitted_at IS NOT NULL AND author_confirmation_id IS NOT NULL)",
            name="ck_pub_revision_submission",
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_revision_base",
        ),
        sa.ForeignKeyConstraint(
            ["author_confirmation_id", "manuscript_id"],
            ["publishing_human_confirmations.id", "publishing_human_confirmations.manuscript_id"],
            name="fk_pub_revision_confirmation",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id", "manuscript_id"],
            ["publishing_editorial_decisions.id", "publishing_editorial_decisions.manuscript_id"],
            name="fk_pub_revision_decision",
        ),
        sa.ForeignKeyConstraint(
            ["draft_version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_revision_draft",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_version_id", "manuscript_id"],
            ["publishing_versions.id", "publishing_versions.manuscript_id"],
            name="fk_pub_revision_submitted",
        ),
        sa.ForeignKeyConstraint(
            ["manuscript_id", "journal_id"],
            ["manuscripts.id", "manuscripts.journal_id"],
            name="fk_pub_revision_tenant",
        ),
        sa.UniqueConstraint("decision_id", name="uq_pub_revision_decision"),
        sa.UniqueConstraint("id", "manuscript_id", name="uq_pub_revision_id_manuscript"),
        sa.UniqueConstraint("manuscript_id", "request_no", name="uq_pub_revision_sequence"),
    )
    op.create_index(
        "uq_pub_revision_requested",
        "publishing_revision_requests",
        ["manuscript_id"],
        unique=True,
        postgresql_where=sa.text("status='requested'"),
    )
    _install_guards()


def _install_guards():
    op.execute(r"""
    CREATE FUNCTION publishing_editorial_confirmation(conf text, manu text, journal text,
      version text, actions text[], fresh boolean DEFAULT true) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; flow record;
    BEGIN
      proof:=publishing_review_confirmation(conf,manu,journal,version,actions,false);
      IF proof#>>'{payload,action}' IS DISTINCT FROM proof->>'action_type'
         OR proof#>>'{payload,version,id}' IS DISTINCT FROM version
         OR NOT EXISTS(SELECT 1 FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
             WHERE t.id=proof->>'work_item_id' AND t.version_id=version AND s.version_id=version
               AND t.status='completed' AND s.status='completed'
               AND t.confirmation_id=conf AND s.confirmation_id=conf) THEN
        RAISE EXCEPTION 'editorial action requires its exact completed version task confirmation';
      END IF;
      IF fresh THEN
        SELECT revision,policy_version INTO flow FROM publishing_workflows
          WHERE manuscript_id=manu AND journal_id=journal FOR SHARE;
        IF NOT FOUND OR flow.revision::text IS DISTINCT FROM proof->>'base_revision'
           OR flow.policy_version::text IS DISTINCT FROM proof->>'policy_version' THEN
          RAISE EXCEPTION 'stale editorial confirmation revision or policy';
        END IF;
      END IF;
      RETURN proof;
    END $$;

    CREATE FUNCTION publishing_editorial_author_snapshot(report text) RETURNS jsonb LANGUAGE plpgsql AS $$
    DECLARE item record; questions jsonb; answers jsonb;
    BEGIN
      SELECT author_text,form_snapshot,answers_json INTO item FROM publishing_review_reports WHERE id=report AND status='submitted';
      IF NOT FOUND THEN RAISE EXCEPTION 'release requires submitted report'; END IF;
      SELECT coalesce(jsonb_agg(jsonb_build_object('key',q.value->'key','label',q.value->'label',
          'kind',q.value->'kind','required',q.value->'required') ORDER BY q.ordinality),'[]'::jsonb),
          coalesce(jsonb_object_agg(q.value->>'key',item.answers_json->(q.value->>'key')),'{}'::jsonb)
        INTO questions,answers FROM jsonb_array_elements(item.form_snapshot->'questions') WITH ORDINALITY q(value,ordinality)
        WHERE q.value->>'audience'='author';
      IF EXISTS (SELECT 1 FROM jsonb_array_elements(questions) q WHERE jsonb_typeof(q->'key') IS DISTINCT FROM 'string'
           OR jsonb_typeof(q->'label') IS DISTINCT FROM 'string' OR q->>'kind' IS DISTINCT FROM 'text'
           OR jsonb_typeof(q->'required') IS DISTINCT FROM 'boolean'
           OR jsonb_typeof(answers->(q->>'key')) IS DISTINCT FROM 'string') THEN
        RAISE EXCEPTION 'release form snapshot must contain safe fixed author questions and answers';
      END IF;
      RETURN jsonb_build_object('author_text',item.author_text,'questions',questions,'answers',answers);
    END $$;

    CREATE FUNCTION publishing_guard_editorial_decision() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE proof jsonb; expected jsonb; rec jsonb; assessment jsonb; basis record;
      source_request record; production record; digests jsonb; wanted jsonb;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'editorial decisions are immutable'; END IF;
      proof:=publishing_editorial_confirmation(NEW.human_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,NEW.version_id,ARRAY['record_decision']);
      expected:=proof#>'{payload,decision}';
      IF proof->>'actor' IS DISTINCT FROM NEW.chief_id
         OR NOT EXISTS(SELECT 1 FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
             WHERE t.id=proof->>'work_item_id' AND t.step_run_id=NEW.step_run_id AND s.step_key='chief_decision')
         OR NOT EXISTS(SELECT 1 FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id
             AND current_version_id=NEW.version_id AND stage='chief_decision')
         OR NOT EXISTS(SELECT 1 FROM publishing_versions WHERE id=NEW.version_id AND frozen_at IS NOT NULL)
         OR NOT EXISTS(SELECT 1 FROM memberships WHERE user_id=NEW.chief_id AND journal_id=NEW.journal_id AND role='chief_editor')
         OR NOT EXISTS(SELECT 1 FROM publishing_assignments WHERE user_id=NEW.chief_id
             AND manuscript_id=NEW.manuscript_id AND journal_id=NEW.journal_id AND capability='chief'
             AND starts_at<=clock_timestamp() AND (ends_at IS NULL OR ends_at>clock_timestamp()))
         OR EXISTS(SELECT 1 FROM manuscripts WHERE id=NEW.manuscript_id AND author_id=NEW.chief_id)
         OR EXISTS(SELECT 1 FROM publishing_version_authors a JOIN users u ON u.id=NEW.chief_id
             WHERE a.manuscript_id=NEW.manuscript_id AND (a.linked_user_id=u.id OR lower(a.email)=lower(u.email)))
         OR proof#>>'{payload,decision_digest}' IS DISTINCT FROM NEW.payload_digest
         OR (expected-ARRAY['public_reports','revision_request','production_assignee','share_reports_anonymity_reviewed']) IS DISTINCT FROM
             jsonb_build_object('id',NEW.id,'version_id',NEW.version_id,'basis_round_id',NEW.basis_round_id,
               'recommendation_confirmation_id',NEW.recommendation_confirmation_id,
               'reassessment_confirmation_id',NEW.reassessment_confirmation_id,'decision_code',NEW.decision_code,
               'revision_kind',NEW.revision_kind,'rationale_private',NEW.rationale_private,
               'author_letter',NEW.author_letter,'policy_version',NEW.policy_version)
         OR jsonb_typeof(expected->'public_reports') IS DISTINCT FROM 'array'
         OR jsonb_typeof(expected->'share_reports_anonymity_reviewed') IS DISTINCT FROM 'boolean' THEN
        RAISE EXCEPTION 'decision must bind exact current chief task and full approved payload';
      END IF;
      IF jsonb_array_length(expected->'public_reports')>0
         AND expected->'share_reports_anonymity_reviewed' IS DISTINCT FROM 'true'::jsonb THEN
        RAISE EXCEPTION 'report sharing requires explicit human anonymity review';
      END IF;
      SELECT * INTO basis FROM publishing_review_rounds WHERE id=NEW.basis_round_id
        AND manuscript_id=NEW.manuscript_id AND journal_id=NEW.journal_id AND status='closed';
      IF NOT FOUND THEN RAISE EXCEPTION 'decision basis must be closed same-manuscript round'; END IF;
      rec:=publishing_editorial_confirmation(NEW.recommendation_confirmation_id,NEW.manuscript_id,
        NEW.journal_id,NEW.version_id,ARRAY['recommend_decision'],false);
      IF rec#>>'{payload,recommendation,version_id}' IS DISTINCT FROM NEW.version_id
         OR rec#>>'{payload,recommendation,basis_round_id}' IS DISTINCT FROM NEW.basis_round_id
         OR rec#>>'{payload,recommendation,reassessment_confirmation_id}' IS DISTINCT FROM NEW.reassessment_confirmation_id
         OR NOT EXISTS(SELECT 1 FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
             WHERE t.id=rec->>'work_item_id' AND s.step_key='editor_recommendation') THEN
        RAISE EXCEPTION 'decision requires completed current-version editor recommendation';
      END IF;
      SELECT coalesce(jsonb_agg(jsonb_build_object('report_id',r.id,'content_digest',r.content_digest,
        'form_digest',r.form_digest) ORDER BY r.id),'[]'::jsonb) INTO digests
        FROM publishing_review_reports r JOIN publishing_review_invitations i ON i.id=r.invitation_id
        WHERE i.round_id=basis.id AND r.status='submitted';
      SELECT coalesce(jsonb_agg(value ORDER BY value->>'report_id'),'[]'::jsonb) INTO wanted
        FROM jsonb_array_elements(rec#>'{payload,recommendation,report_digests}');
      IF digests IS DISTINCT FROM wanted OR jsonb_array_length(digests)<basis.required_reports THEN
        RAISE EXCEPTION 'recommendation must bind actual submitted basis reports';
      END IF;
      IF basis.version_id IS DISTINCT FROM NEW.version_id THEN
        IF NEW.reassessment_confirmation_id IS NULL THEN RAISE EXCEPTION 'cross-version decision needs explicit minor reassessment'; END IF;
        assessment:=publishing_editorial_confirmation(NEW.reassessment_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.version_id,ARRAY['assess_revision'],false);
        SELECT rr.*,d.basis_round_id AS source_basis,d.version_id AS source_version,d.decision_code AS source_code
          INTO source_request FROM publishing_revision_requests rr JOIN publishing_editorial_decisions d ON d.id=rr.decision_id
          WHERE rr.id=assessment#>>'{payload,assessment,revision_request_id}' AND rr.manuscript_id=NEW.manuscript_id
            AND rr.status='submitted' AND rr.submitted_version_id=NEW.version_id;
        IF NOT FOUND OR source_request.kind<>'minor' OR source_request.rereview_required
           OR source_request.source_basis IS DISTINCT FROM NEW.basis_round_id
           OR source_request.source_version IS DISTINCT FROM source_request.base_version_id
           OR source_request.source_code<>'request_revision'
           OR assessment#>>'{payload,assessment,version_id}' IS DISTINCT FROM NEW.version_id
           OR assessment#>>'{payload,assessment,base_version_id}' IS DISTINCT FROM source_request.base_version_id
           OR assessment#>>'{payload,assessment,basis_round_id}' IS DISTINCT FROM NEW.basis_round_id
           OR assessment#>>'{payload,assessment,outcome}' IS DISTINCT FROM 'ready_for_chief'
           OR NOT EXISTS(SELECT 1 FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
               WHERE t.id=assessment->>'work_item_id' AND s.step_key='revision_assessment') THEN
          RAISE EXCEPTION 'cross-version basis requires submitted minor request and current reassessment';
        END IF;
      END IF;
      IF NEW.decision_code='request_revision' THEN
        IF jsonb_typeof(expected->'revision_request') IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'revision decision requires planned request'; END IF;
      ELSIF expected->'revision_request' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'non-revision decision cannot create revision request';
      END IF;
      IF NEW.decision_code='accept' THEN
        SELECT u.id,u.name,u.email INTO production FROM users u JOIN memberships m ON m.user_id=u.id
          WHERE u.id=expected#>>'{production_assignee,id}' AND m.journal_id=NEW.journal_id AND m.role='production_editor';
        IF NOT FOUND OR expected->'production_assignee' IS DISTINCT FROM jsonb_build_object('id',production.id,
             'name',production.name,'email',production.email,'role','production_editor')
           OR EXISTS(SELECT 1 FROM manuscripts WHERE id=NEW.manuscript_id AND author_id=production.id)
           OR EXISTS(SELECT 1 FROM publishing_version_authors a WHERE a.manuscript_id=NEW.manuscript_id
               AND (a.linked_user_id=production.id OR lower(a.email)=lower(production.email))) THEN
          RAISE EXCEPTION 'accept requires exact independent current production assignee';
        END IF;
      ELSIF expected->'production_assignee' IS DISTINCT FROM 'null'::jsonb THEN
        RAISE EXCEPTION 'only accept has a production assignee';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_decision_release() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE decision record; report record; proof jsonb; expected jsonb;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'decision report releases are immutable'; END IF;
      SELECT * INTO decision FROM publishing_editorial_decisions WHERE id=NEW.decision_id AND manuscript_id=NEW.manuscript_id;
      IF NOT FOUND THEN RAISE EXCEPTION 'release requires same-manuscript confirmed decision'; END IF;
      SELECT r.*,i.round_id INTO report FROM publishing_review_reports r JOIN publishing_review_invitations i ON i.id=r.invitation_id
        WHERE r.id=NEW.report_id AND r.manuscript_id=NEW.manuscript_id AND r.status='submitted';
      IF NOT FOUND OR report.round_id IS DISTINCT FROM decision.basis_round_id THEN RAISE EXCEPTION 'release requires submitted basis-round report'; END IF;
      proof:=publishing_editorial_confirmation(decision.human_confirmation_id,NEW.manuscript_id,
        decision.journal_id,decision.version_id,ARRAY['record_decision'],false);
      SELECT value INTO expected FROM jsonb_array_elements(proof#>'{payload,decision,public_reports}') WHERE value->>'report_id'=NEW.report_id;
      IF NOT FOUND OR expected IS DISTINCT FROM jsonb_build_object('report_id',NEW.report_id,'ordinal',NEW.ordinal,
          'author_snapshot',NEW.author_snapshot,'snapshot_digest',NEW.snapshot_digest)
         OR NEW.author_snapshot IS DISTINCT FROM publishing_editorial_author_snapshot(NEW.report_id)
         OR proof#>'{payload,decision,share_reports_anonymity_reviewed}' IS DISTINCT FROM 'true'::jsonb THEN
        RAISE EXCEPTION 'release must match exact approved anonymous author-only snapshot';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_guard_revision_request() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE decision record; proof jsonb; expected jsonb; draft record; response record; owner text;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'revision request history is immutable'; END IF;
      IF TG_OP='UPDATE' AND OLD.status='submitted' THEN RAISE EXCEPTION 'submitted revision request is immutable'; END IF;
      SELECT * INTO decision FROM publishing_editorial_decisions WHERE id=NEW.decision_id
        AND manuscript_id=NEW.manuscript_id AND journal_id=NEW.journal_id;
      IF NOT FOUND OR decision.decision_code<>'request_revision' OR decision.version_id IS DISTINCT FROM NEW.base_version_id
         OR decision.revision_kind IS DISTINCT FROM NEW.kind THEN RAISE EXCEPTION 'revision request requires exact source revision decision'; END IF;
      IF TG_OP='INSERT' THEN
        proof:=publishing_editorial_confirmation(decision.human_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.base_version_id,ARRAY['record_decision']);
        expected:=proof#>'{payload,decision,revision_request}';
        SELECT * INTO draft FROM publishing_versions WHERE id=NEW.draft_version_id AND manuscript_id=NEW.manuscript_id;
        IF NOT FOUND OR draft.frozen_at IS NOT NULL OR NEW.status<>'requested'
           OR NOT EXISTS(SELECT 1 FROM publishing_versions WHERE id=NEW.base_version_id AND version_no<draft.version_no)
           OR NOT EXISTS(SELECT 1 FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id AND draft_version_id=NEW.draft_version_id)
           OR (expected-'due_at') IS DISTINCT FROM jsonb_build_object('id',NEW.id,'decision_id',NEW.decision_id,
             'request_no',NEW.request_no,'base_version_id',NEW.base_version_id,'planned_draft_version_id',NEW.draft_version_id,
             'kind',NEW.kind,'rereview_required',NEW.rereview_required,'author_instructions',NEW.author_instructions)
           OR (expected->>'due_at')::timestamptz IS DISTINCT FROM NEW.due_at THEN
          RAISE EXCEPTION 'revision request and new draft must match complete approved plan';
        END IF;
      ELSE
        IF NEW.status<>'submitted' OR (to_jsonb(NEW)-ARRAY['status','submitted_version_id','submitted_at','author_confirmation_id'])
           IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','submitted_version_id','submitted_at','author_confirmation_id']) THEN
          RAISE EXCEPTION 'only exact requested-to-submitted revision transition is allowed';
        END IF;
        proof:=publishing_editorial_confirmation(NEW.author_confirmation_id,NEW.manuscript_id,
          NEW.journal_id,NEW.submitted_version_id,ARRAY['submit_revision']);
        expected:=proof#>'{payload,revision_request}';
        SELECT author_id INTO owner FROM manuscripts WHERE id=NEW.manuscript_id;
        SELECT * INTO draft FROM publishing_versions WHERE id=NEW.submitted_version_id AND manuscript_id=NEW.manuscript_id;
        SELECT v.id,b.sha256 INTO response FROM publishing_version_files v JOIN publishing_file_objects b ON b.id=v.file_object_id
          WHERE v.version_id=NEW.submitted_version_id AND v.manuscript_id=NEW.manuscript_id AND v.purpose='response';
        IF NOT FOUND OR draft.frozen_at IS NULL OR draft.content_digest IS NULL OR draft.content_digest !~ '^[0-9a-f]{64}$'
           OR proof->>'actor' IS DISTINCT FROM owner
           OR NOT EXISTS(SELECT 1 FROM publishing_workflows WHERE manuscript_id=NEW.manuscript_id AND draft_version_id=NEW.draft_version_id AND stage='author_revision')
           OR NOT EXISTS(SELECT 1 FROM publishing_work_items t JOIN publishing_step_runs s ON s.id=t.step_run_id
             WHERE t.id=proof->>'work_item_id' AND s.step_key='author_revision')
           OR (expected-'due_at') IS DISTINCT FROM jsonb_build_object('id',NEW.id,'decision_id',NEW.decision_id,
             'base_version_id',NEW.base_version_id,'draft_version_id',NEW.draft_version_id,'kind',NEW.kind,
             'rereview_required',NEW.rereview_required,'author_instructions',NEW.author_instructions,
             'submitted_version_id',NEW.submitted_version_id)
           OR (expected->>'due_at')::timestamptz IS DISTINCT FROM NEW.due_at
           OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(proof#>'{payload,version,files}') f
             WHERE f->>'id'=response.id AND f->>'purpose'='response' AND f->>'sha256'=response.sha256) THEN
          RAISE EXCEPTION 'revision submit requires owner confirmation frozen new version and actual response';
        END IF;
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION publishing_require_decision_bundle() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE target text; decision record; proof jsonb; expected jsonb; actual jsonb; plan jsonb;
    BEGIN
      IF TG_TABLE_NAME='publishing_editorial_decisions' THEN target:=NEW.id; ELSE target:=NEW.decision_id; END IF;
      SELECT * INTO decision FROM publishing_editorial_decisions WHERE id=target;
      IF NOT FOUND THEN RAISE EXCEPTION 'decision bundle is missing'; END IF;
      proof:=publishing_editorial_confirmation(decision.human_confirmation_id,decision.manuscript_id,
        decision.journal_id,decision.version_id,ARRAY['record_decision'],false);
      SELECT coalesce(jsonb_agg(value ORDER BY (value->>'ordinal')::integer,value->>'report_id'),'[]'::jsonb)
        INTO expected FROM jsonb_array_elements(proof#>'{payload,decision,public_reports}');
      SELECT coalesce(jsonb_agg(jsonb_build_object('report_id',report_id,'ordinal',ordinal,
        'author_snapshot',author_snapshot,'snapshot_digest',snapshot_digest) ORDER BY ordinal,report_id),'[]'::jsonb)
        INTO actual FROM publishing_decision_report_releases WHERE decision_id=target;
      IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'all and only approved report releases must commit atomically'; END IF;
      plan:=proof#>'{payload,decision,revision_request}';
      IF decision.decision_code='request_revision' THEN
        IF NOT EXISTS(SELECT 1 FROM publishing_revision_requests WHERE decision_id=target AND id=plan->>'id') THEN
          RAISE EXCEPTION 'planned revision request and draft must commit with decision';
        END IF;
      ELSIF EXISTS(SELECT 1 FROM publishing_revision_requests WHERE decision_id=target) THEN
        RAISE EXCEPTION 'non-revision decision cannot own a revision request';
      END IF;
      RETURN NULL;
    END $$;

    CREATE FUNCTION publishing_editorial_reject_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'editorial history cannot truncate'; END $$;
    CREATE TRIGGER publishing_editorial_decision_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_editorial_decisions FOR EACH ROW EXECUTE FUNCTION publishing_guard_editorial_decision();
    CREATE TRIGGER publishing_decision_release_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_decision_report_releases FOR EACH ROW EXECUTE FUNCTION publishing_guard_decision_release();
    CREATE TRIGGER publishing_revision_request_guard BEFORE INSERT OR UPDATE OR DELETE ON publishing_revision_requests FOR EACH ROW EXECUTE FUNCTION publishing_guard_revision_request();
    CREATE CONSTRAINT TRIGGER publishing_decision_bundle AFTER INSERT ON publishing_editorial_decisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_decision_bundle();
    CREATE CONSTRAINT TRIGGER publishing_release_bundle AFTER INSERT ON publishing_decision_report_releases DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_decision_bundle();
    CREATE CONSTRAINT TRIGGER publishing_revision_bundle AFTER INSERT OR UPDATE ON publishing_revision_requests DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION publishing_require_decision_bundle();
    CREATE TRIGGER publishing_editorial_decision_truncate BEFORE TRUNCATE ON publishing_editorial_decisions FOR EACH STATEMENT EXECUTE FUNCTION publishing_editorial_reject_truncate();
    CREATE TRIGGER publishing_decision_release_truncate BEFORE TRUNCATE ON publishing_decision_report_releases FOR EACH STATEMENT EXECUTE FUNCTION publishing_editorial_reject_truncate();
    CREATE TRIGGER publishing_revision_request_truncate BEFORE TRUNCATE ON publishing_revision_requests FOR EACH STATEMENT EXECUTE FUNCTION publishing_editorial_reject_truncate();
    """)


def downgrade():
    op.execute("""
      DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM publishing_editorial_decisions) OR EXISTS(SELECT 1 FROM publishing_decision_report_releases)
           OR EXISTS(SELECT 1 FROM publishing_revision_requests) THEN
          RAISE EXCEPTION 'refusing downgrade: editorial decision or revision history exists';
        END IF;
      END $$;
    """)
    for table in (
        "publishing_decision_report_releases",
        "publishing_revision_requests",
        "publishing_editorial_decisions",
    ):
        op.drop_table(table)
    for function in (
        "publishing_require_decision_bundle",
        "publishing_guard_revision_request",
        "publishing_guard_decision_release",
        "publishing_guard_editorial_decision",
        "publishing_editorial_reject_truncate",
    ):
        op.execute(f"DROP FUNCTION {function}()")
    op.execute("DROP FUNCTION publishing_editorial_author_snapshot(text)")
    op.execute(
        "DROP FUNCTION publishing_editorial_confirmation(text,text,text,text,text[],boolean)"
    )
