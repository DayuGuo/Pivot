"""Peer-review tool policy, private context and revocation across persistent chat."""

import json

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.models import (
    ActionProposal,
    Assignment,
    HumanConfirmation,
    PublishingChatTurn,
)
from apps.api.publishing.domain.review_models import ReviewReport, ReviewRound
from apps.api.publishing.domain.review_schemas import ReportCandidates
from apps.api.publishing.domain.schemas import IntakeCandidates
from apps.api.publishing.models import now
from tests.api.test_publishing_chat_security import (
    call,
    respond,
)
from tests.api.test_publishing_chat_security import (
    scripted_provider as provider_fixture,
)
from tests.api.test_publishing_intake import URL, detail, request_id
from tests.api.test_publishing_peer_review import (
    accept,
    open_round,
    propose,
    report_values,
    reviewer_selection,
    save_report,
)
from tests.api.test_publishing_screening import confirm


@pytest.fixture
def scripted_provider(monkeypatch):
    return provider_fixture.__wrapped__(monkeypatch)


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def post(client, mid, message="读取本人当前评审材料", rid=None):
    return client.post(
        URL + "/chat",
        json={
            "request_id": rid or request_id(),
            "message": message,
            "context": {"manuscript_id": mid, "scope": "case", "view": "work"},
        },
    )


def accepted_case(client, login, world):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    accept(client, login, mid)
    return mid


def test_function_schemas_inline_bounded_dto_references():
    for model in (IntakeCandidates, ReportCandidates):
        encoded = json.dumps(chat.tool_schema(model))
        assert "$ref" not in encoded and "$defs" not in encoded
        assert '"additionalProperties": false' in encoded
    assert "recommendation" not in chat.tool_schema(ReportCandidates)["properties"]


def test_model_cannot_read_original_file_by_guessing_same_version_id(
    client, login, world, scripted_provider, db
):
    mid = reviewer_selection(client, login, world)
    private_file = next(
        f for f in detail(client, mid)["version"]["files"] if f["purpose"] == "manuscript"
    )
    open_round(client, mid, world)
    accept(client, login, mid)
    provider = scripted_provider(
        [[[call("read_current_file", {"file_id": private_file["id"]})][0]]]
    )
    response = post(client, mid)
    assert response.status_code == 404, response.text
    assert len(provider.calls) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(PublishingChatTurn)
            .where(PublishingChatTurn.manuscript_id == mid)
        )
        == 0
    )


def test_reviewer_report_candidates_never_choose_recommendation_or_submit(
    client, login, world, scripted_provider, db
):
    mid = accepted_case(client, login, world)
    report_id = detail(client, mid)["review"]["report"]["id"]
    scripted_provider(
        [
            [
                call(
                    "propose_report_notes",
                    {"candidates": {"author_text": "未核实的合成评审候选文字，供审稿人本人核对。"}},
                )
            ],
            [respond("已准备未核实的本人报告候选。")],
        ]
    )
    response = post(client, mid, "帮助我整理评审报告文字")
    assert response.status_code == 200, response.text
    data = detail(client, mid)
    assert data["review"]["report_candidates"]["verified"] is False
    assert "未核实" in data["review"]["report_candidates"]["author_text"]
    report = db.get(ReviewReport, report_id)
    assert (
        report.status == "draft"
        and report.author_text == ""
        and report.recommendation == "unanswered"
    )
    assert data["review"]["round"]["submitted_reports"] == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 9
    )


@pytest.mark.parametrize(
    "extra", [{"recommendation": "accept"}, {"conflict_status": "none"}, {"status": "submitted"}]
)
def test_report_candidate_model_cannot_write_human_choices(
    client, login, world, scripted_provider, extra
):
    mid = accepted_case(client, login, world)
    before = detail(client, mid)
    scripted_provider(
        [[call("propose_report_notes", {"candidates": {"author_text": "候选", **extra}})]]
    )
    assert post(client, mid, "整理评审报告").status_code == 502
    assert detail(client, mid) == before


def test_reviewer_file_grant_revocation_hides_transcript_and_blocks_receipt_replay(
    client, login, world, scripted_provider, db
):
    mid = accepted_case(client, login, world)
    file = detail(client, mid)["review"]["materials"][0]
    rid = request_id()
    scripted_provider(
        [
            [call("read_current_file", {"file_id": file["id"]})],
            [respond("HISTORY-ANONYMOUS-CANARY", ["file_" + file["id"].replace("-", "")])],
        ]
    )
    assert post(client, mid, rid=rid).status_code == 200
    assert "HISTORY-ANONYMOUS-CANARY" in str(client.get(URL + "/chat?manuscript_id=" + mid).json())
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == "reviewer")
        .values(ends_at=now())
    )
    db.commit()
    assert (
        detail(client, mid)["review"]["invitation"]["status"] == "accepted"
    )  # Summary permission remains.
    assert detail(client, mid)["review"]["materials"] == []
    assert client.get(URL + "/chat?manuscript_id=" + mid).json()["messages"] == []
    replay = post(client, mid, rid=rid)
    assert replay.status_code == 403 and "HISTORY-ANONYMOUS-CANARY" not in replay.text


