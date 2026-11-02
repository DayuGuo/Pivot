"""Check DTOs and PostgreSQL guards in rolled-back, randomly named temporary schemas.

This module never upgrades the shared database's alembic_version or changes its
public tables; only the new migration executes inside an isolated transaction/schema.
"""

import importlib.util
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from apps.api.publishing.db import engine
from apps.api.publishing.domain.checks import (
    CHECK_KINDS,
    CheckInput,
    CheckMaterial,
    CheckPreparationError,
    CheckRun,
    prepare_check,
)
from apps.api.publishing.domain.models import (
    ActionProposal,
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    WorkItem,
)
from apps.api.publishing.models import Base, Journal, Manuscript, User, now, uid

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "infrastructure/migrations/versions/09b73e6a1c22_publishing_checks.py"
)
# tests/api -> repository is parents[2]. No downloaded modules are executed.
spec = importlib.util.spec_from_file_location("checks_migration_under_test", MIGRATION)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def material(kind="precheck_completeness"):
    value = {
        "manuscript_id": uid(),
        "journal_id": uid(),
        "version_id": uid(),
        "step_run_id": uid(),
        "step_key": kind,
        "data": {
            "title": "合成环境研究稿件",
            "abstract": "这是用于验证完整材料人工预审的合成摘要，不含真实稿件或个人数据。" * 3,
            "keywords": ["环境"],
            "authors": [
                {"name": "合成作者", "email": "example@publishing.test", "corresponding": True}
            ],
            "declarations": {
                "originality": True,
                "copyright": True,
                "competing_interests": "none",
                "ethics": "not_applicable",
            },
        },
        "files": [
            {
                "id": uid(),
                "purpose": "manuscript",
                "sha256": "a" * 64,
                "visibility": "author_editor",
            },
            {
                "id": uid(),
                "purpose": "blinded_manuscript",
                "sha256": "b" * 64,
                "visibility": "reviewer",
            },
        ],
    }
    if kind == "similarity_review":
        value["report"] = {
            "id": uid(),
            "journal_id": value["journal_id"],
            "sha256": "c" * 64,
            "byte_size": 100,
            "media_type": "text/plain",
            "scan_status": "validated_text",
            "check_method": "utf8_text_safety",
            "original_filename": "synthetic-report.txt",
        }
    return value


def payload(kind="precheck_completeness", context=None):
    value = {
        "outcome": "pass",
        "notes": "负责人已人工核对合成材料。",
        "declarations": {"materials_reviewed": True},
    }
    if kind == "similarity_review":
        value["file_object_id"] = context["report"]["id"]
        value["declarations"]["report_reviewed"] = True
    elif kind == "technical_screening":
        value["declarations"]["anonymous_material_reviewed"] = True
    elif kind == "chief_scope":
        value["declarations"]["scope_matches"] = True
    elif kind == "editor_quality":
        value["declarations"]["quality_sufficient"] = True
    return value


@pytest.mark.parametrize("kind", CHECK_KINDS)
def test_all_supported_checks_prepare_only_typed_manual_evidence(kind):
    context = material(kind)
    prepared = prepare_check(kind, payload(kind, context), context)
    assert prepared.kind == kind
    assert prepared.check_method == "manual_review"
    assert prepared.requires_human_confirmation is True
    assert prepared.evidence_json["automatic_similarity_detection"] is False
    assert prepared.evidence_json["version_id"] == context["version_id"]
    assert prepared.evidence_json["missing_requirements"] == []
    assert "human_confirmation_id" not in prepared.model_dump()


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_manual_review_is_an_explicit_boolean_not_model_or_string_inference(value):
    proposed = payload()
    proposed["declarations"]["materials_reviewed"] = value
    with pytest.raises(ValidationError):
        CheckInput.model_validate(proposed)


@pytest.mark.parametrize(
    "field", ["prepared_by", "human_confirmation_id", "stage", "role", "check_method"]
)
def test_payload_cannot_supply_authority_or_detector_method(field):
    proposed = payload()
    proposed[field] = "injected"
    with pytest.raises(ValidationError):
        prepare_check("precheck_completeness", proposed, material())


@pytest.mark.parametrize("kind", CHECK_KINDS)
def test_return_requires_reason_and_preserves_finding(kind):
    context = material(kind)
    proposed = {**payload(kind, context), "outcome": "return", "reason": "  请补充可核对证据。  "}
    prepared = prepare_check(kind, proposed, context)
    assert prepared.outcome == "return" and prepared.reason == "请补充可核对证据。"
    proposed["reason"] = "  "
    with pytest.raises(ValidationError):
        prepare_check(kind, proposed, context)


