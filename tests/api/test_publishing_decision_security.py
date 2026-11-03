"""Independent security of human decisions, released feedback and formal revisions."""

import base64
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain.decision_models import EditorialDecision, RevisionRequest
from apps.api.publishing.domain.models import (
    Assignment,
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    SubmissionWorkflow,
    VersionFile,
)
from apps.api.publishing.models import Membership, User, now
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_publishing_decisions import (
    assess,
    choice,
    closed_round,
    decide,
    recommend,
    submit_revision,
)
from tests.api.test_publishing_decisions import production as production_fixture
from tests.api.test_publishing_intake import URL, complete_data, detail, request_id
from tests.api.test_publishing_peer_review import accept, open_round, propose, save_report
from tests.api.test_publishing_screening import confirm


@pytest.fixture
def production(db, world):
    return production_fixture.__wrapped__(db, world)


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    root = tmp_path / "files"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


def count(db, model, mid):
    return db.scalar(select(func.count()).select_from(model).where(model.manuscript_id == mid))


def attempt_proposal(client, mid, action, values):
    return client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": detail(client, mid)["revision"],
            "action_type": action,
            "data": values,
        },
    )


def confirmation_body(before, proposal):
    return {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }


def test_only_responsible_independent_chief_can_record_or_confirm_a_decision(
    client, login, db, world, production
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    login("chief_editor")
    before, proposal = propose(client, mid, "record_decision", choice())
    confirmations = count(db, HumanConfirmation, mid)
    for role in ("author", "editor", "reviewer", "production_editor"):
        login(role)
        response = client.post(
            f"{URL}/manuscripts/{mid}/proposals",
            json={
                "request_id": request_id(),
                "expected_revision": before["revision"],
                "action_type": "record_decision",
                "data": choice("reject"),
            },
        )
        assert response.status_code in {403, 404}, response.text
        assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 404
        response = client.post(
            f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
            json=confirmation_body(before, proposal),
        )
        assert response.status_code == 404, response.text
    assert count(db, EditorialDecision, mid) == 0
    assert count(db, HumanConfirmation, mid) == confirmations


def test_chief_known_author_conflict_after_preparation_blocks_human_confirmation(
    client, login, db, world
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    login("chief_editor")
    before, proposal = propose(client, mid, "record_decision", choice("reject"))
    confirmations = count(db, HumanConfirmation, mid)
    db.execute(
        update(User)
        .where(User.id == world.users["chief_editor"].id)
        .values(email="author@synthetic.test")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.expire_all()
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json=confirmation_body(before, proposal),
    )
    assert response.status_code in {403, 404}, response.text
    assert count(db, EditorialDecision, mid) == 0
    assert count(db, HumanConfirmation, mid) == confirmations
    assert detail(client, mid)["stage"] == "chief_decision"


def test_author_release_is_an_exact_safe_snapshot_not_a_raw_report_permission(
    client, login, db, world
):
    mid = closed_round(client, login, world)
    original = detail(client, mid)
    report = original["review"]["reports"][0]
    recommend(client, login, mid)
    decide(client, login, mid, reports=[report["id"]])
    login("author")
    author = detail(client, mid)
    encoded = json.dumps(author, ensure_ascii=False)
    for private in (
        "CHIEF-PRIVATE",
        "PRIVATE-EDITOR-COMMENT",
        "PRIVATE-ANSWER",
        report["id"],
        world.users["reviewer"].id,
        world.users["reviewer"].email,
        world.users["reviewer"].name,
    ):
        assert private not in encoded
    feedback = author["editorial"]["feedback"][-1]
    released = feedback["reports"][0]
    assert set(released) == {"ordinal", "author_snapshot"}
    assert set(released["author_snapshot"]) == {"author_text", "answers", "questions"}
    assert set(released["author_snapshot"]["answers"]) == {"rigor"}
    assert released["author_snapshot"]["author_text"] == report["author_text"]
    decision = db.scalar(select(EditorialDecision).where(EditorialDecision.manuscript_id == mid))
    confirmation = db.get(HumanConfirmation, decision.human_confirmation_id)
    assert client.get(f"{URL}/proposals/{confirmation.proposal_id}").status_code == 404
    login("reviewer")
    reviewer = detail(client, mid)
    assert reviewer.get("editorial") is None
    assert "CHIEF-PRIVATE" not in json.dumps(reviewer, ensure_ascii=False)


def test_acceptance_never_silently_replaces_approved_production_assignee(
    client, login, db, world, production
):
    other = User(
        email=f"zz-production-{request_id()}@synthetic.test",
        name="另一位合成制作负责人",
        password_hash=hash_password(PASSWORD),
    )
    db.add(other)
    db.flush()
    db.add(Membership(user_id=other.id, journal_id=world.journal.id, role="production_editor"))
    db.commit()
    mid = closed_round(client, login, world)
    recommend(client, login, mid, "accept")
    login("chief_editor")
    before, proposal = propose(client, mid, "record_decision", choice("accept"))
    snapshot = client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()["payload"][
        "decision"
    ]
    assert snapshot["production_assignee"]["id"] == production.id
    confirmations = count(db, HumanConfirmation, mid)
    db.execute(
        update(Membership)
        .where(Membership.user_id == production.id)
        .values(role="editor")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json=confirmation_body(before, proposal),
    )
    assert response.status_code == 409, response.text
    assert count(db, EditorialDecision, mid) == 0
    assert count(db, HumanConfirmation, mid) == confirmations
    flow = db.get(SubmissionWorkflow, mid)
    assert flow.stage == "chief_decision" and flow.accepted_version_id is None
    assert flow.production_editor_id is None
    assert (
        db.scalar(
            select(Assignment).where(
                Assignment.manuscript_id == mid, Assignment.capability == "production"
            )
        )
        is None
    )


@pytest.mark.parametrize("confirmed", [False, True])
def test_chief_snapshot_and_idempotent_receipts_are_hidden_after_responsibility_revoked(
    client, login, db, world, confirmed
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    login("chief_editor")
    before = detail(client, mid)
    prepare_body = {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "action_type": "record_decision",
        "data": choice("reject"),
    }
    prepare_url = f"{URL}/manuscripts/{mid}/proposals"
    response = client.post(prepare_url, json=prepare_body)
    assert response.status_code == 200, response.text
    proposal = response.json()
    confirm_url = f"{URL}/proposals/{proposal['proposal_id']}/confirmations"
    body = confirmation_body(before, proposal)
    if confirmed:
        assert client.post(confirm_url, json=body).status_code == 200
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 200
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == "chief")
        .values(ends_at=now())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert detail(client, mid)["editorial"] is None  # Chief still has journal summary access.
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 404
    assert client.post(prepare_url, json=prepare_body).status_code == 404
    if confirmed:
        assert client.post(confirm_url, json=body).status_code == 404


def test_formal_revision_revalidates_actual_response_bytes_before_freezing_new_version(
    client, login, db, world, private_storage
):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    decide(client, login, mid)
    login("author")
    data = detail(client, mid)
    old_version = data["current_version_id"]
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
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
                    "合成逐项回复文件，必须验证实际内容完整性。".encode()
                ).decode(),
            },
        },
    )
    assert response.status_code == 200, response.text
    before, proposal = propose(client, mid, "submit_revision", {})
    file = next(f for f in before["version"]["files"] if f["purpose"] == "response")
    link = db.get(VersionFile, file["id"])
    blob = db.get(FileObject, link.file_object_id)
    Path(private_storage / blob.storage_key).write_bytes(b"x" * blob.byte_size)
    confirmations = count(db, HumanConfirmation, mid)
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json=confirmation_body(before, proposal),
    )
    assert response.status_code == 409, response.text
    assert count(db, HumanConfirmation, mid) == confirmations
    request = db.scalar(select(RevisionRequest).where(RevisionRequest.manuscript_id == mid))
    assert request.status == "requested" and request.submitted_version_id is None
    assert db.get(ManuscriptVersion, before["version"]["id"]).frozen_at is None
    assert db.get(SubmissionWorkflow, mid).current_version_id == old_version


