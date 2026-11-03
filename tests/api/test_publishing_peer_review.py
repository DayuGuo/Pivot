"""Real in-app peer review: fixed material, explicit response and immutable report."""

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.models import Assignment
from apps.api.publishing.domain.review_models import ReviewReport, ReviewRound
from tests.api.test_publishing_intake import URL, detail, request_id
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


def reviewer_selection(client, login, world):
    mid = submit(client, login)
    login("editor")
    pass_stage(client, mid)
    report = upload_report(client, mid)
    payload = check_payload("similarity_review")
    payload["file_object_id"] = report["id"]
    pass_stage(client, mid, payload)
    pass_stage(client, mid)
    login("chief_editor")
    pass_stage(client, mid)
    before, proposal = stage_proposal(
        client,
        mid,
        {"editor_id": world.users["editor"].id, "notes": "由现有独立责任编辑安排本稿评审"},
        "assign_editor",
    )
    confirm(client, before, proposal)
    login("editor")
    pass_stage(client, mid)
    return mid


def propose(client, mid, action, data):
    current = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "action_type": action,
            "data": data,
        },
    )
    assert response.status_code == 200, response.text
    return current, response.json()


def open_round(client, mid, world, *, required=1, reviewers=None):
    before, proposal = propose(
        client,
        mid,
        "open_review",
        {
            "reviewer_ids": reviewers or [world.users["reviewer"].id],
            "required_reports": required,
            "instructions": "请阅读本轮明确授权的合成匿名稿件，提交给作者与编辑分别可见的评审意见。",
            "response_due_days": 7,
            "report_due_days": 21,
        },
    )
    confirm(client, before, proposal)
    return detail(client, mid)


def accept(client, login, mid, outcome="accept", notes=""):
    login("reviewer")
    data = detail(client, mid)
    invitation = data["review"]["invitation"]
    before, proposal = propose(
        client,
        mid,
        "respond_review_invitation",
        {
            "invitation_id": invitation["id"],
            "outcome": outcome,
            "conflict_status": "none",
            "notes": notes,
        },
    )
    review = client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()
    assert review["payload"]["version"] is None
    assert "authors" not in str(review)
    confirm(client, before, proposal)
    return detail(client, mid)


def report_values():
    return {
        "author_text": "这是一份完全合成的同行评审意见，用于验证稿件评审过程中的材料范围、结构化问题、独立提交和版本一致性，建议作者澄清测试数据和方法的关系。",
        "editor_private_text": "PRIVATE-EDITOR-COMMENT：仅编辑可读的合成保密说明。",
        "answers_json": {
            "rigor": "采用合成数据和明确的对照方法，仍需补充方法描述。",
            "confidential_assessment": "PRIVATE-ANSWER：此字段永远不应自动向作者共享。",
        },
        "recommendation": "minor_revision",
    }


def save_report(client, mid, values=None):
    report = detail(client, mid)["review"]["report"]
    response = client.patch(
        f"{URL}/review-reports/{report['id']}",
        json={
            "request_id": request_id(),
            "expected_revision": report["revision"],
            "data": values or report_values(),
        },
    )
    assert response.status_code == 200, response.text
    return detail(client, mid)


def test_real_round_invitation_accept_report_and_editor_close_are_distinct_human_operations(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    before, proposal = propose(
        client,
        mid,
        "open_review",
        {
            "reviewer_ids": [world.users["reviewer"].id],
            "required_reports": 1,
            "instructions": "请仅使用合成匿名稿件执行本地同行评审测试。",
            "response_due_days": 7,
            "report_due_days": 21,
        },
    )
    assert (
        db.scalar(
            select(func.count()).select_from(ReviewRound).where(ReviewRound.manuscript_id == mid)
        )
        == 0
    )
    confirm(client, before, proposal)
    staff = detail(client, mid)
    assert staff["review"]["round"]["submitted_reports"] == 0
    round_id = staff["review"]["round"]["id"]
    material_url = staff["review"]["materials"][0]["download_url"]
    original_file_url = before["version"]["files"][0]["download_url"]
    login("reviewer")
    pending = detail(client, mid)
    assert pending["review"]["mode"] == "reviewer" and pending["version"] is None
    assert pending["review"]["materials"] == [] and pending["review"]["report"] is None
    assert "测试署名作者" not in str(pending) and world.users["author"].email not in str(pending)
    assert client.get(material_url).status_code == 404
    assert client.get(original_file_url).status_code == 404
    accepted = accept(client, login, mid)
    assert accepted["review"]["can_edit_report"] and accepted["stage"] == "peer_review"
    material = client.get(accepted["review"]["materials"][0]["download_url"])
    assert material.status_code == 200 and material.content.startswith("合成".encode())
    assert "review-manuscript.txt" in material.headers["content-disposition"]
    assert client.get(original_file_url).status_code == 404
    saved = save_report(client, mid)
    report = saved["review"]["report"]
    assert report["status"] == "draft" and saved["review"]["round"]["submitted_reports"] == 0
    # Unsubmitted private reviewer draft is not exposed to editor or author.
    login("editor")
    assert "PRIVATE-EDITOR-COMMENT" not in str(detail(client, mid))
    login("reviewer")
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    assert db.get(ReviewReport, report["id"]).status == "draft"
    confirm(client, before, proposal)
    assert db.get(ReviewReport, report["id"]).status == "submitted"
    login("author")
    author = detail(client, mid)
    assert "PRIVATE-EDITOR-COMMENT" not in str(author) and report["id"] not in str(author)
    login("editor")
    current = detail(client, mid)
    assert current["review"]["round"]["submitted_reports"] == 1
    assert current["review"]["reports"][0]["editor_private_text"].startswith("PRIVATE-EDITOR")
    before, proposal = propose(
        client,
        mid,
        "finish_review",
        {"reason": "本轮实际报告已达到目标，由责任编辑确认结束本轮评审。", "cancel_pending": False},
    )
    confirm(client, before, proposal)
    assert detail(client, mid)["stage"] == "editor_recommendation"
    assert db.get(ReviewRound, round_id).status == "closed"
    assert db.get(ReviewRound, round_id).closing_confirmation_id
    assert (
        db.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(
                Assignment.manuscript_id == mid,
                Assignment.capability == "reviewer",
                Assignment.ends_at.is_(None),
            )
        )
        == 0
    )
    login("reviewer")
    history = detail(client, mid)
    assert history["review"]["report"]["status"] == "submitted"
    assert not history["review"]["can_edit_report"] and history["review"]["materials"] == []
    assert client.get(material_url).status_code == 404
