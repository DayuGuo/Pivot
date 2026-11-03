"""Real peer-review security: scoped material, personal reports and human snapshots."""

import json

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain.models import Assignment, HumanConfirmation
from apps.api.publishing.domain.review_models import ReviewInvitation, ReviewReport, ReviewRound
from apps.api.publishing.models import Membership, User, now
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
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


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


@pytest.fixture
def second_reviewer(db, world):
    user = User(
        email=f"reviewer2-{request_id()}@synthetic.test",
        name="第二位合成审稿人",
        password_hash=hash_password(PASSWORD),
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, journal_id=world.journal.id, role="reviewer"))
    db.commit()
    world.users["reviewer2"] = user
    return user


def count(db, model, mid):
    return db.scalar(select(func.count()).select_from(model).where(model.manuscript_id == mid))


def attempt_proposal(client, mid, action, data):
    current = detail(client, mid)
    return client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "action_type": action,
            "data": data,
        },
    )


def attempt_confirm(client, data, proposal, rid=None):
    return client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": rid or request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )


def response_as(client, login, mid, role="reviewer", outcome="accept"):
    login(role)
    invitation = detail(client, mid)["review"]["invitation"]
    data, proposal = propose(
        client,
        mid,
        "respond_review_invitation",
        {
            "invitation_id": invitation["id"],
            "outcome": outcome,
            "conflict_status": "none",
            "notes": "合成审稿人本人核对邀请后的回应。",
        },
    )
    confirm(client, data, proposal)
    return detail(client, mid)


def submit_report(client, mid):
    report = detail(client, mid)["review"]["report"]
    data, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    confirm(client, data, proposal)
    return detail(client, mid)


def test_decline_does_not_reject_manuscript_and_reinvitation_uses_new_latest_attempt(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    declined = accept(client, login, mid, outcome="decline", notes="本次没有足够时间完成评审。")
    first = declined["review"]["invitation"]
    assert first["status"] == "declined" and first["attempt_no"] == 1
    assert declined["stage"] == "reviewer_selection"
    assert declined["review"]["report"] is None and not declined["review"]["materials"]
    login("editor")
    data, proposal = propose(
        client,
        mid,
        "invite_reviewers",
        {
            "reviewer_ids": [world.users["reviewer"].id],
            "instructions": "编辑确认在第二次尝试中重新安排本篇合成稿件的站内评审。",
            "response_due_days": 7,
            "report_due_days": 21,
        },
    )
    confirm(client, data, proposal)
    login("reviewer")
    pending = detail(client, mid)
    latest = pending["review"]["invitation"]
    assert latest["id"] != first["id"] and latest["attempt_no"] == 2
    assert latest["status"] == "pending" and pending["version"] is None
    assert db.get(ReviewInvitation, first["id"]).status == "declined"
    accepted = accept(client, login, mid)
    assert accepted["review"]["invitation"]["id"] == latest["id"]
    assert accepted["review"]["can_edit_report"]
    assert count(db, ReviewReport, mid) == 1


def test_pending_invitee_cannot_guess_raw_version_or_round_material_downloads(client, login, world):
    mid = reviewer_selection(client, login, world)
    original = detail(client, mid)
    staff = open_round(client, mid, world)
    round_url = staff["review"]["materials"][0]["download_url"]
    raw_urls = [file["download_url"] for file in original["version"]["files"]]
    login("reviewer")
    pending = detail(client, mid)
    assert pending["review"]["materials"] == [] and pending["version"] is None
    for url in [round_url, *raw_urls]:
        assert client.get(url).status_code == 404
    accepted = accept(client, login, mid)
    original_material = client.get(round_url)
    assert original_material.status_code == 200
    assert accepted["version"]["id"] == original["version"]["id"]
    assert accepted["review"]["round"]["version_id"] == original["version"]["id"]
    blinded = next(f for f in original["version"]["files"] if f["purpose"] == "blinded_manuscript")
    assert accepted["review"]["materials"][0]["sha256"] == blinded["sha256"]
    assert accepted["review"]["materials"][0]["name"] == "review-manuscript.txt"
    for url in raw_urls:
        assert client.get(url).status_code == 404
    login("author")
    assert client.get(round_url).status_code == 404
    current = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/files",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "file": {
                "filename": "replacement.txt",
                "purpose": "blinded_manuscript",
                "content_base64": "bmV3IHN5bnRoZXRpYyBjb250ZW50",
            },
        },
    )
    assert response.status_code == 403, response.text
    login("reviewer")
    assert client.get(round_url).content == original_material.content
    assert detail(client, mid)["version"]["id"] == original["version"]["id"]


