"""Real PostgreSQL editorial evidence, author release and formal revision chains."""

import base64

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.decision_models import EditorialDecision, RevisionRequest
from apps.api.publishing.domain.models import ManuscriptVersion, SubmissionWorkflow
from apps.api.publishing.models import Membership, User
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_publishing_intake import URL, complete_data, detail, request_id
from tests.api.test_publishing_peer_review import (
    accept,
    open_round,
    propose,
    reviewer_selection,
    save_report,
)
from tests.api.test_publishing_screening import confirm


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


@pytest.fixture
def production(db, world):
    user = User(
        email=f"production-{world.journal.id}@publishing.test",
        name="测试制作",
        password_hash=hash_password(PASSWORD),
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, journal_id=world.journal.id, role="production_editor"))
    db.commit()
    world.users["production_editor"] = user
    return user


def closed_round(client, login, world):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    accept(client, login, mid)
    saved = save_report(client, mid)
    report = saved["review"]["report"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {
            "report_id": report["id"],
            "expected_report_revision": report["revision"],
        },
    )
    confirm(client, before, proposal)
    login("editor")
    before, proposal = propose(
        client,
        mid,
        "finish_review",
        {
            "reason": "本轮已经实际收到报告，由负责人确认结束评审并汇总建议。",
            "cancel_pending": False,
        },
    )
    confirm(client, before, proposal)
    return mid


def recommendation(code="request_revision", kind="minor"):
    return {
        "recommendation": code,
        "revision_kind": kind if code == "request_revision" else None,
        "rationale_private": "编辑已结合实际报告和当前版本作出独立建议，供主编核对决定。",
        "author_letter": "请作者根据明确的合成评审意见补充方法、数据来源和讨论内容。",
    }


def choice(code="request_revision", kind="minor", reports=None):
    return {
        "decision_code": code,
        "revision_kind": kind if code == "request_revision" else None,
        "rationale_private": "CHIEF-PRIVATE：由本稿主编本人核对全部决定依据并记录独立意见。",
        "author_letter": "本刊已完成人工审核，请根据此决定及明确的作者可见反馈继续处理。",
        "share_report_ids": reports or [],
        "share_reports_anonymity_reviewed": bool(reports),
        "author_instructions": "请逐项回应方法与证据的关系，补充说明并上传实际回复文件。"
        if code == "request_revision"
        else "",
        "due_days": 14 if code == "request_revision" else None,
    }


def recommend(client, login, mid, code="request_revision", kind="minor"):
    login("editor")
    before, proposal = propose(client, mid, "recommend_decision", recommendation(code, kind))
    confirm(client, before, proposal)
    assert detail(client, mid)["stage"] == "chief_decision"
    return proposal


def decide(client, login, mid, code="request_revision", kind="minor", reports=None):
    login("chief_editor")
    before, proposal = propose(client, mid, "record_decision", choice(code, kind, reports))
    confirm(client, before, proposal)
    return proposal


def submit_revision(client, login, mid):
    login("author")
    current = detail(client, mid)
    assert current["stage"] == "author_revision"
    assert current["version"]["data"]["declarations"]["originality"] is False
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "data": complete_data(),
        },
    )
    assert response.status_code == 200, response.text
    response = client.post(
        f"{URL}/manuscripts/{mid}/files",
        json={
            "request_id": request_id(),
            "expected_revision": response.json()["revision"],
            "file": {
                "filename": "response.txt",
                "purpose": "response",
                "content_base64": base64.b64encode(
                    "合成逐项回复：已补充方法、证据和讨论。".encode()
                ).decode(),
            },
        },
    )
    assert response.status_code == 200, response.text
    before, proposal = propose(client, mid, "submit_revision", {})
    confirm(client, before, proposal)
    assert detail(client, mid)["stage"] == "revision_assessment"
    return detail(client, mid)


def assess(client, login, mid, outcome="ready_for_chief"):
    login("editor")
    before, proposal = propose(
        client,
        mid,
        "assess_revision",
        {
            "outcome": outcome,
            "notes": "本人已阅读当前新版本与逐项回复，核对本轮修改和后续流程依据。",
            "declarations": {
                "reviewed_current_version": True,
                "reviewed_response": True,
                "anonymous_material_reviewed": outcome == "rereview",
            },
        },
    )
    confirm(client, before, proposal)
    return detail(client, mid)