def test_reviewer_grant_withdrawn_during_supplier_wait_prevents_next_read_or_request(
    client, login, world, scripted_provider, db
):
    mid = accepted_case(client, login, world)
    file = detail(client, mid)["review"]["materials"][0]

    def revoke(messages, tools):
        db.execute(
            update(Assignment)
            .where(Assignment.manuscript_id == mid, Assignment.capability == "reviewer")
            .values(ends_at=now())
            .execution_options(synchronize_session=False)
        )
        return [call("read_current_file", {"file_id": file["id"]})]

    provider = scripted_provider([revoke, [respond()]])
    assert post(client, mid).status_code == 403
    assert len(provider.calls) == 1


def test_editor_losing_private_report_grant_keeps_manuscript_but_loses_private_chat(
    client, login, world, scripted_provider, db
):
    mid = accepted_case(client, login, world)
    saved = save_report(client, mid)["review"]["report"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": saved["id"], "expected_report_revision": saved["revision"]},
    )
    confirm(client, before, proposal)
    login("editor")
    rid = request_id()

    def inspect(messages, tools):
        assert "PRIVATE-EDITOR-COMMENT" in messages[0]["content"]
        return [respond("PRIVATE-EDITOR-COMMENT只供授权编辑查看")]

    scripted_provider([inspect])
    assert post(client, mid, "解释已提交的评审意见", rid).status_code == 200
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == "handling_editor")
        .values(ends_at=now())
    )
    db.commit()
    assert (
        detail(client, mid)["review"] is None
    )  # The earlier precheck grant still permits manuscript access.
    assert client.get(URL + "/chat?manuscript_id=" + mid).json()["messages"] == []
    assert post(client, mid, "解释已提交的评审意见", rid).status_code == 403


def test_model_prepares_editor_invitation_snapshot_without_creating_round_or_sending(
    client, login, world, scripted_provider, db
):
    mid = reviewer_selection(client, login, world)
    data = {
        "reviewer_ids": [world.users["reviewer"].id],
        "required_reports": 1,
        "instructions": "请阅读本轮明确授权的合成匿名稿件，并完成本人评审意见。",
        "response_due_days": 7,
        "report_due_days": 21,
    }
    scripted_provider(
        [
            [call("prepare_open_review", {"data": data})],
            [respond("已准备站内邀请审核，尚未发出邀请。")],
        ]
    )
    response = post(client, mid, "请准备给测试审稿人的站内邀请")
    assert response.status_code == 200, response.text
    assert response.json()["messages"][1]["action"]["type"] == "review"
    assert (
        db.scalar(
            select(func.count()).select_from(ReviewRound).where(ReviewRound.manuscript_id == mid)
        )
        == 0
    )
    assert detail(client, mid)["stage"] == "reviewer_selection"
    assert (
        db.scalar(
            select(func.count())
            .select_from(ActionProposal)
            .where(ActionProposal.manuscript_id == mid, ActionProposal.action_type == "open_review")
        )
        == 1
    )


def test_model_prepares_saved_report_for_personal_confirmation_only(
    client, login, world, scripted_provider, db
):
    mid = accepted_case(client, login, world)
    report = save_report(client, mid, report_values())["review"]["report"]
    scripted_provider(
        [[call("prepare_report_review")], [respond("报告资料已准备，请本人独立确认。")]]
    )
    response = post(client, mid, "请准备本人的报告提交审核")
    assert response.status_code == 200, response.text
    assert response.json()["messages"][1]["action"]["type"] == "review"
    assert db.get(ReviewReport, report["id"]).status == "draft"


def test_gaining_material_permission_keeps_pre_acceptance_summary_chat(
    client, login, world, scripted_provider
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    login("reviewer")
    scripted_provider([[respond("PENDING-SUMMARY-HISTORY：请先核对本人利益冲突再回应。")]])
    assert post(client, mid, "我需要先了解什么？").status_code == 200
    assert "PENDING-SUMMARY-HISTORY" in str(client.get(URL + "/chat?manuscript_id=" + mid).json())
    accept(client, login, mid)
    assert detail(client, mid)["review"]["materials"]
    assert "PENDING-SUMMARY-HISTORY" in str(client.get(URL + "/chat?manuscript_id=" + mid).json())
