"""Granted identities switch authority without changing ownership or human gates."""

import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from apps.api.publishing import identities, main
from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import Assignment, HumanConfirmation
from apps.api.publishing.models import (
    AuditEvent,
    Conversation,
    LoginSession,
    Manuscript,
    Membership,
    now,
)
from apps.api.publishing.security import Actor, new_session, token_digest
from tests.api.test_dossiers import create as create_dossier
from tests.api.test_publishing_intake import URL, detail, draft, request_id
from tests.api.test_publishing_peer_review import open_round, propose, reviewer_selection
from tests.api.test_publishing_screening import confirm, submit

IDENTITIES = "/api/auth/identities"
SWITCH = "/api/auth/identity"


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def grant(db, world, user_role, role, *, journal=None):
    member = Membership(
        user_id=world.users[user_role].id,
        journal_id=(journal or world.journal).id,
        role=role,
    )
    db.add(member)
    db.commit()
    return member


def switch(client, role, rid=None):
    response = client.post(SWITCH, json={"role": role, "request_id": rid or request_id()})
    if response.status_code == 200:
        current = client.get("/api/auth/me")
        assert current.status_code == 200, current.text
        client.headers["X-CSRF-Token"] = current.json()["csrf_token"]
    return response


def switch_events(db, user_id):
    return db.scalars(
        select(AuditEvent).where(
            AuditEvent.actor_id == user_id, AuditEvent.action == "auth.identity_switched"
        )
    ).all()


def test_identity_endpoints_require_login(client):
    assert client.get(IDENTITIES).status_code == 401
    assert (
        client.post(SWITCH, json={"role": "editor", "request_id": request_id()}).status_code == 401
    )


def test_identity_list_contains_only_current_users_granted_roles(client, login, db, world):
    grant(db, world, "editor", "reviewer")
    grant(db, world, "editor", "chief_editor")
    login()
    before = db.scalar(select(func.count()).select_from(LoginSession))
    response = client.get(IDENTITIES)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user"]["id"] == world.users["editor"].id
    assert data["journal"]["id"] == world.journal.id
    assert data["active_role"] == "editor"
    assert set(data["roles"]) == {"editor", "reviewer", "chief_editor"}
    assert data["csrf_token"] == client.headers["X-CSRF-Token"]
    assert db.scalar(select(func.count()).select_from(LoginSession)) == before
    assert not switch_events(db, world.users["editor"].id)


@pytest.mark.parametrize(
    ("base", "extra", "expected"),
    [
        ("author", ["editor", "reviewer", "chief_editor"], "editor"),
        ("author", ["reviewer", "chief_editor"], "chief_editor"),
        ("author", ["reviewer"], "reviewer"),
        ("author", ["production_editor"], "author"),
    ],
)
def test_login_chooses_deterministic_same_journal_role(
    client, login, db, world, base, extra, expected
):
    for role in reversed(extra):
        grant(db, world, base, role)
    result = login(base)
    assert result["user"]["role"] == expected
    restored = client.get("/api/auth/me")
    assert restored.status_code == 200
    assert restored.json()["user"] == result["user"]


def test_multiple_journals_remain_ambiguous_at_login(client, db, world):
    from tests.api.conftest import PASSWORD

    grant(db, world, "editor", "reviewer", journal=world.other_journal)
    response = client.post(
        "/api/auth/login",
        json={"email": world.users["editor"].email, "password": PASSWORD},
    )
    assert response.status_code == 409, response.text
    assert client.get("/api/auth/me").status_code == 401


def test_existing_active_session_does_not_bypass_multiple_journal_rejection(
    client, login, db, world
):
    login()
    grant(db, world, "editor", "reviewer", journal=world.other_journal)
    assert client.get("/api/auth/me").status_code == 409
    assert client.get(IDENTITIES).status_code == 409
    assert (
        client.post(SWITCH, json={"role": "reviewer", "request_id": request_id()}).status_code
        == 409
    )


def test_session_cannot_bind_another_users_membership(db, world):
    other_member = db.scalar(
        select(Membership).where(Membership.user_id == world.users["author"].id)
    )
    _, session = new_session(world.users["editor"], other_member)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(session)
        db.flush()
    assert db.get(LoginSession, session.token_hash) is None