def test_chief_cannot_release_same_journal_report_from_another_manuscript(client, login, db, world):
    first = closed_round(client, login, world)
    foreign_report = detail(client, first)["review"]["reports"][0]["id"]
    second = closed_round(client, login, world)
    recommend(client, login, second)
    login("chief_editor")
    response = attempt_proposal(client, second, "record_decision", choice(reports=[foreign_report]))
    assert response.status_code == 422, response.text
    assert count(db, EditorialDecision, second) == 0
    assert detail(client, second)["stage"] == "chief_decision"


def test_minor_after_completed_major_rereview_uses_nearest_round_and_keeps_production_private(
    client, login, db, world, production
):
    mid = closed_round(client, login, world)
    first_round = detail(client, mid)["review"]["round"]["id"]
    recommend(client, login, mid, kind="major")
    decide(client, login, mid, kind="major")
    submit_revision(client, login, mid)
    assess(client, login, mid, "rereview")
    opened = open_round(client, mid, world)
    second_round = opened["review"]["round"]["id"]
    assert second_round != first_round
    accept(client, login, mid)
    report = save_report(client, mid)["review"]["report"]
    before, proposal = propose(
        client,
        mid,
        "submit_review",
        {"report_id": report["id"], "expected_report_revision": report["revision"]},
    )
    confirm(client, before, proposal)
    login("editor")
    before, proposal = propose(
        client,
        mid,
        "finish_review",
        {"reason": "大修版本已经完成新的真实同行评审轮次。", "cancel_pending": False},
    )
    confirm(client, before, proposal)
    recommend(client, login, mid)
    decide(client, login, mid, reports=[report["id"]])
    submit_revision(client, login, mid)
    assess(client, login, mid)
    recommend(client, login, mid, "accept")
    decide(client, login, mid, "accept")
    decision = db.scalar(
        select(EditorialDecision).where(
            EditorialDecision.manuscript_id == mid, EditorialDecision.decision_code == "accept"
        )
    )
    assert decision.basis_round_id == second_round
    assert db.get(ManuscriptVersion, decision.version_id).version_no == 3
    flow = db.get(SubmissionWorkflow, mid)
    assert (
        flow.production_editor_id == production.id
        and flow.accepted_version_id == decision.version_id
    )
    login("production_editor")
    output = detail(client, mid)
    assert output["editorial"] is None
    assert "CHIEF-PRIVATE" not in json.dumps(output, ensure_ascii=False)