def test_completeness_finding_does_not_silently_ignore_missing_declarations():
    context = material()
    context["data"]["declarations"]["originality"] = False
    with pytest.raises(CheckPreparationError, match="必需项"):
        prepare_check("precheck_completeness", payload(), context)
    returned = prepare_check(
        "precheck_completeness", {**payload(), "outcome": "return", "reason": "缺声明"}, context
    )
    assert any(
        m["field"] == "declarations.originality"
        for m in returned.evidence_json["missing_requirements"]
    )


@pytest.mark.parametrize(
    "change", ["missing_report", "wrong_id", "wrong_journal", "not_reviewed", "unvalidated_report"]
)
def test_similarity_binds_real_same_journal_validated_report_and_explicit_review(change):
    context = material("similarity_review")
    proposed = payload("similarity_review", context)
    if change == "missing_report":
        context["report"] = None
    elif change == "wrong_id":
        proposed["file_object_id"] = uid()
    elif change == "wrong_journal":
        context["report"]["journal_id"] = uid()
    elif change == "not_reviewed":
        proposed["declarations"]["report_reviewed"] = False
    else:
        context["report"]["check_method"] = "automatic_plagiarism_detection"
    with pytest.raises((CheckPreparationError, ValidationError)):
        prepare_check("similarity_review", proposed, context)


@pytest.mark.parametrize(
    "kind,field",
    [
        ("technical_screening", "anonymous_material_reviewed"),
        ("chief_scope", "scope_matches"),
        ("editor_quality", "quality_sufficient"),
    ],
)
def test_pass_requires_the_responsible_manual_declaration(kind, field):
    context = material(kind)
    proposed = payload(kind, context)
    proposed["declarations"][field] = False
    with pytest.raises(CheckPreparationError):
        prepare_check(kind, proposed, context)


def test_blinded_material_must_actually_be_reviewer_visible_and_step_must_match():
    context = material("technical_screening")
    proposed = payload("technical_screening", context)
    context["files"][1]["visibility"] = "author_editor"
    with pytest.raises(CheckPreparationError, match="盲审文件"):
        prepare_check("technical_screening", proposed, context)
    with pytest.raises(CheckPreparationError, match="当前步骤"):
        prepare_check("chief_scope", proposed, context)
    context["files"].append(context["files"][0].copy())
    with pytest.raises(ValidationError):
        CheckMaterial.model_validate(context)