def test_switch_rotates_session_preserves_expiry_and_records_safe_audit(client, login, db, world):
    target = grant(db, world, "editor", "reviewer")
    old = login()
    raw_cookie = client.cookies.get("publishing_session")
    old_hash = token_digest(raw_cookie)
    previous = db.get(LoginSession, old_hash)
    previous.expires_at = now() + timedelta(minutes=19)
    expiry = previous.expires_at
    db.commit()
    rid = request_id()
    response = switch(client, "reviewer", rid)
    assert response.status_code == 200, response.text
    new_cookie = client.cookies.get("publishing_session")
    assert new_cookie != raw_cookie
    current = client.get("/api/auth/me").json()
    assert current["user"]["id"] == old["user"]["id"]
    assert current["user"]["role"] == "reviewer"
    assert current["csrf_token"] != old["csrf_token"]
    db.expire_all()
    assert db.get(LoginSession, old_hash) is None
    replacement = db.get(LoginSession, token_digest(new_cookie))
    assert replacement.active_membership_id == target.id
    assert replacement.expires_at == expiry
    events = switch_events(db, world.users["editor"].id)
    assert len(events) == 1
    assert events[0].journal_id == world.journal.id
    assert events[0].details == {"from_role": "editor", "to_role": "reviewer", "request_id": rid}
    logged = json.dumps(events[0].details)
    for secret in (raw_cookie, new_cookie, old["csrf_token"], current["csrf_token"]):
        assert secret not in logged
    assert (
        client.get(
            "/api/auth/me", headers={"Cookie": f"publishing_session={raw_cookie}"}
        ).status_code
        == 401
    )
    stale = client.post(
        SWITCH,
        headers={"X-CSRF-Token": old["csrf_token"]},
        json={"role": "editor", "request_id": request_id()},
    )
    assert stale.status_code == 403
    assert client.get("/api/auth/me").json()["user"]["role"] == "reviewer"


def test_same_role_and_replayed_target_are_noops(client, login, db, world):
    grant(db, world, "editor", "reviewer")
    login()
    original_cookie = client.cookies.get("publishing_session")
    original_csrf = client.headers["X-CSRF-Token"]
    response = switch(client, "editor")
    assert response.status_code == 200, response.text
    assert client.cookies.get("publishing_session") == original_cookie
    assert client.headers["X-CSRF-Token"] == original_csrf
    assert not switch_events(db, world.users["editor"].id)
    rid = request_id()
    assert switch(client, "reviewer", rid).status_code == 200
    switched_cookie = client.cookies.get("publishing_session")
    switched_csrf = client.headers["X-CSRF-Token"]
    assert switch(client, "reviewer", rid).status_code == 200
    assert client.cookies.get("publishing_session") == switched_cookie
    assert client.headers["X-CSRF-Token"] == switched_csrf
    assert len(switch_events(db, world.users["editor"].id)) == 1


def test_processed_switch_uuid_cannot_reapply_after_another_switch(client, login, db, world):
    grant(db, world, "editor", "reviewer")
    login()
    original = request_id()
    assert switch(client, "reviewer", original).status_code == 200
    assert switch(client, "editor").status_code == 200
    cookie = client.cookies.get("publishing_session")
    response = client.post(SWITCH, json={"role": "reviewer", "request_id": original})
    assert response.status_code == 409, response.text
    assert client.cookies.get("publishing_session") == cookie
    assert client.get("/api/auth/me").json()["user"]["role"] == "editor"
    assert len(switch_events(db, world.users["editor"].id)) == 2


def test_switch_uuid_cannot_be_reused_for_another_role_or_business_action(client, login, db, world):
    grant(db, world, "editor", "reviewer")
    grant(db, world, "editor", "chief_editor")
    login()
    business_id = request_id()
    created = client.post(
        f"{URL}/drafts", json={"request_id": business_id, "title": "合成请求编号隔离"}
    )
    assert created.status_code == 200, created.text
    collision = client.post(SWITCH, json={"role": "reviewer", "request_id": business_id})
    assert collision.status_code == 409, collision.text
    assert not switch_events(db, world.users["editor"].id)
    switched_id = request_id()
    assert switch(client, "reviewer", switched_id).status_code == 200
    response = client.post(SWITCH, json={"role": "chief_editor", "request_id": switched_id})
    assert response.status_code == 409, response.text
    response = client.post(
        f"{URL}/drafts", json={"request_id": switched_id, "title": "不应创建的合成草稿"}
    )
    assert response.status_code == 409, response.text
    assert client.get("/api/auth/me").json()["user"]["role"] == "reviewer"
    assert len(switch_events(db, world.users["editor"].id)) == 1


