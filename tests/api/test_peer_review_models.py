"""Real PostgreSQL DDL/guards in random schemas; never updates a shared alembic head.

These synthetic fixtures exercise domain constraints, not application permissions,
actual CAS validation, anonymous serialization or browser workflow acceptance.
"""

import importlib.util
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from time import monotonic, sleep
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apps.api.publishing.db import engine
from apps.api.publishing.domain import checks, review_models  # noqa: F401
from apps.api.publishing.domain.models import (
    ActionProposal,
    Assignment,
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    SubmissionWorkflow,
    VersionAuthor,
    VersionFile,
    WorkItem,
)
from apps.api.publishing.domain.review_models import (
    ReviewInvitation,
    ReviewReport,
    ReviewRound,
    ReviewRoundFile,
)
from apps.api.publishing.models import Base, Journal, Manuscript, Membership, User, now, uid

ROOT = Path(__file__).resolve().parents[2]


def migration(name):
    path = next((ROOT / "infrastructure/migrations/versions").glob(name + "_*.py"))
    spec = importlib.util.spec_from_file_location("peer_review_test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def later_migrations(after):
    """Apply the real current head in complete-schema checks, keeping old fixtures historical."""
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "infrastructure/migrations"))
    scripts = ScriptDirectory.from_config(config)
    chain = list(reversed(list(scripts.walk_revisions(base="base", head="heads"))))
    boundary = next(i for i, revision in enumerate(chain) if revision.revision == after)
    return [revision.module for revision in chain[boundary + 1 :]]


MIGRATIONS = [
    migration(name)
    for name in (
        "3984270ae78e",
        "0002",
        "a99d14733f66",
        "c81b8c41b016",
        "e7b24c91a603",
        "f8a12d4c6e90",
        "09b73e6a1c22",
        "10c84f7a2d31",
    )
]


@pytest.fixture
def review_db():
    schema = "test_review_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        with Operations.context(MigrationContext.configure(connection)):
            for module in MIGRATIONS:
                module.upgrade()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session, connection
        finally:
            session.close()
            transaction.rollback()


def boundary(db):
    """Force deferred constraints just as commit would, then restore transaction mode."""
    db.flush()
    db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def proof(w, actor, action, payload, *, task=None, version=None):
    task = task or w.manager_task
    p = ActionProposal(
        id=uid(),
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        work_item_id=task.id,
        version_id=version or w.version.id,
        action_type=action,
        prepared_by=actor.id,
        responsible_user_id=actor.id,
        base_revision=w.flow.revision,
        policy_version=w.flow.policy_version,
        payload_snapshot=payload,
        evidence_digests={},
        digest="d" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    w.db.add(p)
    w.db.flush()
    c = HumanConfirmation(
        id=uid(),
        manuscript_id=w.manuscript.id,
        proposal_id=p.id,
        responsible_user_id=actor.id,
        session_hash="e" * 64,
        digest=p.digest,
        outcome="confirm",
    )
    w.db.add(c)
    w.db.flush()
    return c


@pytest.fixture
def world_review(review_db):
    return make_world(*review_db)


def make_world(db, conn):
    journal = Journal(id=uid(), name="合成同行评审期刊")
    other_journal = Journal(id=uid(), name="其他隔离期刊")
    db.add_all([journal, other_journal])
    db.flush()
    users = {}
    for role in ("author", "editor", "reviewer", "reviewer_b"):
        user = User(
            id=uid(),
            email=f"{uid()}@publishing.test",
            name="合成" + role,
            password_hash="test-no-login",
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                journal_id=journal.id,
                role="reviewer" if role == "reviewer_b" else role,
            )
        )
        users[role] = user
    db.flush()
    m = Manuscript(
        id=uid(),
        journal_id=journal.id,
        author_id=users["author"].id,
        editor_id=users["editor"].id,
        title="合成审稿数据",
        status="screening",
        workflow_kind="publishing",
    )
    db.add(m)
    db.flush()
    version = ManuscriptVersion(
        id=uid(), manuscript_id=m.id, version_no=1, created_by=users["author"].id, title=m.title
    )
    db.add(version)
    db.flush()
    blob = FileObject(
        id=uid(),
        journal_id=journal.id,
        uploaded_by=users["author"].id,
        sha256="a" * 64,
        byte_size=100,
        media_type="text/plain",
        storage_key="aa/" + "a" * 64,
        original_filename="author-private-name.txt",
    )
    db.add(blob)
    db.flush()
    file = VersionFile(
        id=uid(),
        manuscript_id=m.id,
        journal_id=journal.id,
        version_id=version.id,
        file_object_id=blob.id,
        purpose="blinded_manuscript",
        visibility="reviewer",
        display_name="author-private-name.txt",
        created_by=users["author"].id,
    )
    db.add(file)
    db.add(
        VersionAuthor(
            manuscript_id=m.id,
            version_id=version.id,
            ordinal=0,
            name="合成作者",
            email=users["author"].email,
            corresponding=True,
            linked_user_id=users["author"].id,
        )
    )
    db.flush()
    version.frozen_at = now()
    version.content_digest = "f" * 64
    db.flush()
    step = StepRun(
        id=uid(),
        manuscript_id=m.id,
        version_id=version.id,
        step_key="reviewer_selection",
        cycle_no=1,
    )
    db.add(step)
    db.flush()
    task = WorkItem(
        id=uid(),
        manuscript_id=m.id,
        journal_id=journal.id,
        step_run_id=step.id,
        version_id=version.id,
        kind="reviewer_selection",
        assignee_id=users["editor"].id,
    )
    db.add(task)
    db.flush()
    flow = SubmissionWorkflow(
        manuscript_id=m.id,
        journal_id=journal.id,
        number="POS-" + uid(),
        stage="reviewer_selection",
        current_version_id=version.id,
        current_step_id=step.id,
        assigned_editor_id=users["editor"].id,
    )
    db.add(flow)
    db.add(
        Assignment(
            manuscript_id=m.id,
            journal_id=journal.id,
            user_id=users["editor"].id,
            capability="handling_editor",
            assigned_by=users["editor"].id,
        )
    )
    db.flush()
    return SimpleNamespace(
        db=db,
        conn=conn,
        journal=journal,
        other_journal=other_journal,
        users=users,
        manuscript=m,
        version=version,
        file=file,
        blob=blob,
        manager_task=task,
        flow=flow,
    )