def test_minor_revisions_twice_preserve_old_round_and_new_version_evidence_then_accept(
    client,
    login,
    db,
    world,
    production,
):
    mid = closed_round(client, login, world)
    original = detail(client, mid)
    basis = original["review"]["round"]["id"]
    rid = original["review"]["reports"][0]["id"]
    for version_no in (2, 3):
        recommend(client, login, mid)
        proposal = decide(client, login, mid, reports=[rid])
        snapshot = client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()["payload"][
            "decision"
        ]
        assert snapshot["basis_round_id"] == basis
        login("author")
        author = detail(client, mid)
        assert author["version"]["version_no"] == version_no
        assert author["editorial"]["feedback"][-1]["reports"][0]["author_snapshot"][
            "answers"
        ].keys() == {"rigor"}
        assert rid not in str(author) and "PRIVATE-" not in str(author)
        assert world.users["reviewer"].email not in str(author)
        submitted = submit_revision(client, login, mid)
        assert submitted["current_version_id"] != original["current_version_id"]
        assert assess(client, login, mid)["stage"] == "editor_recommendation"
    recommend(client, login, mid, "accept")
    decide(client, login, mid, "accept")
    flow = db.get(SubmissionWorkflow, mid)
    assert flow.stage == "production" and flow.accepted_version_id == flow.current_version_id
    assert flow.production_editor_id == production.id
    assert db.get(ManuscriptVersion, flow.current_version_id).version_no == 3
    assert (
        db.scalar(
            select(func.count())
            .select_from(EditorialDecision)
            .where(EditorialDecision.manuscript_id == mid)
        )
        == 3
    )
    login("production_editor")
    assert any(t["kind"] == "production" for t in detail(client, mid)["own_tasks"])


def test_major_revision_cannot_use_minor_bridge_and_requires_new_round(client, login, db, world):
    mid = closed_round(client, login, world)
    recommend(client, login, mid, kind="major")
    decide(client, login, mid, kind="major")
    submit_revision(client, login, mid)
    login("editor")
    current = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "action_type": "assess_revision",
            "data": {
                "outcome": "ready_for_chief",
                "notes": "不能以普通复核代替大修所要求的新版本实际同行评审。",
                "declarations": {
                    "reviewed_current_version": True,
                    "reviewed_response": True,
                    "anonymous_material_reviewed": False,
                },
            },
        },
    )
    assert response.status_code == 422
    result = assess(client, login, mid, "rereview")
    assert result["stage"] == "reviewer_selection"
    new = open_round(client, mid, world)
    assert new["review"]["round"]["round_no"] == 2
    assert new["review"]["round"]["version_id"] == new["current_version_id"]


def test_chief_may_change_suggestion_and_reject_without_releasing_private_fields(
    client, login, db, world
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid, "accept")
    decide(client, login, mid, "reject")
    assert detail(client, mid)["stage"] == "rejected"
    login("author")
    author = detail(client, mid)
    assert author["editorial"]["feedback"][-1]["decision_code"] == "reject"
    assert "CHIEF-PRIVATE" not in str(author) and not author["allowed_actions"]
    assert db.get(SubmissionWorkflow, mid).accepted_version_id is None


def test_prepare_decision_does_not_create_decision_revision_or_release_and_replay_is_idempotent(
    client, login, db, world
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    login("chief_editor")
    before, proposal = propose(client, mid, "record_decision", choice())
    assert not db.scalar(select(EditorialDecision).where(EditorialDecision.manuscript_id == mid))
    assert not db.scalar(select(RevisionRequest).where(RevisionRequest.manuscript_id == mid))
    body = {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }
    url = f"{URL}/proposals/{proposal['proposal_id']}/confirmations"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    assert client.post(url, json=body).json() == first.json()
    assert (
        db.scalar(
            select(func.count())
            .select_from(EditorialDecision)
            .where(EditorialDecision.manuscript_id == mid)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(RevisionRequest)
            .where(RevisionRequest.manuscript_id == mid)
        )
        == 1
    )
