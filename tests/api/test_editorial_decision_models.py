"""E model/DDL confirmation guards in random, rolled-back PostgreSQL schemas.

Synthetic relational fixtures are not API/browser acceptance or actual CAS validation.
The lead owns current-role policy, full minor lineage traversal and user projections.
"""

import hashlib
import importlib.util
import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apps.api.publishing import editorial_chat, editorial_demo  # noqa: F401
from apps.api.publishing.db import engine
from apps.api.publishing.domain import checks, decision_models  # noqa: F401
from apps.api.publishing.domain.decision_models import (
    DecisionReportRelease,
    EditorialDecision,
    RevisionRequest,
)
from apps.api.publishing.domain.models import (
    ActionProposal,
    Assignment,
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    VersionFile,
    WorkItem,
)
from apps.api.publishing.domain.review_models import ReviewRound, ReviewRoundFile
from apps.api.publishing.domain.review_schemas import FORM
from apps.api.publishing.models import Base, Membership, User, now, uid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "_existing_peer_review_helpers", ROOT / "tests/api/test_peer_review_models.py"
)
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)
MIGRATION = peer.migration("11d95a8b3e42")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.fixture
def editorial_world():
    assert Path(decision_models.__file__).resolve().is_relative_to(ROOT)
    with engine.connect() as c:
        transaction = c.begin()
        schema = "test_editorial_" + uid().replace("-", "")
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
        c.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        with Operations.context(MigrationContext.configure(c)):
            for module in [*peer.MIGRATIONS, MIGRATION]:
                module.upgrade()
        db = Session(bind=c, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            w = peer.make_world(db, c)
            for role in ("chief_editor", "production_editor"):
                u = User(
                    id=uid(),
                    email=f"{uid()}@publishing.test",
                    name="合成" + role,
                    password_hash="not-a-login",
                )
                db.add(u)
                db.flush()
                db.add(Membership(user_id=u.id, journal_id=w.journal.id, role=role))
                w.users[role] = u
            db.add(
                Assignment(
                    manuscript_id=w.manuscript.id,
                    journal_id=w.journal.id,
                    user_id=w.users["chief_editor"].id,
                    capability="chief",
                    assigned_by=w.users["editor"].id,
                )
            )
            w.flow.chief_id = w.users["chief_editor"].id
            db.flush()
            yield w
        finally:
            db.close()
            transaction.rollback()


def task(w, stage, actor, version=None, *, set_current=True):
    version = version or w.version
    cycle = (
        w.db.scalar(
            select(func.max(StepRun.cycle_no)).where(
                StepRun.manuscript_id == w.manuscript.id, StepRun.step_key == stage
            )
        )
        or 0
    ) + 1
    s = StepRun(
        id=uid(),
        manuscript_id=w.manuscript.id,
        version_id=version.id,
        step_key=stage,
        cycle_no=cycle,
    )
    w.db.add(s)
    w.db.flush()
    t = WorkItem(
        id=uid(),
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        version_id=version.id,
        step_run_id=s.id,
        kind=stage,
        assignee_id=actor.id,
    )
    w.db.add(t)
    w.flow.stage, w.flow.current_step_id = stage, s.id
    if set_current:
        w.flow.current_version_id = version.id
    w.db.flush()
    return t


def file_snapshot(w, version):
    return [
        dict(id=f.id, purpose=f.purpose, sha256=b.sha256)
        for f, b in w.db.execute(
            select(VersionFile, FileObject)
            .join(FileObject, FileObject.id == VersionFile.file_object_id)
            .where(VersionFile.version_id == version.id)
        )
    ]


def confirmation(w, actor, action, payload, *, work=None, version=None):
    version = version or w.version
    work = work or task(w, action, actor, version)
    envelope = {
        "action": action,
        "stage": work.kind,
        "version": {"id": version.id, "files": file_snapshot(w, version)},
        "schema_version": 1,
        "synthetic_only": True,
        **payload,
    }
    p = ActionProposal(
        id=uid(),
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        work_item_id=work.id,
        version_id=version.id,
        action_type=action,
        prepared_by=actor.id,
        responsible_user_id=actor.id,
        base_revision=w.flow.revision,
        policy_version=w.flow.policy_version,
        payload_snapshot=envelope,
        evidence_digests={},
        digest=digest(envelope),
        expires_at=now() + timedelta(hours=1),
    )
    w.db.add(p)
    w.db.flush()
    c = HumanConfirmation(
        id=uid(),
        manuscript_id=w.manuscript.id,
        proposal_id=p.id,
        responsible_user_id=actor.id,
        session_hash="a" * 64,
        digest=p.digest,
        outcome="confirm",
    )
    w.db.add(c)
    w.db.flush()
    step = w.db.get(StepRun, work.step_run_id)
    work.status = "completed"
    work.completed_at = now()
    work.confirmation_id = c.id
    step.status = "completed"
    step.completed_at = now()
    step.confirmation_id = c.id
    step.outcome_json = {"action": action, **payload}
    w.db.flush()
    return c, p


def closed_basis(w):
    fixed = dict(
        round_id=uid(),
        round_no=1,
        version_id=w.version.id,
        required_reports=1,
        form_snapshot=deepcopy(FORM),
        form_digest=digest(FORM),
        material_digest=w.blob.sha256,
        files=[
            dict(
                version_file_id=w.file.id,
                sha256=w.blob.sha256,
                role="blinded_manuscript",
                display_name="review-manuscript.txt",
            )
        ],
        invitations=[],
    )
    c = peer.proof(w, w.users["editor"], "open_review", {"review": fixed})
    r = ReviewRound(
        id=fixed["round_id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        version_id=w.version.id,
        round_no=1,
        required_reports=1,
        policy_version=1,
        form_snapshot=FORM,
        form_digest=fixed["form_digest"],
        material_digest=fixed["material_digest"],
        opened_by=w.users["editor"].id,
        opening_confirmation_id=c.id,
    )
    w.db.add(r)
    w.db.flush()
    w.db.add(
        ReviewRoundFile(
            manuscript_id=w.manuscript.id,
            round_id=r.id,
            version_id=w.version.id,
            version_file_id=w.file.id,
            display_name="review-manuscript.txt",
        )
    )
    w.db.flush()
    r.status = "open"
    r.material_sealed_at = now()
    w.db.flush()
    i, response_task = peer.add_invitation(w, r)
    grant, report, report_task = peer.respond(w, i, response_task)
    data = dict(
        author_text="这是给作者的合成匿名评审意见，需要补充方法与结果证据。" * 3,
        editor_private_text="这是仅供编辑核查的合成私密内容，不能对作者开放。" * 2,
        answers_json={
            "rigor": "合成方法证据评估，不含真实稿件。" * 2,
            "confidential_assessment": "给编辑的合成私密答案。" * 3,
        },
        recommendation="minor_revision",
    )
    rc = peer.proof(
        w,
        w.users["reviewer"],
        "submit_review",
        {
            "review_report": dict(
                id=report.id,
                invitation_id=i.id,
                form_digest=report.form_digest,
                data=data,
                content_digest=digest(data),
            )
        },
        task=report_task,
    )
    for k, v in data.items():
        setattr(report, k, v)
    report.status = "submitted"
    report.revision += 1
    report.submitted_at = now()
    report.human_confirmation_id = rc.id
    report.content_digest = digest(data)
    w.db.flush()
    i.status = "submitted"
    i.completed_at = now()
    i.terminal_confirmation_id = rc.id
    report_task.status = "completed"
    report_task.completed_at = now()
    report_task.confirmation_id = rc.id
    w.db.flush()
    cc = peer.proof(
        w,
        w.users["editor"],
        "finish_review",
        {
            "review_closure": dict(
                round_id=r.id,
                reason="合成评审已齐，明确关闭",
                submitted_report_ids=[report.id],
                cancel_invitation_ids=[],
            )
        },
    )
    grant.ends_at = now()
    w.db.flush()
    r.status = "closed"
    r.closed_at = now()
    r.closure_reason = "合成评审已齐，明确关闭"
    r.closing_confirmation_id = cc.id
    w.db.flush()
    w.round, w.report = r, report
    peer.boundary(w.db)
    return r, report


def author_snapshot(report):
    questions = [
        {key: q[key] for key in ("key", "label", "kind", "required")}
        for q in report.form_snapshot["questions"]
        if q["audience"] == "author"
    ]
    return dict(
        author_text=report.author_text,
        answers={q["key"]: report.answers_json[q["key"]] for q in questions},
        questions=questions,
    )


def prepare_decision(
    w,
    code="reject",
    *,
    kind=None,
    share=False,
    assessment=None,
    recommendation="accept",
    actor=None,
    mutate=None,
):
    actor = actor or w.users["chief_editor"]
    rec = dict(
        version_id=w.version.id,
        basis_round_id=w.round.id,
        recommendation=recommendation,
        revision_kind="minor" if recommendation == "request_revision" else None,
        rationale_private="编辑完成对证据的人工评议，保留合成私密建议。" * 2,
        author_letter="编辑提出的合成作者信仍只是建议，不能代替主编决定。" * 2,
        report_digests=[
            dict(
                report_id=w.report.id,
                content_digest=w.report.content_digest,
                form_digest=w.report.form_digest,
            )
        ],
        reassessment_confirmation_id=assessment.id if assessment else None,
    )
    rt = task(w, "editor_recommendation", w.users["editor"])
    rec_c, _ = confirmation(
        w, w.users["editor"], "recommend_decision", {"recommendation": rec}, work=rt
    )
    ct = task(w, "chief_decision", actor)
    value = dict(
        id=uid(),
        version_id=w.version.id,
        basis_round_id=w.round.id,
        recommendation_confirmation_id=rec_c.id,
        reassessment_confirmation_id=assessment.id if assessment else None,
        decision_code=code,
        revision_kind=kind,
        rationale_private="主编已人工审核所有证据，这里是合成的私密决定依据。" * 2,
        author_letter="这是主编向作者提供的合成正式反馈，包含明确下一步要求。" * 2,
        policy_version=w.flow.policy_version,
        production_assignee=None,
        share_reports_anonymity_reviewed=share,
        public_reports=[],
        revision_request=None,
    )
    if share:
        safe = author_snapshot(w.report)
        value["public_reports"] = [
            dict(
                report_id=w.report.id, ordinal=1, author_snapshot=safe, snapshot_digest=digest(safe)
            )
        ]
    if code == "accept":
        u = w.users["production_editor"]
        value["production_assignee"] = dict(
            id=u.id, name=u.name, email=u.email, role="production_editor"
        )
    if code == "request_revision":
        value["revision_request"] = dict(
            id=uid(),
            decision_id=value["id"],
            request_no=(
                w.db.scalar(
                    select(func.max(RevisionRequest.request_no)).where(
                        RevisionRequest.manuscript_id == w.manuscript.id
                    )
                )
                or 0
            )
            + 1,
            base_version_id=w.version.id,
            planned_draft_version_id=uid(),
            kind=kind,
            rereview_required=kind == "major",
            author_instructions="请作者逐项回应合成评审意见，并重新核对数据、稿件与声明。" * 2,
            due_at=(now() + timedelta(days=7)).isoformat(),
        )
    if mutate:
        mutate(value)
    c, p = confirmation(
        w, actor, "record_decision", {"decision": value, "decision_digest": digest(value)}, work=ct
    )
    row = EditorialDecision(
        id=value["id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        version_id=w.version.id,
        step_run_id=ct.step_run_id,
        basis_round_id=w.round.id,
        recommendation_confirmation_id=rec_c.id,
        reassessment_confirmation_id=value["reassessment_confirmation_id"],
        decision_code=code,
        revision_kind=kind,
        rationale_private=value["rationale_private"],
        author_letter=value["author_letter"],
        policy_version=w.flow.policy_version,
        chief_id=actor.id,
        human_confirmation_id=c.id,
        payload_digest=digest(value),
    )
    return row, value, c, p


def insert_decision(w, *args, **kwargs):
    d, value, c, p = prepare_decision(w, *args, **kwargs)
    w.db.add(d)
    w.db.flush()
    return d, value, c, p


def releases(w, d, value):
    rows = []
    for item in value["public_reports"]:
        row = DecisionReportRelease(manuscript_id=w.manuscript.id, decision_id=d.id, **item)
        w.db.add(row)
        rows.append(row)
    w.db.flush()
    return rows


def request_draft(w, d, value, *, response=True):
    plan = value["revision_request"]
    v = ManuscriptVersion(
        id=plan["planned_draft_version_id"],
        manuscript_id=w.manuscript.id,
        version_no=w.version.version_no + 1,
        created_by=w.users["author"].id,
        title="合成正式修回版本",
    )
    w.db.add(v)
    w.db.flush()
    if response:
        b = FileObject(
            id=uid(),
            journal_id=w.journal.id,
            uploaded_by=w.users["author"].id,
            sha256=digest(v.id),
            byte_size=50,
            media_type="text/plain",
            storage_key="fixture-response-" + v.id,
            original_filename="response.txt",
        )
        w.db.add(b)
        w.db.flush()
        w.db.add(
            VersionFile(
                id=uid(),
                manuscript_id=w.manuscript.id,
                journal_id=w.journal.id,
                version_id=v.id,
                file_object_id=b.id,
                purpose="response",
                visibility="author_editor",
                display_name="response.txt",
                created_by=w.users["author"].id,
            )
        )
        w.db.flush()
    w.flow.draft_version_id = v.id
    w.flow.stage = "author_revision"
    w.db.flush()
    rr = RevisionRequest(
        id=plan["id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        decision_id=d.id,
        request_no=plan["request_no"],
        base_version_id=plan["base_version_id"],
        draft_version_id=v.id,
        kind=plan["kind"],
        rereview_required=plan["rereview_required"],
        author_instructions=plan["author_instructions"],
        due_at=datetime.fromisoformat(plan["due_at"]),
    )
    w.db.add(rr)
    w.db.flush()
    return rr, v


def submit_request(w, rr, v, *, actor=None, freeze=True):
    actor = actor or w.users["author"]
    t = task(w, "author_revision", actor, v, set_current=False)
    data = dict(
        id=rr.id,
        decision_id=rr.decision_id,
        base_version_id=rr.base_version_id,
        draft_version_id=rr.draft_version_id,
        kind=rr.kind,
        rereview_required=rr.rereview_required,
        author_instructions=rr.author_instructions,
        due_at=rr.due_at.isoformat(),
        submitted_version_id=v.id,
    )
    c, p = confirmation(w, actor, "submit_revision", {"revision_request": data}, work=t, version=v)
    if freeze:
        v.content_digest = digest(file_snapshot(w, v))
        v.frozen_at = now()
        w.db.flush()
    rr.status = "submitted"
    rr.submitted_version_id = v.id
    rr.submitted_at = now()
    rr.author_confirmation_id = c.id
    w.db.flush()
    w.flow.current_version_id = v.id
    w.flow.draft_version_id = None
    w.db.flush()
    w.version = v
    return c, p


def assess(w, rr, *, outcome="ready_for_chief"):
    t = task(w, "revision_assessment", w.users["editor"])
    data = dict(
        revision_request_id=rr.id,
        version_id=w.version.id,
        outcome=outcome,
        notes="合成编辑复核，确认本版本修改和逐项回应。" * 2,
        declarations={
            "reviewed_current_version": True,
            "reviewed_response": True,
            "anonymous_material_reviewed": outcome == "rereview",
        },
        base_version_id=rr.base_version_id,
        response_file=file_snapshot(w, w.version)[0],
        basis_round_id=w.round.id,
    )
    c, _ = confirmation(w, w.users["editor"], "assess_revision", {"assessment": data}, work=t)
    return c


def test_full_migration_metadata_and_safe_empty_downgrade(editorial_world):
    w = editorial_world
    # This fixture stops at the E migration; F separately compares the complete
    # latest schema, including these three later tables, against all metadata.
    later_tables = {
        "publishing_proof_packages",
        "publishing_proof_responses",
        "publishing_publication_previews",
        "publishing_dossiers",
        "publishing_dossier_versions",
        "publishing_dossier_checks",
        "publishing_dossier_turns",
    }
    context = MigrationContext.configure(
        w.conn,
        opts={
            "include_object": lambda obj, name, kind, reflected, compare_to: not (
                kind == "table" and name in later_tables
            ),
        },
    )
    assert compare_metadata(context, Base.metadata) == []
    fks = {x["name"] for x in inspect(w.conn).get_foreign_keys("publishing_editorial_decisions")}
    assert {
        "fk_pub_decision_basis_round",
        "fk_pub_decision_recommendation",
        "fk_pub_decision_confirmation",
    } <= fks
    with Operations.context(MigrationContext.configure(w.conn)):
        MIGRATION.downgrade()
    assert not inspect(w.conn).has_table("publishing_editorial_decisions")


@pytest.mark.parametrize("code", ["accept", "reject"])
def test_chief_decision_can_differ_from_editor_recommendation(editorial_world, code):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, code, recommendation="request_revision")
    peer.boundary(w.db)
    assert d.decision_code == code and d.revision_kind is None


def test_anonymous_release_is_exact_safe_author_projection(editorial_world):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, share=True)
    rows = releases(w, d, value)
    peer.boundary(w.db)
    snapshot = rows[0].author_snapshot
    assert set(snapshot) == {"author_text", "answers", "questions"}
    assert set(snapshot["answers"]) == {"rigor"}
    assert "confidential_assessment" not in str(snapshot) and "editor_private_text" not in str(
        snapshot
    )


@pytest.mark.parametrize(
    "change",
    ["private_answer", "private_text", "identity", "wrong_order", "wrong_digest", "wrong_report"],
)
def test_release_rejects_content_not_in_exact_human_approved_safe_snapshot(editorial_world, change):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, share=True)
    data = deepcopy(value["public_reports"][0])
    if change == "private_answer":
        data["author_snapshot"]["answers"]["confidential_assessment"] = w.report.answers_json[
            "confidential_assessment"
        ]
    elif change == "private_text":
        data["author_snapshot"]["editor_private_text"] = w.report.editor_private_text
    elif change == "identity":
        data["author_snapshot"]["reviewer_id"] = w.users["reviewer"].id
    elif change == "wrong_order":
        data["ordinal"] = 2
    elif change == "wrong_digest":
        data["snapshot_digest"] = "0" * 64
    else:
        data["report_id"] = uid()
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.add(DecisionReportRelease(manuscript_id=w.manuscript.id, decision_id=d.id, **data))
            w.db.flush()


def test_missing_approved_release_cannot_commit(editorial_world):
    w = editorial_world
    closed_basis(w)
    with pytest.raises(DBAPIError, match="releases must commit"):
        with w.db.begin_nested():
            insert_decision(w, share=True)
            peer.boundary(w.db)


@pytest.mark.parametrize(
    "change",
    ["letter", "digest", "step", "version", "code", "kind", "stale_revision", "wrong_chief_role"],
)
def test_decision_requires_exact_current_chief_action_target_and_payload(editorial_world, change):
    w = editorial_world
    closed_basis(w)
    d, value, c, p = prepare_decision(
        w, actor=w.users["editor"] if change == "wrong_chief_role" else None
    )
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            if change == "letter":
                d.author_letter += "edited"
            elif change == "digest":
                d.payload_digest = "0" * 64
            elif change == "step":
                d.step_run_id = w.manager_task.step_run_id
            elif change == "version":
                d.version_id = uid()
            elif change == "code":
                d.decision_code = "accept"
            elif change == "kind":
                d.revision_kind = "minor"
            elif change == "stale_revision":
                w.flow.revision += 1
                w.db.flush()
            w.db.add(d)
            w.db.flush()


@pytest.mark.parametrize(
    "table,mutation",
    [
        ("publishing_editorial_decisions", "update"),
        ("publishing_editorial_decisions", "delete"),
        ("publishing_editorial_decisions", "truncate"),
        ("publishing_decision_report_releases", "update"),
        ("publishing_decision_report_releases", "delete"),
        ("publishing_decision_report_releases", "truncate"),
    ],
)
def test_decision_and_release_are_immutable(editorial_world, table, mutation):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, share=True)
    releases(w, d, value)
    peer.boundary(w.db)
    column = "author_letter" if table == "publishing_editorial_decisions" else "snapshot_digest"
    statement = {
        "update": f"UPDATE {table} SET {column}='changed'",
        "delete": f"DELETE FROM {table}",
        "truncate": f"TRUNCATE {table} CASCADE",
    }[mutation]
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.execute(text(statement))


