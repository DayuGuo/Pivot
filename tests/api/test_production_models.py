"""F append-only production facts in rolled-back, synthetic PostgreSQL schemas.

These tests exercise SQL contracts rather than CAS bytes, UI, policy service or real mail.
The complete migration chain is compared to the actual imported model registry.
"""

import importlib.util
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.domain import production_models
from apps.api.publishing.domain.models import (
    ActionProposal,
    Assignment,
    FileObject,
    HumanConfirmation,
    StepRun,
    VersionFile,
)
from apps.api.publishing.domain.production_models import (
    ProofPackage,
    ProofResponse,
    PublicationPreview,
)
from apps.api.publishing.models import Base, now, uid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "_production_editorial_helpers", ROOT / "tests/api/test_editorial_decision_models.py"
)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
MIGRATION = e.peer.migration("12e06b9c4f53")
digest = e.digest


@pytest.fixture
def production_world():
    assert Path(production_models.__file__).resolve().is_relative_to(ROOT)
    generator = e.editorial_world.__wrapped__()
    w = next(generator)
    try:
        with Operations.context(MigrationContext.configure(w.conn)):
            MIGRATION.upgrade()
        e.closed_basis(w)
        w.acceptance, _, _, _ = e.insert_decision(w, "accept")
        w.flow.accepted_version_id = w.version.id
        w.manuscript.status = "accepted"
        w.production = w.users["production_editor"]
        w.db.add(
            Assignment(
                manuscript_id=w.manuscript.id,
                journal_id=w.journal.id,
                user_id=w.production.id,
                capability="production",
                assigned_by=w.users["chief_editor"].id,
            )
        )
        w.flow.production_editor_id = w.production.id
        w.db.flush()
        e.peer.boundary(w.db)
        yield w
    finally:
        generator.close()


def metadata(w):
    # Independent expected public projection, not SQL-helper output.
    return dict(
        schema_version=1,
        title=w.version.title,
        abstract=w.version.abstract,
        language=w.version.language,
        article_type=w.version.article_type,
        keywords=w.version.metadata_json.get("keywords", []),
        authors=[
            dict(name="合成作者", orcid=None, affiliations=[], corresponding=True, contributions=[])
        ],
        funding_statement=w.version.metadata_json.get("funding_statement", ""),
    )


