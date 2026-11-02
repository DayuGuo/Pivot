"""Sequential human checks over frozen versions; all operations use actual APIs/DB."""

import base64
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain.checks import CheckRun
from apps.api.publishing.domain.models import (
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    SubmissionWorkflow,
    WorkItem,
)
from apps.api.publishing.models import Membership
from tests.api.test_publishing_intake import (
    URL,
    complete_data,
    detail,
    draft,
    fill,
    prepare,
    request_id,
)


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    return tmp_path / "files"


def confirm(client, data, proposal):
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, login):
    login("author")
    data = fill(client, draft(client))
    confirm(client, data, prepare(client, data))
    return data["id"]


def check_payload(stage, outcome="pass"):
    declarations = {"materials_reviewed": True}
    if stage == "similarity_review":
        declarations["report_reviewed"] = True
    if stage == "technical_screening":
        declarations["anonymous_material_reviewed"] = True
    if stage == "chief_scope":
        declarations["scope_matches"] = True
    if stage == "editor_quality":
        declarations["quality_sufficient"] = True
    return {
        "outcome": outcome,
        "notes": "已由当前负责人阅读实际合成材料并记录本地测试结论。",
        "reason": "需要作者补交或修正合成材料。" if outcome == "return" else "",
        "declarations": declarations,
    }


def stage_proposal(client, mid, payload, action="record_check"):
    data = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": action,
            "data": payload,
        },
    )
    assert response.status_code == 200, response.text
    # Preparation alone must never complete the current work item or stage.
    assert detail(client, mid)["stage"] == data["stage"]
    return data, response.json()


def pass_stage(client, mid, payload=None):
    data = detail(client, mid)
    payload = payload or check_payload(data["stage"])
    before, proposal = stage_proposal(client, mid, payload)
    confirm(client, before, proposal)
    return detail(client, mid)


def upload_report(client, mid, content="合成相似度人工测试报告；非外部检测服务结果。"):
    data = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/reports",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "file": {
                "filename": "synthetic-report.txt",
                "purpose": "similarity_report",
                "content_base64": base64.b64encode(content.encode()).decode(),
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["report"]


def test_full_screening_chief_assignment_editor_quality_are_real_confirmed_gates(
    client, login, db, world
):
    mid = submit(client, login)
    login("editor")
    assert detail(client, mid)["staff_review"]["kind"] == "precheck_completeness"
    data = pass_stage(client, mid)
    assert data["stage"] == "similarity_review"
    report = upload_report(client, mid)
    assert client.get(report["download_url"]).content.startswith("合成相似度".encode())
    payload = check_payload("similarity_review")
    payload["file_object_id"] = report["id"]
    data = pass_stage(client, mid, payload)
    assert data["stage"] == "technical_screening"
    assert pass_stage(client, mid)["stage"] == "chief_scope"
    # A precheck assignment does not own the chief's task.
    assert detail(client, mid)["allowed_actions"] == []
    login("chief_editor")
    assert pass_stage(client, mid)["stage"] == "assign_editor"
    data = detail(client, mid)
    candidates = data["staff_review"]["eligible_editors"]
    assert world.users["editor"].id in [u["id"] for u in candidates]
    before, proposal = stage_proposal(
        client,
        mid,
        {"editor_id": world.users["editor"].id, "notes": "合成本刊责任编辑分派"},
        "assign_editor",
    )
    assert confirm(client, before, proposal)["stage"] == "editor_quality"
    login("editor")
    assert pass_stage(client, mid)["stage"] == "reviewer_selection"
    assert detail(client, mid)["allowed_actions"] == []  # Next slice is not a fake button.
    checks = db.scalars(select(CheckRun).where(CheckRun.manuscript_id == mid)).all()
    assert len(checks) == 5 and all(c.finalized_at and c.human_confirmation_id for c in checks)
    assert all(c.check_method == "manual_review" for c in checks)
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 7
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(WorkItem)
            .where(WorkItem.manuscript_id == mid, WorkItem.status == "pending")
        )
        == 1
    )
    login("author")
    assert detail(client, mid)["stage"] == "reviewer_selection"
    assert client.get(report["download_url"]).status_code == 404
    assert detail(client, mid)["staff_review"] is None


