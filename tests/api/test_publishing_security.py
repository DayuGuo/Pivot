"""Security boundaries across legacy projections, physical files and lock waits.

Lock callbacks deterministically schedule a database revocation after authentication
but before the action resumes. They do not simulate HTTP authentication failures.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update

from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import (
    ActionProposal,
    ActionReceipt,
    FileObject,
    HumanConfirmation,
    ManuscriptVersion,
    VersionFile,
)
from apps.api.publishing.models import LoginSession, Membership
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
    root = tmp_path / "private-files"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


def confirmation_count(db, manuscript_id):
    return db.scalar(
        select(func.count())
        .select_from(HumanConfirmation)
        .where(HumanConfirmation.manuscript_id == manuscript_id)
    )


def test_legacy_workspace_entire_response_keeps_unsubmitted_material_private(client, login):
    login("author")
    data = fill(client, draft(client))
    submitted = complete_data()
    submitted["title"] = "Private draft canary " + request_id()
    response = client.patch(
        f"{URL}/manuscripts/{data['id']}/intake",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "data": submitted,
        },
    )
    assert response.status_code == 200, response.text
    data = detail(client, data["id"])
    proposal = prepare(client, data)
    private_markers = [
        data["id"],
        data["version"]["id"],
        submitted["title"],
        proposal["proposal_id"],
        proposal["digest"],
    ]
    for attachment in data["version"]["files"]:
        private_markers.extend([attachment["id"], attachment["sha256"]])
    for role in ("editor", "chief_editor", "reviewer"):
        login(role)
        # Inspect the full response, including audit payloads and future additions.
        response = client.get("/api/workspace")
        assert response.status_code == 200, response.text
        public_view = json.dumps(response.json(), ensure_ascii=False)
        for marker in private_markers:
            assert marker not in public_view, f"Private metadata exposed to {role}: {marker}"
        assert client.get(f"{URL}/manuscripts/{data['id']}").status_code == 404


@pytest.mark.parametrize("gate", ["prepare", "confirm"])
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_physical_file_damage_prevents_human_gate_without_partial_commit(
    client, login, db, private_storage, gate, damage
):
    login("author")
    data = fill(client, draft(client))
    mid = data["id"]
    proposal = prepare(client, data) if gate == "confirm" else None
    link = db.get(VersionFile, data["version"]["files"][0]["id"])
    blob = db.get(FileObject, link.file_object_id)
    target = Path(private_storage) / blob.storage_key
    assert target.is_file()
    if damage == "missing":
        target.unlink()
    else:
        # Same length, different bytes: mere existence and size checks cannot pass.
        raw = target.read_bytes()
        target.write_bytes(b"X" * len(raw))
    failed_request = request_id()
    if gate == "prepare":
        response = client.post(
            f"{URL}/manuscripts/{mid}/proposals",
            json={
                "request_id": failed_request,
                "expected_revision": data["revision"],
                "action_type": "submit",
                "data": {},
            },
        )
    else:
        response = client.post(
            f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
            json={
                "request_id": failed_request,
                "expected_revision": data["revision"],
                "digest": proposal["digest"],
                "acknowledged": True,
            },
        )
    assert response.status_code == 409, response.text
    assert confirmation_count(db, mid) == 0
    assert (
        db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == failed_request)) is None
    )
    db.expire_all()
    assert db.get(ManuscriptVersion, data["version"]["id"]).frozen_at is None
    saved = detail(client, mid)
    assert saved["stage"] == "author_draft" and saved["revision"] == data["revision"]
    proposals = db.scalars(select(ActionProposal).where(ActionProposal.manuscript_id == mid)).all()
    assert len(proposals) == (1 if gate == "confirm" else 0)


@pytest.mark.parametrize("lock_boundary", ["request", "manuscript"])
@pytest.mark.parametrize("revocation", ["session", "role"])
def test_revocation_while_action_waits_for_lock_cannot_save_or_issue_receipt(
    client, login, db, world, monkeypatch, lock_boundary, revocation
):
    login("author")
    created = draft(client)
    mid = created["manuscript_id"]
    before = detail(client, mid)
    calls = []

    def revoke():
        calls.append(revocation)
        user_id = world.users["author"].id
        # Core SQL keeps the authenticated ORM actor unchanged, like a concurrent
        # logout or administrator update on a separate connection would do.
        if revocation == "session":
            statement = delete(LoginSession).where(LoginSession.user_id == user_id)
        else:
            statement = (
                update(Membership)
                .where(Membership.user_id == user_id, Membership.journal_id == world.journal.id)
                .values(role="reviewer")
            )
        db.execute(statement.execution_options(synchronize_session=False))

    if lock_boundary == "request":
        original_lock = core.lock_request

        def request_lock(session, actor, request):
            original_lock(session, actor, request)
            revoke()

        monkeypatch.setattr(core, "lock_request", request_lock)
    else:
        original_scalar = db.scalar

        def manuscript_lock(statement, *args, **kwargs):
            result = original_scalar(statement, *args, **kwargs)
            if (
                not calls
                and getattr(statement, "_for_update_arg", None) is not None
                and "FROM manuscripts" in str(statement)
            ):
                revoke()
            return result

        monkeypatch.setattr(db, "scalar", manuscript_lock)

    failed_request = request_id()
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={
            "request_id": failed_request,
            "expected_revision": created["revision"],
            "data": complete_data(),
        },
    )
    assert calls == [revocation], "The test must actually reach the chosen lock boundary"
    assert response.status_code == 403, response.text
    assert (
        db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == failed_request)) is None
    )
    db.expire_all()
    version = db.get(ManuscriptVersion, before["version"]["id"])
    assert version.title == before["version"]["data"]["title"]
    assert version.abstract == before["version"]["data"]["abstract"]
    assert version.frozen_at is None
    assert confirmation_count(db, mid) == 0