@pytest.mark.parametrize("kind", ["minor", "major"])
def test_formal_revision_creates_new_draft_then_owner_frozen_submission(editorial_world, kind):
    w = editorial_world
    closed_basis(w)
    base = w.version
    d, value, _, _ = insert_decision(w, "request_revision", kind=kind)
    rr, v = request_draft(w, d, value)
    peer.boundary(w.db)
    submit_request(w, rr, v)
    peer.boundary(w.db)
    assert rr.submitted_version_id == v.id != base.id and base.frozen_at is not None
    assert rr.rereview_required == (kind == "major")
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.execute(
                text(
                    "UPDATE publishing_revision_requests SET author_instructions='changed' WHERE id=:id"
                ),
                {"id": rr.id},
            )


def test_missing_planned_revision_request_cannot_commit(editorial_world):
    w = editorial_world
    closed_basis(w)
    with pytest.raises(DBAPIError, match="planned revision request"):
        with w.db.begin_nested():
            insert_decision(w, "request_revision", kind="minor")
            peer.boundary(w.db)


@pytest.mark.parametrize("failure", ["no_response", "not_frozen", "other_actor"])
def test_revision_submission_requires_actual_response_new_frozen_version_and_owner(
    editorial_world, failure
):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, "request_revision", kind="minor")
    rr, v = request_draft(w, d, value, response=failure != "no_response")
    peer.boundary(w.db)
    with pytest.raises(DBAPIError, match="revision submit"):
        with w.db.begin_nested():
            submit_request(
                w,
                rr,
                v,
                actor=w.users["editor"] if failure == "other_actor" else None,
                freeze=failure != "not_frozen",
            )