@pytest.fixture
def checks_db():
    """Real PG migration under a rolled-back schema; shared head stays untouched."""
    schema = "test_check_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        Base.metadata.create_all(
            connection,
            tables=[t for t in Base.metadata.sorted_tables if t.name != "publishing_check_runs"],
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session, connection
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def check_world(checks_db):
    db, connection = checks_db
    journal, other = Journal(id=uid(), name="合成检查期刊"), Journal(id=uid(), name="其他期刊")
    actor = User(
        id=uid(),
        email=f"{uid()}@publishing.test",
        name="合成人工负责人",
        password_hash="unused-test-hash",
    )
    db.add_all([journal, other, actor])
    db.flush()
    manuscript = Manuscript(
        id=uid(),
        journal_id=journal.id,
        author_id=actor.id,
        editor_id=None,
        title="合成稿件",
        status="submitted",
        workflow_kind="publishing",
    )
    second = Manuscript(
        id=uid(),
        journal_id=journal.id,
        author_id=actor.id,
        editor_id=None,
        title="第二稿件",
        status="submitted",
        workflow_kind="publishing",
    )
    db.add_all([manuscript, second])
    db.flush()
    version = ManuscriptVersion(
        id=uid(), manuscript_id=manuscript.id, version_no=1, created_by=actor.id, frozen_at=now()
    )
    other_version = ManuscriptVersion(
        id=uid(), manuscript_id=second.id, version_no=1, created_by=actor.id, frozen_at=now()
    )
    sibling_version = ManuscriptVersion(
        id=uid(), manuscript_id=manuscript.id, version_no=2, created_by=actor.id, frozen_at=now()
    )
    db.add_all([version, other_version, sibling_version])
    db.flush()
    step = StepRun(
        id=uid(),
        manuscript_id=manuscript.id,
        version_id=version.id,
        step_key="precheck_completeness",
        cycle_no=1,
    )
    other_step = StepRun(
        id=uid(),
        manuscript_id=second.id,
        version_id=other_version.id,
        step_key="precheck_completeness",
        cycle_no=1,
    )
    db.add_all([step, other_step])
    db.flush()
    task = WorkItem(
        id=uid(),
        manuscript_id=manuscript.id,
        journal_id=journal.id,
        step_run_id=step.id,
        version_id=version.id,
        kind=step.step_key,
        assignee_id=actor.id,
    )
    db.add(task)
    db.flush()
    proposal = ActionProposal(
        id=uid(),
        manuscript_id=manuscript.id,
        journal_id=journal.id,
        work_item_id=task.id,
        version_id=version.id,
        action_type="check_pass",
        prepared_by=actor.id,
        responsible_user_id=actor.id,
        base_revision=1,
        policy_version=1,
        payload_snapshot={},
        evidence_digests={},
        digest="c" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    db.add(proposal)
    db.flush()
    confirmation = HumanConfirmation(
        id=uid(),
        manuscript_id=manuscript.id,
        proposal_id=proposal.id,
        responsible_user_id=actor.id,
        session_hash="d" * 64,
        digest=proposal.digest,
        outcome="confirm",
    )
    db.add(confirmation)
    db.flush()
    return SimpleNamespace(
        db=db,
        connection=connection,
        journal=journal,
        other_journal=other,
        actor=actor,
        manuscript=manuscript,
        version=version,
        other_version=other_version,
        sibling_version=sibling_version,
        step=step,
        other_step=other_step,
        task=task,
        proposal=proposal,
        confirmation=confirmation,
    )


def row(world, **changes):
    values = dict(
        id=uid(),
        manuscript_id=world.manuscript.id,
        journal_id=world.journal.id,
        version_id=world.version.id,
        step_run_id=world.step.id,
        kind="precheck_completeness",
        outcome="pass",
        notes="合成材料人工检查",
        prepared_by=world.actor.id,
    )
    values.update(changes)
    return CheckRun(**values)


def test_migration_creates_composite_fks_unique_finalized_index_and_reversible_empty_table(
    checks_db,
):
    db, connection = checks_db
    inspector = inspect(connection)
    keys = {f["name"]: f for f in inspector.get_foreign_keys("publishing_check_runs")}
    assert keys["fk_pub_check_file_journal"]["constrained_columns"] == [
        "file_object_id",
        "journal_id",
    ]
    for name in ("fk_pub_check_version", "fk_pub_check_step", "fk_pub_check_confirmation"):
        assert "manuscript_id" in keys[name]["constrained_columns"]
    unique = next(
        i
        for i in inspector.get_indexes("publishing_check_runs")
        if i["name"] == "uq_pub_check_finalized_step"
    )
    assert unique["unique"] and "finalized_at IS NOT NULL" in str(unique["dialect_options"])
    with Operations.context(MigrationContext.configure(connection)):
        migration.downgrade()
    assert not inspect(connection).has_table("publishing_check_runs")


@pytest.mark.parametrize(
    "change",
    [
        "cross_version",
        "cross_step",
        "same_manuscript_wrong_version",
        "wrong_kind",
        "cross_journal",
        "return_without_reason",
        "automatic_method",
        "blank_notes",
        "unconfirmed_final",
        "confirmation_without_final",
    ],
)
def test_db_rejects_wrong_relationships_and_invalid_findings(check_world, change):
    world = check_world
    overrides = {
        "cross_version": {"version_id": world.other_version.id},
        "cross_step": {"step_run_id": world.other_step.id},
        "same_manuscript_wrong_version": {"version_id": world.sibling_version.id},
        "wrong_kind": {"kind": "chief_scope"},
        "cross_journal": {"journal_id": world.other_journal.id},
        "return_without_reason": {"outcome": "return", "reason": " "},
        "automatic_method": {"check_method": "automatic_similarity"},
        "blank_notes": {"notes": " "},
        "unconfirmed_final": {"finalized_at": now()},
        "confirmation_without_final": {"human_confirmation_id": world.confirmation.id},
    }[change]
    with pytest.raises(DBAPIError):
        with world.db.begin_nested():
            world.db.add(row(world, **overrides))
            world.db.flush()


def test_finalized_check_is_immutable_and_one_per_step(check_world):
    world = check_world
    finalized = row(world, human_confirmation_id=world.confirmation.id, finalized_at=now())
    world.db.add(finalized)
    world.db.flush()
    assert (
        world.db.scalar(select(CheckRun.id).where(CheckRun.step_run_id == world.step.id))
        == finalized.id
    )
    for sql in [
        "UPDATE publishing_check_runs SET notes='changed' WHERE id=:id",
        "DELETE FROM publishing_check_runs WHERE id=:id",
        "TRUNCATE publishing_check_runs",
    ]:
        with pytest.raises(DBAPIError, match="immutable"):
            with world.db.begin_nested():
                world.db.execute(text(sql), {"id": finalized.id})
    second_proposal = ActionProposal(
        id=uid(),
        manuscript_id=world.manuscript.id,
        journal_id=world.journal.id,
        work_item_id=world.task.id,
        version_id=world.version.id,
        action_type="check_pass",
        prepared_by=world.actor.id,
        responsible_user_id=world.actor.id,
        base_revision=1,
        policy_version=1,
        payload_snapshot={},
        evidence_digests={},
        digest="f" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    world.db.add(second_proposal)
    world.db.flush()
    second_confirmation = HumanConfirmation(
        id=uid(),
        manuscript_id=world.manuscript.id,
        proposal_id=second_proposal.id,
        responsible_user_id=world.actor.id,
        session_hash="d" * 64,
        digest=second_proposal.digest,
        outcome="confirm",
    )
    world.db.add(second_confirmation)
    world.db.flush()
    with pytest.raises(DBAPIError, match="uq_pub_check_finalized_step"):
        with world.db.begin_nested():
            world.db.add(
                row(world, human_confirmation_id=second_confirmation.id, finalized_at=now())
            )
            world.db.flush()
    # Multiple unfinalized preparation rows do not claim the step was passed.
    world.db.add_all([row(world), row(world)])
    world.db.flush()
    assert len(world.db.scalars(select(CheckRun)).all()) == 3
    with pytest.raises(DBAPIError, match="refusing downgrade"):
        with world.db.begin_nested():
            with Operations.context(MigrationContext.configure(world.connection)):
                migration.downgrade()


@pytest.mark.parametrize(
    "invalid",
    [
        "digest",
        "proposal_version",
        "returned_confirmation",
        "unfrozen_version",
        "proposal_responsible",
        "prepared_attribution",
    ],
)
def test_db_requires_confirmation_of_matching_version_and_responsible_step(check_world, invalid):
    world = check_world
    if invalid == "digest":
        world.confirmation.digest = "e" * 64
    elif invalid == "proposal_version":
        world.proposal.version_id = world.sibling_version.id
    elif invalid == "returned_confirmation":
        world.confirmation.outcome = "return"
    elif invalid == "unfrozen_version":
        world.version.frozen_at = None
    else:
        other_actor = User(
            id=uid(),
            email=f"{uid()}@publishing.test",
            name="其他合成负责人",
            password_hash="unused",
        )
        world.db.add(other_actor)
        world.db.flush()
        if invalid == "proposal_responsible":
            world.proposal.responsible_user_id = other_actor.id
        else:
            world.proposal.prepared_by = other_actor.id
    world.db.flush()
    with pytest.raises(DBAPIError, match="matching responsible|frozen submission"):
        with world.db.begin_nested():
            world.db.add(
                row(world, human_confirmation_id=world.confirmation.id, finalized_at=now())
            )
            world.db.flush()


def test_similarity_report_is_independent_and_rejects_cross_journal_file(check_world):
    world = check_world
    world.step.step_key = "similarity_review"
    world.db.flush()
    foreign = FileObject(
        id=uid(),
        journal_id=world.other_journal.id,
        uploaded_by=world.actor.id,
        sha256="e" * 64,
        byte_size=20,
        media_type="text/plain",
        storage_key="sha256-" + "e" * 64,
        original_filename="report.txt",
    )
    world.db.add(foreign)
    world.db.flush()
    for report_id in [None, foreign.id]:
        with pytest.raises(DBAPIError):
            with world.db.begin_nested():
                world.db.add(row(world, kind="similarity_review", file_object_id=report_id))
                world.db.flush()
    local = FileObject(
        id=uid(),
        journal_id=world.journal.id,
        uploaded_by=world.actor.id,
        sha256="f" * 64,
        byte_size=20,
        media_type="text/plain",
        storage_key="sha256-" + "f" * 64,
        original_filename="local-report.txt",
    )
    world.db.add(local)
    world.db.flush()
    check = row(world, kind="similarity_review", file_object_id=local.id)
    world.db.add(check)
    world.db.flush()
    assert check.file_object_id == local.id
    assert not world.db.execute(
        text("SELECT 1 FROM publishing_version_files WHERE version_id=:id"),
        {"id": world.version.id},
    ).first()