def test_other_people_and_foreign_journal_cannot_respond_save_or_confirm_personal_report(
    client, login, db, world, second_reviewer
):
    mid = reviewer_selection(client, login, world)
    staff = open_round(client, mid, world)
    invitation_id = staff["review"]["invitations"][0]["id"]
    round_url = staff["review"]["materials"][0]["download_url"]
    accept(client, login, mid)
    saved = save_report(client, mid)
    report = saved["review"]["report"]
    data, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    outsider = User(
        email=f"outsider-{request_id()}@synthetic.test",
        name="其他期刊审稿人",
        password_hash=hash_password(PASSWORD),
    )
    db.add(outsider)
    db.flush()
    db.add(Membership(user_id=outsider.id, journal_id=world.other_journal.id, role="reviewer"))
    db.commit()
    world.users["outsider"] = outsider
    for role in ("reviewer2", "outsider", "author", "editor"):
        login(role)
        response = client.patch(
            f"{URL}/review-reports/{report['id']}",
            json={
                "request_id": request_id(),
                "expected_revision": report["revision"],
                "data": report_values(),
            },
        )
        assert response.status_code == 404, response.text
        assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 404
        assert attempt_confirm(client, data, proposal).status_code == 404
        response = client.post(
            f"{URL}/manuscripts/{mid}/proposals",
            json={
                "request_id": request_id(),
                "expected_revision": saved["revision"],
                "action_type": "respond_review_invitation",
                "data": {
                    "invitation_id": invitation_id,
                    "outcome": "accept",
                    "conflict_status": "none",
                },
            },
        )
        assert response.status_code in {403, 404}, response.text
        if role in {"reviewer2", "outsider", "author"}:
            assert client.get(round_url).status_code == 404
    assert db.get(ReviewReport, report["id"]).status == "draft"


def test_reviewer_private_draft_and_raw_report_ids_are_not_staff_or_author_payload(
    client, login, world, second_reviewer
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world, reviewers=[world.users["reviewer"].id, second_reviewer.id])
    accept(client, login, mid)
    values = report_values()
    values["editor_private_text"] = "UNSUBMITTED-PRIVATE-" + request_id()
    data = save_report(client, mid, values)
    report_id = data["review"]["report"]["id"]
    for role in ("editor", "chief_editor", "author", "reviewer2"):
        login(role)
        projection = detail(client, mid)
        serialized = json.dumps(projection, ensure_ascii=False)
        assert values["editor_private_text"] not in serialized
        assert report_id not in serialized
    login("reviewer")
    submit_report(client, mid)
    login("author")
    serialized = json.dumps(detail(client, mid), ensure_ascii=False)
    assert report_id not in serialized and values["editor_private_text"] not in serialized