@pytest.mark.parametrize(
    "stage",
    [
        "precheck_completeness",
        "similarity_review",
        "technical_screening",
        "chief_scope",
        "editor_quality",
    ],
)
def test_no_missing_manual_declaration_or_wrong_role_can_prepare_pass(client, login, stage, world):
    mid = submit(client, login)
    login("editor")
    if stage != "precheck_completeness":
        pass_stage(client, mid)
    if stage in {"technical_screening", "chief_scope", "editor_quality"}:
        report = upload_report(client, mid)
        finding = check_payload("similarity_review")
        finding["file_object_id"] = report["id"]
        pass_stage(client, mid, finding)
    if stage in {"chief_scope", "editor_quality"}:
        pass_stage(client, mid)
        login("chief_editor")
    if stage == "editor_quality":
        pass_stage(client, mid)
        before, proposal = stage_proposal(
            client,
            mid,
            {"editor_id": world.users["editor"].id, "notes": "合成责任编辑分派"},
            "assign_editor",
        )
        confirm(client, before, proposal)
        login("editor")
    assert detail(client, mid)["stage"] == stage
    data = detail(client, mid)
    payload = {"outcome": "pass", "notes": "未确认读过资料", "declarations": {}}
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": "record_check",
            "data": payload,
        },
    )
    assert response.status_code == 422
    login("author")
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": "record_check",
            "data": check_payload(stage),
        },
    )
    assert response.status_code == 403


def test_similarity_requires_current_actual_report_and_modified_report_expires_proposal(
    client, login, db, private_storage
):
    mid = submit(client, login)
    login("editor")
    pass_stage(client, mid)
    data = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": "record_check",
            "data": check_payload("similarity_review"),
        },
    )
    assert response.status_code == 422
    report = upload_report(client, mid)
    payload = check_payload("similarity_review")
    payload["file_object_id"] = report["id"]
    before, proposal = stage_proposal(client, mid, payload)
    blob = db.get(FileObject, report["id"])
    Path(private_storage / blob.storage_key).write_bytes(b"x" * blob.byte_size)
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": before["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert detail(client, mid)["stage"] == "similarity_review"
    assert (
        db.scalar(select(func.count()).select_from(CheckRun).where(CheckRun.manuscript_id == mid))
        == 1
    )


def test_return_creates_new_version_preserves_frozen_history_and_rechecks_new_material(
    client, login, db
):
    mid = submit(client, login)
    login("editor")
    old = detail(client, mid)["version"]
    payload = check_payload("precheck_completeness", "return")
    before, proposal = stage_proposal(client, mid, payload)
    assert confirm(client, before, proposal)["stage"] == "author_revision"
    login("author")
    data = detail(client, mid)
    assert data["version"]["version_no"] == 2 and not data["version"]["frozen_at"]
    assert data["return_request"]["return_to"] == "precheck_completeness"
    assert "补交" in data["return_request"]["reason"]
    assert not data["version"]["data"]["declarations"]["originality"]
    assert db.get(ManuscriptVersion, old["id"]).frozen_at
    values = complete_data()
    values["title"] = "作者修正后的合成稿件"
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={"request_id": request_id(), "expected_revision": data["revision"], "data": values},
    )
    assert response.status_code == 200, response.text
    data = detail(client, mid)
    assert confirm(client, data, prepare(client, data))["stage"] == "precheck_completeness"
    assert db.get(SubmissionWorkflow, mid).current_version_id == data["version"]["id"]
    assert db.get(ManuscriptVersion, old["id"]).title == old["data"]["title"]
    steps = db.scalars(
        select(StepRun)
        .where(StepRun.manuscript_id == mid, StepRun.step_key == "precheck_completeness")
        .order_by(StepRun.cycle_no)
    ).all()
    assert [s.cycle_no for s in steps] == [1, 2]
    assert steps[0].status == "completed" and steps[1].status == "pending"


def test_role_change_after_prepare_blocks_confirm(client, login, db, world):
    mid = submit(client, login)
    login("editor")
    data, proposal = stage_proposal(client, mid, check_payload("precheck_completeness"))
    db.execute(
        update(Membership)
        .where(Membership.user_id == world.users["editor"].id)
        .values(role="reviewer")
    )
    db.commit()
    # CSRF/session belongs to same user, but the new role has no editorial capability.
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code in {403, 404}
    assert (
        db.scalar(select(func.count()).select_from(CheckRun).where(CheckRun.manuscript_id == mid))
        == 0
    )


def test_known_coauthor_does_not_gain_access_and_cannot_be_auto_assigned_to_approve(
    client, login, db, world
):
    login("author")
    created = draft(client)
    values = complete_data()
    values["authors"].append(
        {
            "name": world.users["editor"].name,
            "email": world.users["editor"].email,
            "orcid": None,
            "affiliations": [],
            "contributions": [],
            "corresponding": False,
        }
    )
    # First complete the standard files, then store the known editorial coauthor.
    data = fill(client, created)
    response = client.patch(
        f"{URL}/manuscripts/{data['id']}/intake",
        json={"request_id": request_id(), "expected_revision": data["revision"], "data": values},
    )
    assert response.status_code == 200, response.text
    data = detail(client, data["id"])
    proposal = prepare(client, data)
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 409  # No independent editor configured in this test journal.
    assert detail(client, data["id"])["stage"] == "author_draft"
    assert not db.get(ManuscriptVersion, data["version"]["id"]).frozen_at
    login("editor")
    assert client.get(f"{URL}/manuscripts/{data['id']}").status_code == 404