def test_minor_v2_and_v3_can_use_same_v1_round_with_each_current_reassessment(editorial_world):
    w = editorial_world
    closed_basis(w)
    basis_version = w.round.version_id
    last = None
    for _ in range(2):
        d, value, _, _ = insert_decision(w, "request_revision", kind="minor", assessment=last)
        rr, v = request_draft(w, d, value)
        submit_request(w, rr, v)
        last = assess(w, rr)
        peer.boundary(w.db)
    d, _, _, _ = insert_decision(w, "accept", assessment=last)
    peer.boundary(w.db)
    assert d.version_id == w.version.id != basis_version and w.version.version_no == 3


def test_major_cannot_bridge_old_round_without_new_review(editorial_world):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, "request_revision", kind="major")
    rr, v = request_draft(w, d, value)
    submit_request(w, rr, v)
    a = assess(w, rr)
    with pytest.raises(DBAPIError, match="submitted minor request"):
        with w.db.begin_nested():
            insert_decision(w, "accept", assessment=a)


def test_history_bearing_downgrade_is_refused(editorial_world):
    w = editorial_world
    closed_basis(w)
    insert_decision(w)
    peer.boundary(w.db)
    with pytest.raises(DBAPIError, match="refusing downgrade"):
        with w.db.begin_nested():
            with Operations.context(MigrationContext.configure(w.conn)):
                MIGRATION.downgrade()