@pytest.mark.parametrize(
    ("role", "status"),
    [("author", 403), ("chief_editor", 403), ("reviewer", 403), ("administrator", 422)],
)
def test_ungranted_roles_cannot_be_claimed(client, login, db, world, role, status):
    login()
    cookie = client.cookies.get("publishing_session")
    before = client.headers["X-CSRF-Token"]
    response = client.post(SWITCH, json={"role": role, "request_id": request_id()})
    assert response.status_code == status, response.text
    assert client.cookies.get("publishing_session") == cookie
    assert client.get("/api/auth/me").json()["csrf_token"] == before
    assert not switch_events(db, world.users["editor"].id)


@pytest.mark.parametrize("boundary", ["missing_csrf", "wrong_csrf", "cross_site"])
def test_switch_reuses_browser_and_csrf_boundaries(client, login, db, world, boundary):
    grant(db, world, "editor", "reviewer")
    login()
    cookie = client.cookies.get("publishing_session")
    if boundary == "missing_csrf":
        del client.headers["X-CSRF-Token"]
        headers = {}
    elif boundary == "wrong_csrf":
        headers = {"X-CSRF-Token": "wrong-token"}
    else:
        headers = {"Sec-Fetch-Site": "cross-site"}
    response = client.post(
        SWITCH, headers=headers, json={"role": "reviewer", "request_id": request_id()}
    )
    assert response.status_code == 403, response.text
    assert client.cookies.get("publishing_session") == cookie
    assert not switch_events(db, world.users["editor"].id)


def test_revoked_target_grant_cannot_be_selected(client, login, db, world):
    member = grant(db, world, "editor", "reviewer")
    login()
    assert "reviewer" in client.get(IDENTITIES).json()["roles"]
    db.delete(member)
    db.commit()
    assert (
        client.post(SWITCH, json={"role": "reviewer", "request_id": request_id()}).status_code
        == 403
    )
    assert client.get("/api/auth/me").json()["user"]["role"] == "editor"


def test_target_role_changed_after_authentication_cannot_use_cached_membership(
    client, login, db, world, monkeypatch
):
    target = grant(db, world, "editor", "reviewer")
    login()
    cookie = client.cookies.get("publishing_session")
    original_lock = identities.lock_request
    changed = []

    def change_target_after_authentication(database, actor, rid):
        original_lock(database, actor, rid)
        cached = database.get(Membership, target.id)
        assert cached.role == "reviewer"
        database.execute(
            update(Membership)
            .where(Membership.id == target.id)
            .values(role="author")
            .execution_options(synchronize_session=False)
        )
        assert cached.role == "reviewer"
        changed.append(True)

    monkeypatch.setattr(identities, "lock_request", change_target_after_authentication)
    response = client.post(SWITCH, json={"role": "reviewer", "request_id": request_id()})
    assert changed and response.status_code == 403, response.text
    assert client.cookies.get("publishing_session") == cookie
    assert client.get("/api/auth/me").json()["user"]["role"] == "editor"
    assert not switch_events(db, world.users["editor"].id)


def test_conversation_creation_cannot_commit_after_its_session_is_removed(
    client, login, db, world, monkeypatch
):
    login()
    original_create = main.create_conversation
    created = []

    def create_then_remove_session(database, actor, title):
        item = original_create(database, actor, title)
        created.append(item.id)
        database.execute(
            delete(LoginSession)
            .where(LoginSession.token_hash == actor.session.token_hash)
            .execution_options(synchronize_session=False)
        )
        return item

    monkeypatch.setattr(main, "create_conversation", create_then_remove_session)
    response = client.post("/api/conversations", json={"title": "不应提交的合成对话"})
    assert created and response.status_code == 403, response.text
    # The shared HTTP fixture leaves a failed request transaction open; emulate
    # get_db's normal close/rollback before checking the committed snapshot.
    db.rollback()
    assert db.get(Conversation, created[0]) is None
    assert not db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.actor_id == world.users["editor"].id,
            AuditEvent.action == "conversation.created",
            AuditEvent.entity_id == created[0],
        )
    )


def test_role_switch_does_not_open_others_drafts_or_private_dossiers(client, login, db, world):
    login("author")
    mid = draft(client)["manuscript_id"]
    login("chief_editor")
    dossier = create_dossier(client)
    for role in ("author", "reviewer", "chief_editor"):
        grant(db, world, "editor", role)
    login()
    for role in ("editor", "reviewer", "author", "chief_editor"):
        assert switch(client, role).status_code == 200
        assert client.get(f"{URL}/manuscripts/{mid}").status_code == 404
        assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 404


