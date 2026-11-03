"""Independent review of peer-review snapshot/replay and lock-wait authorization."""

import json

import pytest
from sqlalchemy import select, update

from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import ActionProposal, Assignment, PublishingChatTurn
from apps.api.publishing.models import now
from tests.api.test_publishing_chat_security import call, respond
from tests.api.test_publishing_chat_security import scripted_provider as provider_fixture
from tests.api.test_publishing_intake import URL, detail, request_id
from tests.api.test_publishing_peer_chat import accepted_case, post
from tests.api.test_publishing_peer_review import (
    propose,
    reviewer_selection,
    save_report,
)
from tests.api.test_publishing_screening import confirm


@pytest.fixture
def scripted_provider(monkeypatch):
    return provider_fixture.__wrapped__(monkeypatch)


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def revoke(db, mid, capability):
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == capability)
        .values(ends_at=now())
        .execution_options(synchronize_session=False)
    )


@pytest.mark.parametrize("confirmed", [False, True])
def test_peer_snapshot_and_action_receipts_need_current_private_staff_grant(
    client, login, db, world, confirmed
):
    mid = reviewer_selection(client, login, world)
    before = detail(client, mid)
    body = {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "action_type": "open_review",
        "data": {
            "reviewer_ids": [world.users["reviewer"].id],
            "required_reports": 1,
            "instructions": "负责人逐项审核本轮合成匿名稿件的站内邀请快照。",
        },
    }
    url = f"{URL}/manuscripts/{mid}/proposals"
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    proposal = response.json()
    confirmation_body = {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }
    confirmation_url = f"{URL}/proposals/{proposal['proposal_id']}/confirmations"
    if confirmed:
        response = client.post(confirmation_url, json=confirmation_body)
        assert response.status_code == 200, response.text
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 200
    revoke(db, mid, "handling_editor")
    db.commit()
    # Earlier precheck responsibility still permits the manuscript, not the invitation roster.
    assert detail(client, mid)["review"] is None
    denied = client.get(f"{URL}/proposals/{proposal['proposal_id']}")
    assert denied.status_code == 404, denied.text
    assert world.users["reviewer"].email not in denied.text
    assert client.post(url, json=body).status_code == 404
    if confirmed:
        assert client.post(confirmation_url, json=confirmation_body).status_code == 404


def test_old_screening_snapshot_needs_original_capability_not_just_manuscript_access(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    proposal = next(
        p
        for p in db.scalars(
            select(ActionProposal).where(
                ActionProposal.manuscript_id == mid, ActionProposal.action_type == "record_check"
            )
        )
        if p.payload_snapshot["stage"] == "precheck_completeness"
    )
    url = f"{URL}/proposals/{proposal.id}"
    assert client.get(url).json()["status"] == "confirmed"
    revoke(db, mid, "precheck")
    db.commit()
    assert detail(client, mid)["review"]["mode"] == "staff"  # Handling grant remains.
    assert client.get(url).status_code == 404


def test_chat_receipt_replay_rechecks_file_scope_after_request_lock_wait(
    client, login, db, world, scripted_provider, monkeypatch
):
    mid = accepted_case(client, login, world)
    file = detail(client, mid)["review"]["materials"][0]
    rid = request_id()
    canary = "ONLY-WITH-ANONYMOUS-FILE-GRANT-" + request_id()
    scripted_provider([[call("read_current_file", {"file_id": file["id"]})], [respond(canary)]])
    first = post(client, mid, rid=rid)
    assert first.status_code == 200, first.text
    original_lock = core.lock_request
    revoked = []

    def wait_then_revoke(session, actor, request):
        original_lock(session, actor, request)
        revoke(db, mid, "reviewer")
        revoked.append(True)

    monkeypatch.setattr(core, "lock_request", wait_then_revoke)
    replay = post(client, mid, rid=rid)
    assert revoked == [True]
    assert replay.status_code == 403, replay.text
    assert canary not in replay.text


def test_final_answer_rechecks_file_scope_after_manuscript_lock_wait(
    client, login, db, world, scripted_provider, monkeypatch
):
    mid = accepted_case(client, login, world)
    file = detail(client, mid)["review"]["materials"][0]
    scripted_provider(
        [[call("read_current_file", {"file_id": file["id"]})], [respond("LOCK-WAIT-PRIVATE")]]
    )
    original_scalar = db.scalar
    revoked = []

    def wait_then_revoke(statement, *args, **kwargs):
        result = original_scalar(statement, *args, **kwargs)
        if (
            not revoked
            and getattr(statement, "_for_update_arg", None) is not None
            and "FROM manuscripts" in str(statement)
        ):
            revoke(db, mid, "reviewer")
            revoked.append(True)
        return result

    monkeypatch.setattr(db, "scalar", wait_then_revoke)
    response = post(client, mid)
    assert revoked == [True], "The scheduling callback must reach the final manuscript lock"
    assert response.status_code == 403, response.text
    assert (
        db.scalar(select(PublishingChatTurn).where(PublishingChatTurn.manuscript_id == mid)) is None
    )


def test_filtered_private_history_is_not_reintroduced_into_next_provider_memory(
    client, login, db, world, scripted_provider
):
    mid = accepted_case(client, login, world)
    report = save_report(client, mid)["review"]["report"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    confirm(client, before, proposal)
    login("editor")
    canary = "PRIVATE-MEMORY-CANARY-" + request_id()
    scripted_provider([[respond(canary)]])
    assert post(client, mid, "解释已提交的保密报告").status_code == 200
    assert canary in client.get(URL + "/chat?manuscript_id=" + mid).text
    revoke(db, mid, "handling_editor")
    db.commit()
    assert detail(client, mid)["review"] is None

    def inspect_safe_memory(messages, tools):
        encoded = json.dumps(messages, ensure_ascii=False)
        assert canary not in encoded
        assert "PRIVATE-EDITOR-COMMENT" not in encoded
        return [respond("当前仅依据仍有权查看的稿件信息回答。")]

    scripted_provider([inspect_safe_memory])
    response = post(client, mid, "重新概述目前有权查看的信息")
    assert response.status_code == 200, response.text
    assert canary not in response.text