@pytest.mark.parametrize("role", ["chief_editor", "production_editor"])
def test_decision_db_conflict_includes_historical_author_email_without_account_link(
    editorial_world, role
):
    w = editorial_world
    closed_basis(w)
    historical_email = w.users["author"].email
    w.users["author"].email = "changed-profile-" + uid() + "@publishing.test"
    w.db.flush()
    w.users[role].email = historical_email.upper()
    w.db.flush()
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            insert_decision(w, "accept" if role == "production_editor" else "reject")


@pytest.mark.parametrize("field", ["editor_private_text", "reviewer_id", "private_answer"])
def test_even_approved_release_snapshot_cannot_expose_non_author_source_fields(
    editorial_world, field
):
    w = editorial_world
    closed_basis(w)

    def inject(value):
        snapshot = value["public_reports"][0]["author_snapshot"]
        if field == "private_answer":
            snapshot["answers"]["confidential_assessment"] = w.report.answers_json[
                "confidential_assessment"
            ]
        else:
            snapshot[field] = (
                w.report.editor_private_text
                if field == "editor_private_text"
                else w.users["reviewer"].id
            )
        value["public_reports"][0]["snapshot_digest"] = digest(snapshot)

    d, value, _, _ = insert_decision(w, share=True, mutate=inject)
    with pytest.raises(DBAPIError, match="anonymous author-only snapshot"):
        with w.db.begin_nested():
            releases(w, d, value)


