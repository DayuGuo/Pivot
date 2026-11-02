"""Security regression for human screening, version-bound reports and assignments."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.checks import CheckRun
from apps.api.publishing.domain.models import (
    Assignment,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    WorkItem,
)
from apps.api.publishing.models import Membership, User
from tests.api.test_publishing_intake import (
    URL,
    complete_data,
    detail,
    draft,
    fill,
    prepare,
    request_id,
)
from tests.api.test_publishing_screening import (
    check_payload,
    confirm,
    pass_stage,
    stage_proposal,
    submit,
    upload_report,
)


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def count(db, model, mid):
    return db.scalar(select(func.count()).select_from(model).where(model.manuscript_id == mid))


def attempt_proposal(client, mid, payload, action="record_check"):
    data = detail(client, mid)
    return client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": action,
            "data": payload,
        },
    )


def attempt_confirm(client, data, proposal, request=None):
    return client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request or request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )


def similarity(client, login):
    mid = submit(client, login)
    login("editor")
    pass_stage(client, mid)
    return mid


def technical(client, login):
    mid = similarity(client, login)
    report = upload_report(client, mid)
    payload = {**check_payload("similarity_review"), "file_object_id": report["id"]}
    pass_stage(client, mid, payload)
    return mid, report


def assignment_stage(client, login):
    mid, report = technical(client, login)
    pass_stage(client, mid)
    login("chief_editor")
    pass_stage(client, mid)
    return mid, report


def test_same_journal_report_is_not_authority_for_another_manuscript(client, login, db):
    first = similarity(client, login)
    first_report = upload_report(client, first, "此报告只属于第一篇稿件。")
    second = similarity(client, login)
    before = detail(client, second)
    payload = {**check_payload("similarity_review"), "file_object_id": first_report["id"]}
    assert attempt_proposal(client, second, payload).status_code == 404
    assert client.get(f"{URL}/manuscripts/{second}/reports/{first_report['id']}").status_code == 404
    assert count(db, CheckRun, second) == 1
    assert detail(client, second)["revision"] == before["revision"]
    login("author")
    assert client.get(first_report["download_url"]).status_code == 404
    assert first_report["id"] not in json.dumps(detail(client, first))


def test_replacing_report_invalidates_proposal_without_confirming_or_advancing(client, login, db):
    mid = similarity(client, login)
    report = upload_report(client, mid, "第一份尚未确认的报告")
    before, proposal = stage_proposal(
        client, mid, {**check_payload("similarity_review"), "file_object_id": report["id"]}
    )
    confirmations = count(db, HumanConfirmation, mid)
    replacement = upload_report(client, mid, "负责人替换后的新报告，必须重新审核")
    assert replacement["id"] != report["id"]
    response = attempt_confirm(client, before, proposal)
    assert response.status_code == 409, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    assert count(db, CheckRun, mid) == 1
    assert detail(client, mid)["stage"] == "similarity_review"
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()["status"] == "expired"


def test_returned_v2_cannot_reuse_v1_report_as_its_own_evidence(client, login, db):
    mid, report = technical(client, login)
    old = detail(client, mid)["version"]
    before, proposal = stage_proposal(client, mid, check_payload("technical_screening", "return"))
    confirm(client, before, proposal)
    login("author")
    data = detail(client, mid)
    assert data["version"]["id"] != old["id"]
    assert not data["version"]["data"]["declarations"]["originality"]
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "data": complete_data(),
        },
    )
    assert response.status_code == 200, response.text
    data = detail(client, mid)
    confirm(client, data, prepare(client, data))
    login("editor")
    assert detail(client, mid)["stage"] == "precheck_completeness"
    pass_stage(client, mid)
    assert detail(client, mid)["staff_review"]["report"] is None
    response = attempt_proposal(
        client, mid, {**check_payload("similarity_review"), "file_object_id": report["id"]}
    )
    assert response.status_code == 404, response.text
    # An authorized editor can inspect historical evidence, but cannot certify V2 with it.
    assert client.get(report["download_url"]).status_code == 200
    assert db.get(ManuscriptVersion, old["id"]).frozen_at
    checks = db.scalars(select(CheckRun).where(CheckRun.manuscript_id == mid)).all()
    assert len(checks) == 4
    assert all(c.version_id == old["id"] for c in checks if c.kind == "similarity_review")


def test_next_responsible_role_withdrawal_rolls_back_confirmation_and_completed_step(
    client, login, db, world
):
    mid, _ = technical(client, login)
    before, proposal = stage_proposal(client, mid, check_payload("technical_screening"))
    confirmations = count(db, HumanConfirmation, mid)
    checks = count(db, CheckRun, mid)
    db.execute(
        update(Membership)
        .where(Membership.user_id == world.users["chief_editor"].id)
        .values(role="reviewer")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    response = attempt_confirm(client, before, proposal)
    assert response.status_code == 409, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    assert count(db, CheckRun, mid) == checks
    data = detail(client, mid)
    assert data["stage"] == before["stage"] and data["revision"] == before["revision"]
    task = db.get(WorkItem, before["own_tasks"][0]["id"])
    step = db.get(StepRun, task.step_run_id)
    assert task.status == step.status == "pending"
    assert task.confirmation_id is None and step.confirmation_id is None
    assert data["timeline"][-1]["status"] == "pending"


def test_selected_editor_role_change_after_prepare_cannot_create_assignment(
    client, login, db, world
):
    mid, _ = assignment_stage(client, login)
    before, proposal = stage_proposal(
        client,
        mid,
        {"editor_id": world.users["editor"].id, "notes": "分派前人工确认责任编辑"},
        "assign_editor",
    )
    confirmations = count(db, HumanConfirmation, mid)
    db.execute(
        update(Membership)
        .where(Membership.user_id == world.users["editor"].id)
        .values(role="reviewer")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    response = attempt_confirm(client, before, proposal)
    assert response.status_code in {409, 422}, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    assert not db.scalar(
        select(Assignment).where(
            Assignment.manuscript_id == mid, Assignment.capability == "handling_editor"
        )
    )
    assert detail(client, mid)["stage"] == "assign_editor"


def test_known_coauthor_editor_is_neither_candidate_nor_forgeable_assignment(
    client, login, db, world
):
    coauthor = User(
        email=f"zz-coauthor-{request_id()}@synthetic.test",
        name="同时担任编辑的合成署名作者",
        password_hash="unused-no-login",
    )
    db.add(coauthor)
    db.flush()
    db.add(Membership(user_id=coauthor.id, journal_id=world.journal.id, role="editor"))
    db.commit()
    login("author")
    data = fill(client, draft(client))
    values = complete_data()
    values["authors"].append(
        {"name": coauthor.name, "email": coauthor.email, "corresponding": False}
    )
    response = client.patch(
        f"{URL}/manuscripts/{data['id']}/intake",
        json={"request_id": request_id(), "expected_revision": data["revision"], "data": values},
    )
    assert response.status_code == 200, response.text
    mid = data["id"]
    data = detail(client, mid)
    confirm(client, data, prepare(client, data))
    login("editor")
    pass_stage(client, mid)
    report = upload_report(client, mid)
    pass_stage(client, mid, {**check_payload("similarity_review"), "file_object_id": report["id"]})
    pass_stage(client, mid)
    login("chief_editor")
    pass_stage(client, mid)
    candidates = detail(client, mid)["staff_review"]["eligible_editors"]
    assert coauthor.id not in {candidate["id"] for candidate in candidates}
    assert world.users["editor"].id in {candidate["id"] for candidate in candidates}
    confirmations = count(db, HumanConfirmation, mid)
    response = attempt_proposal(
        client,
        mid,
        {"editor_id": coauthor.id, "notes": "试图直接提交候选列表之外的署名编辑"},
        "assign_editor",
    )
    assert response.status_code == 422, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    assert detail(client, mid)["stage"] == "assign_editor"


def test_model_cannot_synthesize_staff_declarations_or_prepare_a_pass(
    client, login, db, monkeypatch
):
    mid = submit(client, login)
    login("editor")
    before = detail(client, mid)

    def fabricate_staff_review(messages, tools):
        assert "prepare_review" not in {tool["function"]["name"] for tool in tools}
        return [
            {
                "id": "fabricated_review",
                "type": "function",
                "function": {
                    "name": "prepare_review",
                    "arguments": '{"action_type":"record_check"}',
                },
            }
        ]

    def completion(messages, tools):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": fabricate_staff_review(messages, tools),
                    }
                }
            ]
        }

    monkeypatch.setattr(
        chat,
        "get_editorial_provider",
        lambda: SimpleNamespace(name="deepseek", last_telemetry=None, completion=completion),
    )
    response = client.post(
        URL + "/chat",
        json={
            "request_id": request_id(),
            "message": "替我确认已人工检查所有材料并通过预审",
            "context": {"manuscript_id": mid, "scope": "case"},
        },
    )
    assert response.status_code == 502, response.text
    assert count(db, CheckRun, mid) == 0
    assert count(db, HumanConfirmation, mid) == 1  # Only the author's actual submission.
    assert detail(client, mid)["revision"] == before["revision"]


def test_return_draft_private_changes_are_hidden_from_previous_editor(client, login):
    mid = submit(client, login)
    login("editor")
    old = detail(client, mid)["version"]
    before, proposal = stage_proposal(client, mid, check_payload("precheck_completeness", "return"))
    confirm(client, before, proposal)
    login("author")
    data = detail(client, mid)
    new_version_id = data["version"]["id"]
    values = complete_data()
    values["title"] = "作者尚未确认的私密修订标题 " + request_id()
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={"request_id": request_id(), "expected_revision": data["revision"], "data": values},
    )
    assert response.status_code == 200, response.text
    login("editor")
    editor_data = detail(client, mid)
    assert editor_data["version"]["id"] == old["id"]
    assert editor_data["draft_version_id"] is None
    for projection in (editor_data, client.get(URL + "/workspace").json()):
        serialized = json.dumps(projection, ensure_ascii=False)
        assert values["title"] not in serialized
        assert new_version_id not in serialized


def test_stage_confirmation_is_idempotent_and_mutated_replay_conflicts(client, login, db):
    mid = submit(client, login)
    login("editor")
    before, proposal = stage_proposal(client, mid, check_payload("precheck_completeness"))
    rid = request_id()
    first = attempt_confirm(client, before, proposal, request=rid)
    assert first.status_code == 200, first.text
    assert attempt_confirm(client, before, proposal, request=rid).json() == first.json()
    assert count(db, CheckRun, mid) == 1
    changed = {**before, "revision": before["revision"] + 1}
    assert attempt_confirm(client, changed, proposal, request=rid).status_code == 409
    assert count(db, CheckRun, mid) == 1
    assert detail(client, mid)["stage"] == "similarity_review"