def blob(w, content="synthetic proof A", **overrides):
    row = FileObject(
        id=uid(),
        journal_id=w.journal.id,
        uploaded_by=w.production.id,
        sha256=digest(content),
        byte_size=len(content.encode()),
        media_type="text/plain",
        storage_key="synthetic/" + digest(content),
        original_filename="deduplicated-private-original.txt",
        check_method="utf8_text_safety",
        scan_status="validated_text",
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    w.db.add(row)
    w.db.flush()
    return row


def file_snapshot(b, name):
    return dict(
        id=b.id,
        filename=name,
        sha256=b.sha256,
        byte_size=b.byte_size,
        media_type=b.media_type,
    )


def confirmation(w, actor, action, stage, payload, *, package_id, previous=None, mutate=None):
    work = e.task(w, stage, actor)
    step = w.db.get(StepRun, work.step_run_id)
    step.outcome_json = {"package_id": previous if action == "send_proof" else package_id}
    w.db.flush()
    envelope = dict(
        action=action,
        stage=stage,
        version=None,
        schema_version=1,
        synthetic_only=True,
        **payload,
    )
    if mutate:
        mutate(envelope)
    p = ActionProposal(
        id=uid(),
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        work_item_id=work.id,
        version_id=w.version.id,
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
        session_hash="b" * 64,
        digest=p.digest,
        outcome="confirm",
    )
    w.db.add(c)
    w.db.flush()
    work.status, work.completed_at, work.confirmation_id = "completed", now(), c.id
    step.status, step.completed_at, step.confirmation_id = "completed", now(), c.id
    step.outcome_json = {"action": action, "package_id": package_id}
    if action == "send_proof":
        step.outcome_json["previous_package_id"] = previous
    w.db.flush()
    return c, p


def prepare_package(w, *, previous=None, b=None, actor=None, mutate=None, row_mutate=None):
    actor = actor or w.production
    b = b or blob(w)
    count = w.db.scalar(select(func.count()).select_from(ProofPackage))
    value = dict(
        id=uid(),
        accepted_version_id=w.version.id,
        acceptance_decision_id=w.acceptance.id,
        package_no=count + 1,
        file=file_snapshot(b, "proof-bound-name.txt"),
        metadata_snapshot=metadata(w),
        production_user_id=actor.id,
    )
    value["material_digest"] = digest(value)
    c, p = confirmation(
        w,
        actor,
        "send_proof",
        "production",
        {
            "proof_package": value,
            "previous_package_id": previous.id if previous else None,
            "input": {"declarations": {"metadata_reviewed": True, "proof_reviewed": True}},
        },
        package_id=value["id"],
        previous=previous.id if previous else None,
        mutate=mutate,
    )
    row = ProofPackage(
        id=value["id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        accepted_version_id=w.version.id,
        acceptance_decision_id=w.acceptance.id,
        package_no=value["package_no"],
        file_object_id=b.id,
        display_name=value["file"]["filename"],
        metadata_snapshot=deepcopy(value["metadata_snapshot"]),
        material_digest=value["material_digest"],
        production_user_id=actor.id,
        human_confirmation_id=c.id,
    )
    if row_mutate:
        row_mutate(row)
    return row, value, c, p


def package(w, **kwargs):
    row, value, _, _ = prepare_package(w, **kwargs)
    w.db.add(row)
    e.peer.boundary(w.db)
    return row, value


def prepare_response(w, pkg, snapshot, *, outcome="approve", notes="", actor=None, mutate=None):
    actor = actor or w.users["author"]
    value = dict(
        id=uid(),
        package_id=pkg.id,
        accepted_version_id=pkg.accepted_version_id,
        outcome=outcome,
        notes=notes,
        declarations={"proof_reviewed": True},
        package_digest=pkg.material_digest,
    )
    c, p = confirmation(
        w,
        actor,
        "confirm_proof",
        "author_proof",
        dict(proof_package=snapshot, proof_response=value),
        package_id=pkg.id,
        mutate=mutate,
    )
    return (
        ProofResponse(
            id=value["id"],
            manuscript_id=w.manuscript.id,
            package_id=pkg.id,
            author_id=actor.id,
            outcome=outcome,
            notes=notes,
            human_confirmation_id=c.id,
        ),
        value,
        c,
        p,
    )


def response(w, pkg, snapshot, **kwargs):
    row, _, _, _ = prepare_response(w, pkg, snapshot, **kwargs)
    w.db.add(row)
    e.peer.boundary(w.db)
    return row


def prepare_preview(w, pkg, approved, snapshot, *, mutate=None, row_mutate=None, actor=None):
    actor = actor or w.production
    value = dict(
        id=uid(),
        accepted_version_id=pkg.accepted_version_id,
        package_id=pkg.id,
        proof_response_id=approved.id,
        metadata_snapshot=deepcopy(pkg.metadata_snapshot),
        file=deepcopy(snapshot["file"]),
        production_user_id=actor.id,
        local_only=True,
    )
    value["content_digest"] = digest(value)
    c, p = confirmation(
        w,
        actor,
        "prepare_local_preview",
        "preview_confirmation",
        dict(
            preview=value,
            input={"declarations": {"metadata_reviewed": True, "approved_proof_reviewed": True}},
        ),
        package_id=pkg.id,
        mutate=mutate,
    )
    row = PublicationPreview(
        id=value["id"],
        manuscript_id=w.manuscript.id,
        journal_id=w.journal.id,
        accepted_version_id=pkg.accepted_version_id,
        package_id=pkg.id,
        proof_response_id=approved.id,
        metadata_snapshot=deepcopy(pkg.metadata_snapshot),
        file_object_id=pkg.file_object_id,
        display_name=pkg.display_name,
        content_digest=value["content_digest"],
        production_user_id=actor.id,
        human_confirmation_id=c.id,
    )
    if row_mutate:
        row_mutate(row)
    return row, value, c, p


def rejects(w, row, match):
    with pytest.raises(DBAPIError, match=match):
        w.db.add(row)
        e.peer.boundary(w.db)


def test_complete_chain_metadata_has_zero_drift(production_world):
    w = production_world
    # The F fixture remains historical; the complete-head assertion also applies
    # the later private-dossier migration in this rolled-back test schema.
    with Operations.context(MigrationContext.configure(w.conn)):
        for module in e.peer.later_migrations(MIGRATION.revision):
            module.upgrade()
    assert compare_metadata(MigrationContext.configure(w.conn), Base.metadata) == []
    assert [
        len(cls.__table__.columns) for cls in (ProofPackage, ProofResponse, PublicationPreview)
    ] == [13, 8, 13]
    fks = inspect(w.conn).get_foreign_keys("publishing_publication_previews")
    assert any(
        f["constrained_columns"] == ["proof_response_id", "manuscript_id", "package_id"]
        for f in fks
    )
    assert any(
        f["constrained_columns"] == ["package_id", "manuscript_id", "accepted_version_id"]
        for f in fks
    )


def test_approved_local_preview_binds_same_immutable_package(production_world):
    w = production_world
    before = w.db.scalar(select(func.count()).select_from(VersionFile))
    pkg, snapshot = package(w)
    approved = response(w, pkg, snapshot)
    preview, _, _, _ = prepare_preview(w, pkg, approved, snapshot)
    w.db.add(preview)
    e.peer.boundary(w.db)
    assert w.manuscript.status == "accepted"
    assert w.flow.accepted_version_id == pkg.accepted_version_id == preview.accepted_version_id
    assert preview.file_object_id == pkg.file_object_id
    assert snapshot["file"]["filename"] == "proof-bound-name.txt"
    assert (
        snapshot["file"]["filename"] != w.db.get(FileObject, pkg.file_object_id).original_filename
    )
    assert w.db.scalar(select(func.count()).select_from(VersionFile)) == before
    assert "email" not in str(preview.metadata_snapshot)
    assert "declarations" not in str(preview.metadata_snapshot)
    assert w.db.scalar(
        text("SELECT publishing_production_metadata(:id)"), {"id": w.version.id}
    ) == metadata(w)


def test_corrections_allow_restore_older_bytes_not_same_previous(production_world):
    w = production_world
    a = blob(w, "proof A")
    first, s1 = package(w, b=a)
    response(
        w,
        first,
        s1,
        outcome="request_corrections",
        notes="请按作者逐项检查后的具体意见修改本次校样内容。",
    )
    second, s2 = package(w, previous=first, b=blob(w, "proof B"))
    response(
        w,
        second,
        s2,
        outcome="request_corrections",
        notes="本次改动不适合，请恢复此前已经检查过的相关表述。",
    )
    third, s3 = package(w, previous=second, b=a)
    approved = response(w, third, s3)
    preview, _, _, _ = prepare_preview(w, third, approved, s3)
    w.db.add(preview)
    e.peer.boundary(w.db)
    assert [first.package_no, second.package_no, third.package_no] == [1, 2, 3]
    assert third.file_object_id == first.file_object_id


@pytest.mark.parametrize(
    "which",
    ["metadata", "file", "declaration", "private_version", "previous", "package_no", "acceptance"],
)
def test_send_requires_exact_snapshot_and_declarations(production_world, which):
    w = production_world

    def mutate(p):
        if which == "metadata":
            p["proof_package"]["metadata_snapshot"]["authors"][0]["email"] = (
                "private@publishing.test"
            )
        elif which == "file":
            p["proof_package"]["file"]["download_url"] = "/must-not-freeze"
        elif which == "declaration":
            p["input"]["declarations"]["proof_reviewed"] = "true"
        elif which == "private_version":
            p["version"] = {"id": w.version.id, "files": []}
        elif which == "previous":
            p.pop("previous_package_id")
        elif which == "package_no":
            p["proof_package"]["package_no"] = 8
        else:
            p["proof_package"]["acceptance_decision_id"] = uid()

    row, _, _, _ = prepare_package(w, mutate=mutate)
    rejects(w, row, "production action|send proof|first proof|proof package number")


@pytest.mark.parametrize(
    "which", ["foreign_journal", "unvalidated", "wrong_media", "untrusted_check"]
)
def test_proof_requires_local_same_journal_validated_text(production_world, which):
    w = production_world
    overrides = {
        "foreign_journal": {"journal_id": w.other_journal.id},
        "unvalidated": {"scan_status": "unscanned"},
        "wrong_media": {"media_type": "application/pdf"},
        "untrusted_check": {"check_method": "none"},
    }
    row, _, _, _ = prepare_package(w, b=blob(w, **overrides[which]))
    rejects(w, row, "validated same-journal text")


@pytest.mark.parametrize("actor", ["editor", "chief_editor", "author"])
def test_send_requires_actual_production_role_and_assignment(production_world, actor):
    w = production_world
    row, _, _, _ = prepare_package(w, actor=w.users[actor])
    rejects(w, row, "production actor")


def test_current_role_reassignment_is_permitted_without_old_accept_person_binding(production_world):
    w = production_world
    new = w.users["reviewer_b"]
    from apps.api.publishing.models import Membership

    membership = w.db.scalar(
        select(Membership).where(
            Membership.user_id == new.id, Membership.journal_id == w.journal.id
        )
    )
    membership.role = "production_editor"
    w.db.add(
        Assignment(
            manuscript_id=w.manuscript.id,
            journal_id=w.journal.id,
            user_id=new.id,
            capability="production",
            assigned_by=w.users["chief_editor"].id,
        )
    )
    w.db.flush()
    pkg, _ = package(w, actor=new)
    assert pkg.production_user_id != w.production.id


@pytest.mark.parametrize(
    "which", ["different_hash", "short_notes", "non_author", "missing_review", "changed_metadata"]
)
def test_author_must_review_exact_package(production_world, which):
    w = production_world
    pkg, snapshot = package(w)

    def mutate(p):
        if which == "different_hash":
            p["proof_package"]["file"]["sha256"] = "d" * 64
        elif which == "missing_review":
            p["proof_response"]["declarations"]["proof_reviewed"] = False
        elif which == "changed_metadata":
            p["proof_package"]["metadata_snapshot"]["title"] = "新标题"

    row, _, _, _ = prepare_response(
        w,
        pkg,
        snapshot,
        actor=w.users["reviewer"] if which == "non_author" else None,
        outcome="request_corrections" if which == "short_notes" else "approve",
        notes="too short" if which == "short_notes" else "",
        mutate=mutate,
    )
    rejects(w, row, "author response|ck_pub_proof_response_notes")


def test_package_only_one_author_response(production_world):
    w = production_world
    pkg, snapshot = package(w)
    response(w, pkg, snapshot)
    row, _, _, _ = prepare_response(w, pkg, snapshot)
    rejects(w, row, "uq_pub_proof_response_once")


@pytest.mark.parametrize(
    "which", ["unchanged_bytes", "previous_approved", "missing_previous", "wrong_previous"]
)
def test_new_package_requires_exact_returned_predecessor(production_world, which):
    w = production_world
    pkg, snapshot = package(w)
    response(
        w,
        pkg,
        snapshot,
        outcome="approve" if which == "previous_approved" else "request_corrections",
        notes="这是作者人工审核的明确更正意见，需要更新校样。",
    )
    previous = None if which == "missing_previous" else pkg
    b = (
        w.db.get(FileObject, pkg.file_object_id)
        if which == "unchanged_bytes"
        else blob(w, "updated proof")
    )
    row, _, _, _ = prepare_package(
        w,
        previous=previous,
        b=b,
        mutate=(lambda p: p.update(previous_package_id=uid()))
        if which == "wrong_previous"
        else None,
    )
    rejects(w, row, "exact preceding returned")


@pytest.mark.parametrize(
    "which",
    [
        "not_approved",
        "file_substitution",
        "metadata_change",
        "remote_preview",
        "missing_review",
        "package_mismatch",
    ],
)
def test_preview_requires_approved_unchanged_local_package(production_world, which):
    w = production_world
    pkg, snapshot = package(w)
    approved = response(
        w,
        pkg,
        snapshot,
        outcome="request_corrections" if which == "not_approved" else "approve",
        notes="作者检查后明确要求根据更正意见更新本次校样内容。",
    )
    other = blob(w, "substitution") if which == "file_substitution" else None

    def mutate(p):
        if which == "remote_preview":
            p["preview"]["local_only"] = False
        if which == "missing_review":
            p["input"]["declarations"]["approved_proof_reviewed"] = False
        if which == "package_mismatch":
            p["preview"]["package_id"] = uid()

    def row_mutate(row):
        if which == "file_substitution":
            row.file_object_id = other.id
        if which == "metadata_change":
            row.metadata_snapshot = dict(row.metadata_snapshot, title="未审批新标题")

    row, _, _, _ = prepare_preview(w, pkg, approved, snapshot, mutate=mutate, row_mutate=row_mutate)
    rejects(w, row, "same-package author approval|preview must bind")


@pytest.mark.parametrize(
    "table",
    ["publishing_proof_packages", "publishing_proof_responses", "publishing_publication_previews"],
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE", "TRUNCATE"])
def test_all_production_history_is_immutable(production_world, table, operation):
    w = production_world
    pkg, snapshot = package(w)
    approved = response(w, pkg, snapshot)
    preview, _, _, _ = prepare_preview(w, pkg, approved, snapshot)
    w.db.add(preview)
    e.peer.boundary(w.db)
    sql = f"DELETE FROM {table}" if operation == "DELETE" else f"{operation} {table}"
    if operation == "UPDATE":
        sql += " SET manuscript_id=manuscript_id"
    with pytest.raises(DBAPIError, match="immutable|cannot truncate"):
        w.db.execute(text(sql))


def test_downgrade_refuses_actual_proof_history(production_world):
    w = production_world
    package(w)
    with Operations.context(MigrationContext.configure(w.conn)):
        with pytest.raises(DBAPIError, match="refusing downgrade"):
            MIGRATION.downgrade()


@pytest.mark.parametrize("action", ["send_proof", "prepare_local_preview"])
def test_production_db_conflict_checks_historical_author_email(production_world, action):
    w = production_world
    if action == "prepare_local_preview":
        pkg, snapshot = package(w)
        approved = response(w, pkg, snapshot)
    historical = w.users["author"].email
    w.users["author"].email = uid() + "@new-profile.publishing.test"
    w.db.flush()
    w.production.email = historical.upper()
    w.db.flush()
    if action == "send_proof":
        row, _, _, _ = prepare_package(w)
    else:
        row, _, _, _ = prepare_preview(w, pkg, approved, snapshot)
    rejects(w, row, "production actor|preview must bind")


@pytest.mark.parametrize(
    "changed",
    [
        "revision",
        "policy",
        "accepted_version",
        "step_pointer",
        "stage",
        "envelope_stage",
        "typed_task_kind",
    ],
)
def test_f_confirmation_must_bind_exact_current_workflow(production_world, changed):
    w = production_world
    row, _, _, proposal = prepare_package(
        w,
        mutate=(lambda p: p.update(stage="chief_decision"))
        if changed == "envelope_stage"
        else None,
    )
    if changed == "revision":
        w.flow.revision += 1
    elif changed == "policy":
        w.flow.policy_version += 1
    elif changed == "accepted_version":
        w.flow.accepted_version_id = None
    elif changed == "step_pointer":
        w.flow.current_step_id = w.manager_task.step_run_id
    elif changed == "stage":
        w.flow.stage = "preview_confirmation"
    elif changed == "typed_task_kind":
        from apps.api.publishing.domain.models import WorkItem

        work = w.db.get(WorkItem, proposal.work_item_id)
        work.kind = "author_proof"
    w.db.flush()
    rejects(w, row, "production action")