def test_switching_to_editor_cannot_bypass_own_authorship_conflict(client, login, db, world):
    mid = submit(client, login)
    member = grant(db, world, "author", "editor")
    login("author")
    current = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == token_digest(client.cookies.get("publishing_session"))
        )
    )
    actor = Actor(world.users["author"], member, current)
    manuscript = db.get(Manuscript, mid)
    assert actor.role == "editor" and core.is_conflicted(db, manuscript, actor.user)
    with pytest.raises(HTTPException) as failure:
        core.assign(db, actor, manuscript, actor.user.id, "precheck")
    assert failure.value.status_code == 422
    assert not db.scalar(
        select(Assignment.id).where(
            Assignment.manuscript_id == mid,
            Assignment.user_id == actor.user.id,
            Assignment.capability == "precheck",
        )
    )
    assert detail(client, mid)["allowed_actions"] == []


def test_role_view_separates_editor_work_from_owned_author_drafts(client, login, db, world):
    assigned_id = submit(client, login)
    grant(db, world, "editor", "author")
    grant(db, world, "editor", "chief_editor")
    login()
    owned_id = draft(client)["manuscript_id"]
    compatible = client.get(f"{URL}/workspace")
    assert compatible.status_code == 200, compatible.text
    assert {owned_id, assigned_id} <= {item["id"] for item in compatible.json()["submissions"]}
    editorial = client.get(f"{URL}/workspace?role_view=true")
    assert editorial.status_code == 200, editorial.text
    assert {item["id"] for item in editorial.json()["submissions"]} == {assigned_id}
    assert {task["kind"] for task in editorial.json()["tasks"]} == {"precheck_completeness"}
    assert detail(client, owned_id)["is_owner"]
    assert switch(client, "author").status_code == 200
    authorship = client.get(f"{URL}/workspace?role_view=true")
    assert authorship.status_code == 200, authorship.text
    assert {item["id"] for item in authorship.json()["submissions"]} == {owned_id}
    assert {task["kind"] for task in authorship.json()["tasks"]} == {"author_draft"}
    assert client.get(f"{URL}/manuscripts/{assigned_id}").status_code == 404
    assert switch(client, "chief_editor").status_code == 200
    chief = client.get(f"{URL}/workspace?role_view=true")
    assert chief.status_code == 200, chief.text
    assert {item["id"] for item in chief.json()["submissions"]} == {assigned_id}
    assert chief.json()["tasks"] == []


def test_supplementary_reviewer_role_requires_acceptance_and_preserves_blind_material(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    staff = open_round(client, mid, world)
    material_url = staff["review"]["materials"][0]["download_url"]
    grant(db, world, "reviewer", "editor")
    assert login("reviewer")["user"]["role"] == "editor"
    owned_id = draft(client)["manuscript_id"]
    assert switch(client, "reviewer").status_code == 200
    queue = client.get(f"{URL}/workspace?role_view=true")
    assert queue.status_code == 200, queue.text
    assert {item["id"] for item in queue.json()["submissions"]} == {mid}
    assert {task["kind"] for task in queue.json()["tasks"]} == {"respond_review_invitation"}
    compatible = client.get(f"{URL}/workspace")
    assert {item["id"] for item in compatible.json()["submissions"]} == {mid, owned_id}
    pending = detail(client, mid)
    assert pending["version"] is None and not pending["review"]["materials"]
    assert client.get(material_url).status_code == 404
    before, proposal = propose(
        client,
        mid,
        "respond_review_invitation",
        {
            "invitation_id": pending["review"]["invitation"]["id"],
            "outcome": "accept",
            "conflict_status": "none",
            "notes": "本人核对合成邀请后明确接受，不由身份切换代替回应。",
        },
    )
    confirmations = db.scalar(select(func.count()).select_from(HumanConfirmation))
    confirm(client, before, proposal)
    assert db.scalar(select(func.count()).select_from(HumanConfirmation)) == confirmations + 1
    accepted = detail(client, mid)
    assert accepted["review"]["can_edit_report"]
    assert db.scalar(
        select(Assignment.id).where(
            Assignment.manuscript_id == mid,
            Assignment.user_id == world.users["reviewer"].id,
            Assignment.capability == "reviewer",
        )
    )
    assert client.get(material_url).status_code == 200
    assert switch(client, "editor").status_code == 200
    editorial = client.get(f"{URL}/workspace?role_view=true")
    assert editorial.status_code == 200, editorial.text
    assert editorial.json()["submissions"] == [] and editorial.json()["tasks"] == []
    assert client.get(f"{URL}/manuscripts/{mid}").status_code == 404
    assert client.get(material_url).status_code == 404
    assert switch(client, "reviewer").status_code == 200
    assert client.get(material_url).status_code == 200