def invite_spec(w, reviewer=None, attempt=1):
    reviewer = reviewer or w.users["reviewer"]
    return dict(
        id=uid(),
        reviewer_id=reviewer.id,
        attempt_no=attempt,
        invitation_snapshot={
            "title": "匿名测试稿件",
            "abstract": "仅合成匿名摘要",
            "instructions": "合成任务",
        },
        content_digest="b" * 64,
        response_due_at=(now() + timedelta(days=2)).isoformat(),
        report_due_at=(now() + timedelta(days=7)).isoformat(),
    )


def open_round(w, *, seal=True, files=True, invitation=None):
    target = dict(
        round_id=uid(),
        round_no=1,
        version_id=w.version.id,
        required_reports=1,
        form_snapshot={"questions": [{"key": "methods", "required": True, "audience": "author"}]},
        form_digest="c" * 64,
        material_digest="a" * 64,
        files=[
            dict(
                version_file_id=w.file.id,
                sha256=w.blob.sha256,
                role="blinded_manuscript",
                display_name="review-manuscript.txt",
            )
        ],
        invitations=[invitation] if invitation else [],
    )
    conf = proof(w, w.users["editor"], "open_review", {"review": target})
    r = ReviewRound(
        id=target["round_id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        version_id=w.version.id,
        round_no=1,
        required_reports=1,
        policy_version=1,
        form_snapshot=target["form_snapshot"],
        form_digest=target["form_digest"],
        material_digest=target["material_digest"],
        opened_by=w.users["editor"].id,
        opening_confirmation_id=conf.id,
    )
    w.db.add(r)
    w.db.flush()
    if files:
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
    if seal:
        r.status = "open"
        r.material_sealed_at = now()
        w.db.flush()
    return r, target, conf


def add_invitation(w, r, item=None, *, proof_action="invite_reviewers", open_conf=None):
    item = item or invite_spec(w)
    payload = dict(
        round_id=r.id,
        round_no=r.round_no,
        version_id=r.version_id,
        required_reports=r.required_reports,
        form_snapshot=r.form_snapshot,
        form_digest=r.form_digest,
        material_digest=r.material_digest,
        files=[
            dict(
                version_file_id=w.file.id,
                sha256=w.blob.sha256,
                role="blinded_manuscript",
                display_name="review-manuscript.txt",
            )
        ],
        invitations=[item],
    )
    conf = open_conf or proof(w, w.users["editor"], proof_action, {"review": payload})
    i = ReviewInvitation(
        id=item["id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        round_id=r.id,
        version_id=w.version.id,
        reviewer_id=item["reviewer_id"],
        attempt_no=item["attempt_no"],
        invited_by=w.users["editor"].id,
        invitation_snapshot=item["invitation_snapshot"],
        content_digest=item["content_digest"],
        policy_version=1,
        response_due_at=__import__("datetime").datetime.fromisoformat(item["response_due_at"]),
        report_due_at=__import__("datetime").datetime.fromisoformat(item["report_due_at"]),
        invitation_confirmation_id=conf.id,
    )
    w.db.add(i)
    w.db.flush()
    step = StepRun(
        id=uid(),
        manuscript_id=w.manuscript.id,
        version_id=w.version.id,
        step_key="respond_review_invitation",
        cycle_no=item["attempt_no"] + (100 if i.reviewer_id == w.users["reviewer_b"].id else 0),
    )
    w.db.add(step)
    w.db.flush()
    task = WorkItem(
        id=uid(),
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        version_id=w.version.id,
        step_run_id=step.id,
        kind="respond_review_invitation",
        assignee_id=i.reviewer_id,
        review_invitation_id=i.id,
    )
    w.db.add(task)
    w.db.flush()
    return i, task


def respond(w, i, task, *, outcome="accept", conflict="none", grant=True, report=True):
    actor = next(u for u in w.users.values() if u.id == i.reviewer_id)
    conf = proof(
        w,
        actor,
        "respond_review_invitation",
        {
            "response": {
                "invitation_id": i.id,
                "outcome": outcome,
                "conflict_status": conflict,
                "notes": "合成人工声明",
            }
        },
        task=task,
    )
    i.status = "accepted" if outcome == "accept" else "declined"
    i.responded_at = now()
    i.conflict_status = conflict
    i.response_notes = "合成人工声明"
    i.response_confirmation_id = conf.id
    if outcome == "accept":
        i.accepted_at = now()
    else:
        i.declined_at = now()
    w.db.flush()
    task.status = "completed"
    task.completed_at = now()
    task.confirmation_id = conf.id
    w.db.flush()
    g = None
    p = None
    t = None
    if outcome == "accept" and grant:
        g = Assignment(
            manuscript_id=w.manuscript.id,
            journal_id=w.journal.id,
            user_id=i.reviewer_id,
            capability="reviewer",
            review_invitation_id=i.id,
            assigned_by=i.reviewer_id,
        )
        w.db.add(g)
        w.db.flush()
    if outcome == "accept" and report:
        r = w.db.get(ReviewRound, i.round_id)
        p = ReviewReport(
            id=uid(),
            manuscript_id=w.manuscript.id,
            invitation_id=i.id,
            form_snapshot=r.form_snapshot,
            form_digest=r.form_digest,
        )
        w.db.add(p)
        w.db.flush()
        s = StepRun(
            id=uid(),
            manuscript_id=w.manuscript.id,
            version_id=w.version.id,
            step_key="submit_review",
            cycle_no=i.attempt_no + (100 if i.reviewer_id == w.users["reviewer_b"].id else 0),
        )
        w.db.add(s)
        w.db.flush()
        t = WorkItem(
            id=uid(),
            manuscript_id=w.manuscript.id,
            journal_id=w.journal.id,
            step_run_id=s.id,
            version_id=w.version.id,
            kind="submit_review",
            assignee_id=i.reviewer_id,
            review_report_id=p.id,
        )
        w.db.add(t)
        w.db.flush()
    return g, p, t


def submit(w, i, p, t):
    actor = next(u for u in w.users.values() if u.id == i.reviewer_id)
    values = {
        "author_text": "合成作者可见评审意见",
        "editor_private_text": "仅供编辑的合成私密意见",
        "answers_json": {"methods": "合成方法评估"},
        "recommendation": "minor_revision",
    }
    conf = proof(
        w,
        actor,
        "submit_review",
        {
            "review_report": {
                "id": p.id,
                "invitation_id": i.id,
                "form_digest": p.form_digest,
                "data": values,
                "content_digest": "f" * 64,
            }
        },
        task=t,
    )
    for key, val in values.items():
        setattr(p, key, val)
    p.revision += 1
    p.status = "submitted"
    p.submitted_at = now()
    p.human_confirmation_id = conf.id
    p.content_digest = "f" * 64
    w.db.flush()
    i.status = "submitted"
    i.completed_at = now()
    i.terminal_confirmation_id = conf.id
    w.db.flush()
    t.status = "completed"
    t.completed_at = now()
    t.confirmation_id = conf.id
    w.db.flush()
    return conf


def test_migration_matches_metadata_and_empty_downgrade(review_db):
    db, conn = review_db
    # Keep the D fixture unchanged for constraint tests; this one explicitly
    # reaches the current head and compares every registered table and column.
    later = later_migrations(MIGRATIONS[-1].revision)
    with Operations.context(MigrationContext.configure(conn)):
        for module in later:
            module.upgrade()
    context = MigrationContext.configure(conn)
    assert compare_metadata(context, Base.metadata) == []
    assert {"fk_pub_review_round_file_round", "fk_pub_review_round_file_version_file"} <= {
        x["name"] for x in inspect(conn).get_foreign_keys("publishing_review_round_files")
    }
    with Operations.context(MigrationContext.configure(conn)):
        for module in reversed(later):
            module.downgrade()
        MIGRATIONS[-1].downgrade()
    assert not inspect(conn).has_table("publishing_review_rounds")


def test_atomic_initialization_seal_and_invitation_acceptance_report_submit(world_review):
    w = world_review
    item = invite_spec(w)
    r, _, c = open_round(w, invitation=item)
    i, t = add_invitation(w, r, item, open_conf=c)
    g, p, report_task = respond(w, i, t)
    submit(w, i, p, report_task)
    boundary(w.db)
    assert i.status == "submitted" and p.status == "submitted" and g.ends_at is None
    assert w.db.get(ReviewRound, r.id).version_id == w.version.id


def test_unsealed_round_cannot_reach_commit_boundary(world_review):
    w = world_review
    with pytest.raises(DBAPIError, match="cannot commit"):
        with w.db.begin_nested():
            open_round(w, seal=False)
            boundary(w.db)


def test_seal_requires_exact_confirmed_file_set(world_review):
    w = world_review
    with pytest.raises(DBAPIError, match="fixed material"):
        with w.db.begin_nested():
            open_round(w, files=False)


@pytest.mark.parametrize("mutation", ["append", "update", "delete", "truncate"])
def test_sealed_round_material_is_immutable(world_review, mutation):
    w = world_review
    r, _, _ = open_round(w)
    commands = {
        "append": (
            "INSERT INTO publishing_review_round_files(id,manuscript_id,round_id,version_id,version_file_id,role,display_name,created_at) VALUES(:id,:m,:r,:v,:f,'blinded_manuscript','review-manuscript.txt',now())",
            dict(id=uid(), m=w.manuscript.id, r=r.id, v=w.version.id, f=w.file.id),
        ),
        "update": (
            "UPDATE publishing_review_round_files SET display_name='changed' WHERE round_id=:r",
            dict(r=r.id),
        ),
        "delete": ("DELETE FROM publishing_review_round_files WHERE round_id=:r", dict(r=r.id)),
        "truncate": ("TRUNCATE publishing_review_round_files", {}),
    }
    sql, args = commands[mutation]
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.execute(text(sql), args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("form_digest", "0" * 64),
        ("required_reports", 2),
        ("version_id", "missing"),
        ("opened_by", "missing"),
    ],
)
def test_round_opening_facts_do_not_mutate(world_review, field, value):
    w = world_review
    r, _, _ = open_round(w)
    with pytest.raises(DBAPIError, match="immutable"):
        with w.db.begin_nested():
            w.db.execute(
                text(f"UPDATE publishing_review_rounds SET {field}=:v WHERE id=:id"),
                dict(v=value, id=r.id),
            )


def test_wrong_action_confirmation_cannot_open_round(world_review):
    w = world_review
    with pytest.raises(DBAPIError, match="confirmation"):
        with w.db.begin_nested():
            c = proof(w, w.users["editor"], "submit", {})
            w.db.add(
                ReviewRound(
                    id=uid(),
                    manuscript_id=w.manuscript.id,
                    journal_id=w.journal.id,
                    version_id=w.version.id,
                    round_no=1,
                    policy_version=1,
                    form_snapshot={},
                    form_digest="a" * 64,
                    material_digest="b" * 64,
                    opened_by=w.users["editor"].id,
                    opening_confirmation_id=c.id,
                )
            )
            w.db.flush()


def test_decline_preserves_attempt_and_allows_reinvite_but_not_duplicate_active(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    respond(w, i, t, outcome="decline", conflict="declared")
    boundary(w.db)
    second, _ = add_invitation(w, r, invite_spec(w, attempt=2))
    boundary(w.db)
    assert i.status == "declined" and second.id != i.id
    with pytest.raises(DBAPIError, match="uq_pub_review_invitation_effective"):
        with w.db.begin_nested():
            add_invitation(w, r, invite_spec(w, attempt=3))


@pytest.mark.parametrize(
    "failure", ["conflict", "other_actor", "stale", "wrong_invitation", "wrong_notes"]
)
def test_acceptance_requires_exact_own_current_no_conflict_response(world_review, failure):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            data = dict(
                invitation_id="wrong" if failure == "wrong_invitation" else i.id,
                outcome="accept",
                conflict_status="declared" if failure == "conflict" else "none",
                notes="expected",
            )
            c = proof(
                w,
                w.users["editor"] if failure == "other_actor" else w.users["reviewer"],
                "respond_review_invitation",
                {"response": data},
                task=t,
            )
            if failure == "stale":
                w.flow.revision += 1
                w.db.flush()
            i.status = "accepted"
            i.accepted_at = now()
            i.responded_at = now()
            i.conflict_status = data["conflict_status"]
            i.response_confirmation_id = c.id
            i.response_notes = "wrong" if failure == "wrong_notes" else "expected"
            w.db.flush()


def test_acceptance_cannot_commit_without_actual_grant_and_report(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    with pytest.raises(DBAPIError, match="atomic grant"):
        with w.db.begin_nested():
            respond(w, i, t, grant=False, report=False)
            boundary(w.db)


def test_pending_invitation_cannot_create_report_or_grant(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, _ = add_invitation(w, r)
    for entity in [
        Assignment(
            manuscript_id=w.manuscript.id,
            journal_id=w.journal.id,
            user_id=i.reviewer_id,
            capability="reviewer",
            review_invitation_id=i.id,
        ),
        ReviewReport(
            manuscript_id=w.manuscript.id,
            invitation_id=i.id,
            form_snapshot=r.form_snapshot,
            form_digest=r.form_digest,
        ),
    ]:
        with pytest.raises(DBAPIError):
            with w.db.begin_nested():
                w.db.add(entity)
                w.db.flush()


@pytest.mark.parametrize("target", ["invitation", "report"])
def test_typed_task_rejects_wrong_recipient_or_version(world_review, target):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    _, p, rt = respond(w, i, t)
    task = t if target == "invitation" else rt
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.add(
                WorkItem(
                    id=uid(),
                    manuscript_id=w.manuscript.id,
                    journal_id=w.journal.id,
                    step_run_id=task.step_run_id,
                    version_id=w.version.id,
                    kind=task.kind,
                    assignee_id=w.users["editor"].id,
                    review_invitation_id=i.id if target == "invitation" else None,
                    review_report_id=p.id if target == "report" else None,
                )
            )
            w.db.flush()


@pytest.mark.parametrize("mutation", ["content", "digest", "target", "private", "form"])
def test_report_submission_must_match_full_confirmed_snapshot(world_review, mutation):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    _, p, rt = respond(w, i, t)
    data = dict(
        author_text="approved",
        editor_private_text="private",
        answers_json={"methods": "approved"},
        recommendation="accept",
    )
    c = proof(
        w,
        w.users["reviewer"],
        "submit_review",
        {
            "review_report": dict(
                id=p.id,
                invitation_id=i.id,
                form_digest=p.form_digest,
                data=data,
                content_digest="f" * 64,
            )
        },
        task=rt,
    )
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            for k, v in data.items():
                setattr(p, k, v)
            p.status = "submitted"
            p.revision += 1
            p.submitted_at = now()
            p.human_confirmation_id = c.id
            p.content_digest = "f" * 64
            if mutation == "content":
                p.author_text = "changed"
            elif mutation == "digest":
                p.content_digest = None
            elif mutation == "target":
                p.invitation_id = uid()
            elif mutation == "private":
                p.editor_private_text = "changed private"
            else:
                p.form_digest = "0" * 64
            w.db.flush()


@pytest.mark.parametrize("mutation", ["update", "delete", "truncate", "reopen"])
def test_submitted_report_and_invitation_history_cannot_change(world_review, mutation):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    _, p, rt = respond(w, i, t)
    submit(w, i, p, rt)
    boundary(w.db)
    sql = {
        "update": "UPDATE publishing_review_reports SET author_text='changed' WHERE id=:id",
        "delete": "DELETE FROM publishing_review_reports WHERE id=:id",
        "truncate": "TRUNCATE publishing_review_reports",
        "reopen": "UPDATE publishing_review_invitations SET status='accepted',completed_at=NULL WHERE id=:inv",
    }[mutation]
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            w.db.execute(text(sql), dict(id=p.id, inv=i.id))


def test_finish_review_closes_exact_reports_and_revokes_grant(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    g, p, rt = respond(w, i, t)
    submit(w, i, p, rt)
    c = proof(
        w,
        w.users["editor"],
        "finish_review",
        {
            "review_closure": dict(
                round_id=r.id,
                reason="合成评审已齐",
                submitted_report_ids=[p.id],
                cancel_invitation_ids=[],
            )
        },
    )
    g.ends_at = now()
    w.db.flush()
    r.status = "closed"
    r.closed_at = now()
    r.closure_reason = "合成评审已齐"
    r.closing_confirmation_id = c.id
    w.db.flush()
    boundary(w.db)
    assert r.status == "closed"
    with pytest.raises(DBAPIError, match="immutable"):
        with w.db.begin_nested():
            w.db.execute(
                text("UPDATE publishing_review_rounds SET closure_reason='changed' WHERE id=:id"),
                {"id": r.id},
            )


def test_finish_cannot_fake_target_or_ignore_active_grant(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    _, p, rt = respond(w, i, t)
    submit(w, i, p, rt)
    c = proof(
        w,
        w.users["editor"],
        "finish_review",
        {
            "review_closure": dict(
                round_id=r.id,
                reason="claimed",
                submitted_report_ids=[p.id],
                cancel_invitation_ids=[],
            )
        },
    )
    with pytest.raises(DBAPIError, match="outstanding work"):
        with w.db.begin_nested():
            r.status = "closed"
            r.closed_at = now()
            r.closure_reason = "claimed"
            r.closing_confirmation_id = c.id
            w.db.flush()


def test_data_bearing_downgrade_is_refused(world_review):
    w = world_review
    open_round(w)
    with pytest.raises(DBAPIError, match="refusing downgrade"):
        with w.db.begin_nested():
            with Operations.context(MigrationContext.configure(w.conn)):
                MIGRATIONS[-1].downgrade()


def cancel(w, i, task, *, grant=None, report=None, report_task=None, cleanup=True):
    submitted = w.db.scalars(
        select(ReviewReport.id)
        .join(ReviewInvitation, ReviewInvitation.id == ReviewReport.invitation_id)
        .where(ReviewInvitation.round_id == i.round_id, ReviewReport.status == "submitted")
        .order_by(ReviewReport.id)
    ).all()
    c = proof(
        w,
        w.users["editor"],
        "cancel_review_invitation",
        {
            "review_closure": dict(
                round_id=i.round_id,
                reason="合成人工撤销",
                submitted_report_ids=list(submitted),
                cancel_invitation_ids=[i.id],
            )
        },
    )
    i.status = "cancelled"
    i.cancelled_at = now()
    i.terminal_confirmation_id = c.id
    w.db.flush()
    if cleanup:
        if grant:
            grant.ends_at = now()
            w.db.flush()
        if report:
            report.status = "withdrawn"
            report.revision += 1
            report.updated_at = now()
            w.db.flush()
        target = report_task or task
        target.status = "cancelled"
        target.confirmation_id = c.id
        w.db.flush()
    return c


@pytest.mark.parametrize("accepted", [False, True])
def test_explicit_cancellation_preserves_attempt_and_revokes_only_unsubmitted_work(
    world_review, accepted
):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    g = p = rt = None
    if accepted:
        g, p, rt = respond(w, i, t)
    cancel(w, i, t, grant=g, report=p, report_task=rt)
    boundary(w.db)
    assert i.status == "cancelled"
    if accepted:
        assert g.ends_at is not None and p.status == "withdrawn"
    next_inv, _ = add_invitation(w, r, invite_spec(w, attempt=2))
    boundary(w.db)
    assert next_inv.status == "pending"


def test_cancelled_acceptance_cannot_commit_with_live_grant_or_private_draft(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    g, p, rt = respond(w, i, t)
    with pytest.raises(DBAPIError, match="active grant or draft"):
        with w.db.begin_nested():
            cancel(w, i, t, grant=g, report=p, report_task=rt, cleanup=False)
            boundary(w.db)


def test_opening_invitation_list_must_be_created_before_commit(world_review):
    w = world_review
    with pytest.raises(DBAPIError, match="invitations must all commit"):
        with w.db.begin_nested():
            open_round(w, invitation=invite_spec(w))
            boundary(w.db)


def test_submitted_invitation_cannot_reinvite_same_person_or_cancel(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    g, p, rt = respond(w, i, t)
    submit(w, i, p, rt)
    boundary(w.db)
    with pytest.raises(DBAPIError, match="uq_pub_review_invitation_effective"):
        with w.db.begin_nested():
            add_invitation(w, r, invite_spec(w, attempt=2))
    with pytest.raises(DBAPIError, match="immutable"):
        with w.db.begin_nested():
            cancel(w, i, t, grant=g, report=p, report_task=rt)


@pytest.mark.parametrize("target", ["response", "report"])
def test_typed_task_cannot_complete_using_unrelated_human_confirmation(world_review, target):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    if target == "report":
        _, _, t = respond(w, i, t)
    with pytest.raises(DBAPIError):
        with w.db.begin_nested():
            t.status = "completed"
            t.completed_at = now()
            t.confirmation_id = r.opening_confirmation_id
            w.db.flush()


def test_grant_cannot_be_reactivated_or_recreated_after_end(world_review):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    g, p, rt = respond(w, i, t)
    submit(w, i, p, rt)
    g.ends_at = now()
    w.db.flush()
    with pytest.raises(DBAPIError, match="reactivate"):
        with w.db.begin_nested():
            w.db.execute(
                text("UPDATE publishing_assignments SET ends_at=NULL WHERE id=:id"), {"id": g.id}
            )
    with pytest.raises(DBAPIError, match="recreated"):
        with w.db.begin_nested():
            w.db.add(
                Assignment(
                    manuscript_id=w.manuscript.id,
                    journal_id=w.journal.id,
                    user_id=i.reviewer_id,
                    capability="reviewer",
                    review_invitation_id=i.id,
                )
            )
            w.db.flush()


@pytest.mark.parametrize("failure", ["changed_role", "author_conflict"])
def test_acceptance_checks_current_reviewer_role_and_known_author_conflict(world_review, failure):
    w = world_review
    r, _, _ = open_round(w)
    i, t = add_invitation(w, r)
    if failure == "changed_role":
        w.db.scalar(
            select(Membership).where(
                Membership.user_id == i.reviewer_id, Membership.journal_id == w.journal.id
            )
        ).role = "editor"
    else:
        w.manuscript.author_id = i.reviewer_id
    w.db.flush()
    with pytest.raises(DBAPIError, match="independent no-conflict"):
        with w.db.begin_nested():
            respond(w, i, t)


def test_timestamp_snapshot_accepts_equivalent_iso_z_timezone(world_review):
    w = world_review
    r, _, _ = open_round(w)
    item = invite_spec(w)
    item["response_due_at"] = item["response_due_at"].replace("+00:00", "Z")
    item["report_due_at"] = item["report_due_at"].replace("+00:00", "Z")
    i, _ = add_invitation(w, r, item)
    boundary(w.db)
    assert i.response_due_at.tzinfo is not None


def test_invitation_rejects_a_changed_fixed_material_snapshot(world_review):
    w = world_review
    r, _, _ = open_round(w)
    item = invite_spec(w)
    wrong = proof(
        w,
        w.users["editor"],
        "invite_reviewers",
        {
            "review": dict(
                round_id=r.id,
                round_no=1,
                version_id=w.version.id,
                required_reports=1,
                form_snapshot=r.form_snapshot,
                form_digest=r.form_digest,
                material_digest=r.material_digest,
                files=[],
                invitations=[item],
            )
        },
    )
    with pytest.raises(DBAPIError, match="confirmed target"):
        with w.db.begin_nested():
            add_invitation(w, r, item, open_conf=wrong)


def test_two_connections_cannot_append_during_initialization_seal_or_after_commit(
    record_testsuite_property,
):
    """Committed synthetic schema only; initialization itself can never commit.

    B cannot see A's initializing/sealing row, so its append is rejected rather than
    joining the atomic file set. Once A commits open, B is rejected by the sealed gate.
    An explicit lock assay then proves the file guard waits on the committed parent
    row (55P03 lock timeout), rather than checking its state without synchronization.
    """
    schema = "test_review_race_" + uuid4().hex
    assert re.fullmatch(r"test_review_race_[0-9a-f]{32}", schema)
    committed_setup = False
    observations = []
    try:
        with engine.connect() as setup:
            tx = setup.begin()
            setup.execute(text(f'CREATE SCHEMA "{schema}"'))
            setup.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            with Operations.context(MigrationContext.configure(setup)):
                for module in MIGRATIONS:
                    module.upgrade()
            s = Session(
                bind=setup, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            w = make_world(s, setup)
            s.commit()
            tx.commit()
            s.close()
            committed_setup = True
        with engine.connect() as first, ThreadPoolExecutor(max_workers=1) as pool:
            tx = first.begin()
            first.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            s = Session(
                bind=first, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            w.db = s
            w.conn = first
            r, _, _ = open_round(w, seal=False)
            params = dict(id=uid(), m=w.manuscript.id, r=r.id, v=w.version.id, f=w.file.id)

            def append(phase):
                started = monotonic()
                with engine.connect() as second:
                    other_tx = second.begin()
                    second.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                    second.execute(text("SET LOCAL lock_timeout='300ms'"))
                    second.execute(text("SET LOCAL statement_timeout='3s'"))
                    try:
                        second.execute(
                            text(
                                "INSERT INTO publishing_review_round_files(id,manuscript_id,round_id,version_id,version_file_id,role,display_name,created_at) VALUES(:id,:m,:r,:v,:f,'blinded_manuscript','review-manuscript.txt',clock_timestamp())"
                            ),
                            {**params, "id": uid()},
                        )
                    except DBAPIError as exc:
                        return dict(
                            phase=phase,
                            sqlstate=exc.orig.sqlstate,
                            seconds=round(monotonic() - started, 4),
                        )
                    finally:
                        other_tx.rollback()
                raise AssertionError("concurrent append unexpectedly succeeded")

            observations.append(pool.submit(append, "initializing_uncommitted").result(timeout=5))
            assert observations[-1]["sqlstate"] == "P0001"
            r.status = "open"
            r.material_sealed_at = now()
            s.flush()
            observations.append(pool.submit(append, "sealed_uncommitted").result(timeout=5))
            assert observations[-1]["sqlstate"] == "P0001"
            boundary(s)
            s.commit()
            tx.commit()
            s.close()
            observations.append(pool.submit(append, "sealed_committed").result(timeout=5))
            assert observations[-1]["sqlstate"] == "P0001"
            tx = first.begin()
            first.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            first.execute(
                text("SELECT id FROM publishing_review_rounds WHERE id=:id FOR UPDATE"),
                {"id": r.id},
            )
            observations.append(pool.submit(append, "sealed_parent_locked").result(timeout=5))
            assert observations[-1]["sqlstate"] == "55P03"
            tx.rollback()
            observations.append(
                pool.submit(append, "sealed_parent_lock_released").result(timeout=5)
            )
            assert observations[-1]["sqlstate"] == "P0001"
            with first.begin():
                first.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                assert first.scalar(text("SELECT count(*) FROM publishing_review_round_files")) == 1
                assert first.scalar(text("SELECT status FROM publishing_review_rounds")) == "open"
        record_testsuite_property("peer_review_concurrency_schema", schema)
        record_testsuite_property("peer_review_concurrency_order_and_results", str(observations))
    finally:
        if committed_setup:
            assert re.fullmatch(r"test_review_race_[0-9a-f]{32}", schema)
            with engine.begin() as cleanup:
                cleanup.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_response_deadline_is_hard_but_overdue_report_can_be_human_submitted(world_review):
    w = world_review
    r, _, _ = open_round(w)
    item = invite_spec(w)
    item["response_due_at"] = (now() + timedelta(seconds=2)).isoformat()
    item["report_due_at"] = (now() + timedelta(seconds=2.5)).isoformat()
    i, t = add_invitation(w, r, item)
    _, p, rt = respond(w, i, t)
    remaining = (i.report_due_at - now()).total_seconds()
    if remaining > 0:
        sleep(remaining + 0.05)
    submit(w, i, p, rt)
    boundary(w.db)
    assert i.report_due_at < now() and p.status == "submitted"


def test_pending_expiration_is_deterministic_without_fabricated_human_approval(world_review):
    w = world_review
    r, _, _ = open_round(w)
    item = invite_spec(w)
    item["response_due_at"] = (now() + timedelta(seconds=2)).isoformat()
    item["report_due_at"] = (now() + timedelta(days=1)).isoformat()
    i, t = add_invitation(w, r, item)
    remaining = (i.response_due_at - now()).total_seconds()
    if remaining > 0:
        sleep(remaining + 0.05)
    with pytest.raises(DBAPIError, match="own current confirmation"):
        with w.db.begin_nested():
            respond(w, i, t)
    i.status = "expired"
    w.db.flush()
    t.status = "cancelled"
    w.db.flush()
    boundary(w.db)
    assert i.response_confirmation_id is None and i.terminal_confirmation_id is None