def test_report_old_revision_and_prepared_snapshot_cannot_submit_after_human_edit(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    accept(client, login, mid)
    old = save_report(client, mid)
    report = old["review"]["report"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    confirmations = count(db, HumanConfirmation, mid)
    values = report_values()
    values["author_text"] += " 这是负责人在准备审核后主动修改的最终文字。"
    current = save_report(client, mid, values)
    assert current["review"]["report"]["revision"] > report["revision"]
    stale = client.patch(
        f"{URL}/review-reports/{report['id']}",
        json={
            "request_id": request_id(),
            "expected_revision": report["revision"],
            "data": report_values(),
        },
    )
    assert stale.status_code == 409, stale.text
    assert attempt_confirm(client, before, proposal).status_code == 409
    assert count(db, HumanConfirmation, mid) == confirmations
    assert db.get(ReviewReport, report["id"]).status == "draft"
    assert detail(client, mid)["review"]["report"]["author_text"] == values["author_text"]


@pytest.mark.parametrize("withdrawal", ["grant", "membership", "coauthor"])
def test_revocation_blocks_material_save_and_prepared_submission(
    client, login, db, world, withdrawal
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    accept(client, login, mid)
    saved = save_report(client, mid)
    report = saved["review"]["report"]
    url = saved["review"]["materials"][0]["download_url"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    confirmations = count(db, HumanConfirmation, mid)
    uid = world.users["reviewer"].id
    if withdrawal == "grant":
        statement = (
            update(Assignment)
            .where(
                Assignment.manuscript_id == mid,
                Assignment.user_id == uid,
                Assignment.capability == "reviewer",
            )
            .values(ends_at=now())
        )
    elif withdrawal == "membership":
        statement = update(Membership).where(Membership.user_id == uid).values(role="editor")
    else:
        # Match the already-frozen synthetic author snapshot, not a guessed access grant.
        statement = update(User).where(User.id == uid).values(email="author@synthetic.test")
    db.execute(statement.execution_options(synchronize_session=False))
    db.commit()
    db.expire_all()  # Model a fresh request's actor after this external authority change.
    assert client.get(url).status_code == 404
    response = client.patch(
        f"{URL}/review-reports/{report['id']}",
        json={
            "request_id": request_id(),
            "expected_revision": report["revision"],
            "data": report_values(),
        },
    )
    assert response.status_code in {403, 404}, response.text
    assert attempt_confirm(client, before, proposal).status_code in {403, 404}
    assert count(db, HumanConfirmation, mid) == confirmations
    assert db.get(ReviewReport, report["id"]).status == "draft"


def test_finish_cannot_reduce_fixed_target_by_cancelling_unsubmitted_reviews(
    client, login, db, world, second_reviewer
):
    mid = reviewer_selection(client, login, world)
    open_round(
        client, mid, world, required=2, reviewers=[world.users["reviewer"].id, second_reviewer.id]
    )
    accept(client, login, mid)
    save_report(client, mid)
    submit_report(client, mid)
    login("editor")
    before = detail(client, mid)
    response = attempt_proposal(
        client,
        mid,
        "finish_review",
        {"reason": "试图以取消未完成邀请代替第二份有效报告", "cancel_pending": True},
    )
    assert response.status_code == 422, response.text
    assert detail(client, mid)["revision"] == before["revision"]
    assert db.get(ReviewRound, before["review"]["round"]["id"]).status == "open"
    assert count(db, ReviewReport, mid) == 1


def test_finishing_requires_explicit_cancellation_and_unchanged_draft_snapshot(
    client, login, db, world, second_reviewer
):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world, reviewers=[world.users["reviewer"].id, second_reviewer.id])
    accept(client, login, mid)
    save_report(client, mid)
    submit_report(client, mid)
    response_as(client, login, mid, role="reviewer2")
    second = save_report(client, mid)
    second_report = second["review"]["report"]
    material_url = second["review"]["materials"][0]["download_url"]
    login("editor")
    assert (
        attempt_proposal(
            client,
            mid,
            "finish_review",
            {"reason": "结束已达到目标的本轮评审", "cancel_pending": False},
        ).status_code
        == 422
    )
    before, proposal = propose(
        client,
        mid,
        "finish_review",
        {"reason": "明确结束并取消另一位尚未提交的草稿任务", "cancel_pending": True},
    )
    snapshot = client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()["payload"]
    assert snapshot["cancellations"][0]["report_revision"] == second_report["revision"]
    confirmations = count(db, HumanConfirmation, mid)
    login("reviewer2")
    values = report_values()
    values["author_text"] += " 未完成报告的新修订不能被旧取消快照静默覆盖。"
    save_report(client, mid, values)
    login("editor")
    assert attempt_confirm(client, before, proposal).status_code == 409
    assert count(db, HumanConfirmation, mid) == confirmations
    before, proposal = propose(
        client,
        mid,
        "finish_review",
        {"reason": "重新审核最新未提交草稿版本后明确取消并结束", "cancel_pending": True},
    )
    rid = request_id()
    first = attempt_confirm(client, before, proposal, rid)
    assert first.status_code == 200, first.text
    assert attempt_confirm(client, before, proposal, rid).json() == first.json()
    assert db.get(ReviewReport, second_report["id"]).status == "withdrawn"
    login("reviewer2")
    assert client.get(material_url).status_code == 404
    history = detail(client, mid)
    assert history["review"]["report"]["status"] == "withdrawn"
    assert not history["review"]["can_edit_report"]


def test_open_confirmation_rechecks_remaining_capacity_after_candidate_role_withdrawal(
    client, login, db, world, second_reviewer
):
    mid = reviewer_selection(client, login, world)
    before, proposal = propose(
        client,
        mid,
        "open_review",
        {
            "reviewer_ids": [world.users["reviewer"].id],
            "required_reports": 2,
            "instructions": "本轮需要两位独立审稿人的报告，先确认第一位邀请。",
        },
    )
    confirmations = count(db, HumanConfirmation, mid)
    db.execute(
        update(Membership).where(Membership.user_id == second_reviewer.id).values(role="author")
    )
    db.commit()
    response = attempt_confirm(client, before, proposal)
    assert response.status_code in {409, 422}, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    assert count(db, ReviewRound, mid) == 0
    assert count(db, ReviewInvitation, mid) == 0