def test_shared_reports_need_explicit_anonymity_review_in_the_confirmed_payload(editorial_world):
    w = editorial_world
    closed_basis(w)
    with pytest.raises(DBAPIError, match="human anonymity review"):
        with w.db.begin_nested():
            insert_decision(
                w,
                share=True,
                mutate=lambda value: value.update(share_reports_anonymity_reviewed=False),
            )


def test_accept_requires_exact_snapshot_of_current_production_account(editorial_world):
    w = editorial_world
    closed_basis(w)
    with pytest.raises(DBAPIError, match="production assignee"):
        with w.db.begin_nested():
            insert_decision(
                w,
                "accept",
                mutate=lambda value: value["production_assignee"].update(
                    email="wrong@publishing.test"
                ),
            )


@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
def test_requested_revision_plan_is_not_mutable_or_erasable(editorial_world, operation):
    w = editorial_world
    closed_basis(w)
    d, value, _, _ = insert_decision(w, "request_revision", kind="minor")
    request_draft(w, d, value)
    peer.boundary(w.db)
    sql = {
        "update": "UPDATE publishing_revision_requests SET author_instructions='changed instructions'",
        "delete": "DELETE FROM publishing_revision_requests",
        "truncate": "TRUNCATE publishing_revision_requests",
    }[operation]
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.execute(text(sql))
