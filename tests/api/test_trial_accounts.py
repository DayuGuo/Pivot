"""Trial enrollment uses real PostgreSQL/auth; never sends mail or calls a model."""

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from apps.api.publishing.models import AuditEvent, LoginSession, Membership, TrialAccount, User
from apps.api.publishing.operations.trial_accounts import TrialAccessError, TrialCommand, execute
from apps.api.publishing.security import Actor, check_password, ensure_current_actor, hash_password

OPERATOR_PASSWORD = "SyntheticOperatorPassword2026!"
PARTICIPANT_PASSWORD = "SyntheticParticipantPassword2026!"
NEW_PASSWORD = "NewSyntheticParticipantPassword2026!"


@pytest.fixture
def operator_setup(db, world, monkeypatch):
    user = world.users["editor"]
    user.password_hash = hash_password(OPERATOR_PASSWORD)
    db.commit()
    monkeypatch.setenv("PIVOT_BOOTSTRAP_PROFILE", "private-preview")
    monkeypatch.setenv("PIVOT_OPERATOR_EMAIL", user.email)
    monkeypatch.setenv("PIVOT_OPERATOR_PASSWORD", OPERATOR_PASSWORD)
    monkeypatch.setenv("EMAIL_SEND_ENABLED", "false")
    return user


def create_command(world, **changes):
    values = dict(
        action="create",
        journal_id=world.journal.id,
        request_id=str(uuid4()),
        email=f"trial-{uuid4().hex}@synthetic.test",
        name="试用编辑",
        confirmed=True,
        password=PARTICIPANT_PASSWORD,
        reason="pilot_enrollment",
    )
    values.update(changes)
    return TrialCommand(**values)


def change_command(account, action="disable", **changes):
    values = dict(
        action=action,
        journal_id=account["journal_id"],
        request_id=str(uuid4()),
        user_id=account["user_id"],
        expected_revision=account["revision"],
        confirmed=True,
        reason="pilot_finished",
    )
    if action != "disable":
        values["password"] = NEW_PASSWORD
    values.update(changes)
    return TrialCommand(**values)


def sign_in(client, account, password=PARTICIPANT_PASSWORD):
    response = client.post(
        "/api/auth/login", json={"email": account["email"], "password": password}
    )
    if response.status_code == 200:
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


def test_enrollment_idempotence_single_editor_and_safe_receipt(db, world, operator_setup):
    command = create_command(world)
    first = execute(db, command)
    assert execute(db, command) == first
    assert first["status"] == "active" and first["revision"] == 1
    roles = db.scalars(select(Membership.role).where(Membership.user_id == first["user_id"])).all()
    assert roles == ["editor"]
    user = db.get(User, first["user_id"])
    assert check_password(PARTICIPANT_PASSWORD, user.password_hash)
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == user.id)).all()
    assert len(events) == 1 and events[0].actor_id == operator_setup.id
    assert PARTICIPANT_PASSWORD not in json.dumps([first, events[0].details])
    assert user.password_hash not in json.dumps([first, events[0].details])
    roster = execute(db, TrialCommand(action="list"))
    assert len(roster["accounts"]) == 1 and roster["journal_id"] == world.journal.id
    with pytest.raises(TrialAccessError, match="Retry password differs"):
        execute(
            db,
            command.model_copy(
                update={
                    "password": TrialCommand(
                        **{**command.model_dump(), "password": NEW_PASSWORD}
                    ).password
                }
            ),
        )


def test_disable_resume_preserves_dossier_and_never_revives_sessions(
    db, world, client, operator_setup
):
    from tests.api.test_dossiers import create

    account = execute(db, create_command(world))
    assert sign_in(client, account).status_code == 200
    dossier = create(client)
    old_session = db.scalar(select(LoginSession).where(LoginSession.user_id == account["user_id"]))
    actor = Actor(
        db.get(User, account["user_id"]),
        db.scalar(select(Membership).where(Membership.user_id == account["user_id"])),
        old_session,
    )
    ensure_current_actor(db, actor)
    disable = change_command(account)
    disabled = execute(db, disable)
    assert disabled["revoked_sessions"] == 1 and disabled["revision"] == 2
    assert execute(db, disable) == disabled
    assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 401
    assert sign_in(client, account).status_code == 401
    with pytest.raises(HTTPException):
        ensure_current_actor(db, actor, for_commit=True)
    db.rollback()
    with pytest.raises(TrialAccessError, match="new password"):
        execute(db, change_command(disabled, "resume", password=PARTICIPANT_PASSWORD))
    resumed = execute(db, change_command(disabled, "resume"))
    assert resumed["status"] == "active"
    with pytest.raises(HTTPException):
        ensure_current_actor(db, actor, for_commit=True)
    db.rollback()
    assert sign_in(client, account).status_code == 401
    assert sign_in(client, account, NEW_PASSWORD).status_code == 200
    assert client.get(f"/api/dossiers/{dossier['id']}").status_code == 200
    with pytest.raises(TrialAccessError, match="superseded"):
        execute(db, disable)


def test_two_editors_have_separate_dossiers_and_no_management_http(
    db, world, client, operator_setup
):
    from tests.api.test_dossiers import create

    first = execute(db, create_command(world))
    second = execute(db, create_command(world))
    assert sign_in(client, first).status_code == 200
    dossier = create(client)
    assert sign_in(client, second).status_code == 200
    assert client.get(f"/api/dossiers/{dossier['id']}").status_code in {403, 404}
    assert client.post("/api/trial/accounts", json={"action": "create"}).status_code == 404
    response = client.post(
        "/api/auth/identity", json={"role": "chief_editor", "request_id": str(uuid4())}
    )
    assert response.status_code == 403


def test_rotate_password_revokes_all_sessions(db, world, client, operator_setup):
    account = execute(db, create_command(world))
    assert sign_in(client, account).status_code == 200
    assert sign_in(client, account).status_code == 200
    updated = execute(db, change_command(account, "rotate-password"))
    assert updated["revoked_sessions"] == 2
    assert client.get("/api/auth/me").status_code == 401
    assert sign_in(client, account).status_code == 401
    assert sign_in(client, account, NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "key,value",
    [
        ("PIVOT_BOOTSTRAP_PROFILE", "local"),
        ("EMAIL_SEND_ENABLED", "true"),
        ("PIVOT_OPERATOR_PASSWORD", "WrongOperatorPassword2026!"),
        ("PIVOT_OPERATOR_EMAIL", "unconfigured@synthetic.test"),
    ],
)
def test_operator_boundary_no_partial_creation(db, world, operator_setup, monkeypatch, key, value):
    command = create_command(world)
    monkeypatch.setenv(key, value)
    with pytest.raises(TrialAccessError):
        execute(db, command)
    assert db.scalar(select(User.id).where(User.email == command.email)) is None


def test_cannot_take_over_existing_user_or_other_journal(db, world, operator_setup):
    world.users["author"].email = f"existing-{uuid4().hex}@synthetic.test"
    db.commit()
    original = world.users["author"].password_hash
    with pytest.raises(TrialAccessError, match="already exists"):
        execute(db, create_command(world, email=world.users["author"].email))
    assert world.users["author"].password_hash == original
    with pytest.raises(TrialAccessError, match="requested journal"):
        execute(db, create_command(world, journal_id=world.other_journal.id))
    with pytest.raises(TrialAccessError, match="not managed"):
        execute(
            db,
            change_command(
                {"user_id": operator_setup.id, "journal_id": world.journal.id, "revision": 1}
            ),
        )


def test_state_and_revision_conflicts_cannot_reenable_or_overwrite(db, world, operator_setup):
    account = execute(db, create_command(world))
    with pytest.raises(TrialAccessError, match="current access state"):
        execute(db, change_command(account, "resume"))
    with pytest.raises(TrialAccessError, match="Account changed"):
        execute(db, change_command(account, expected_revision=9))
    assert db.get(TrialAccount, account["user_id"]).status == "active"
    command = change_command(account)
    execute(db, command)
    with pytest.raises(TrialAccessError, match="different content"):
        execute(db, change_command(account, "resume", request_id=command.request_id))


@pytest.mark.parametrize(
    "changes",
    [
        {"confirmed": False},
        {"confirmed": "true"},
        {"password": "short"},
        {"password": None},
        {"name": " "},
        {"email": "editor@publishing.test"},
        {"role": "chief_editor"},
        {"reason": "arbitrary secret"},
        {"journal_id": None},
    ],
)
def test_invalid_commands_refuse_before_gateway(world, changes):
    with pytest.raises(ValidationError):
        create_command(world, **changes)


def test_operator_password_cannot_be_reused(db, world, operator_setup):
    with pytest.raises(TrialAccessError, match="independent"):
        execute(db, create_command(world, password=OPERATOR_PASSWORD))


def test_failed_audit_rolls_back_user_membership_and_enrollment(
    db, world, operator_setup, monkeypatch
):
    from apps.api.publishing.operations import trial_accounts

    command = create_command(world)

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(trial_accounts, "record", fail)
    with pytest.raises(RuntimeError, match="Synthetic audit"):
        execute(db, command)
    assert db.scalar(select(User.id).where(User.email == command.email)) is None


@pytest.mark.parametrize(
    "role,private,expected",
    [
        ("editor", True, "/library"),
        ("chief_editor", True, "/library"),
        ("author", True, "/"),
        ("reviewer", True, "/"),
        ("editor", False, "/"),
    ],
)
def test_private_landing_respects_role(client, login, monkeypatch, role, private, expected):
    monkeypatch.setenv("PIVOT_BOOTSTRAP_PROFILE", "private-preview" if private else "local")
    assert login(role)["landing_path"] == expected
    assert client.get("/api/auth/me").json()["landing_path"] == expected


def test_roster_limit_counts_disabled_accounts(db, world, operator_setup, monkeypatch):
    from apps.api.publishing.operations import trial_accounts

    monkeypatch.setattr(trial_accounts, "MAX_ACCOUNTS", 1)
    account = execute(db, create_command(world))
    execute(db, change_command(account))
    command = create_command(world)
    with pytest.raises(TrialAccessError, match="limit reached"):
        execute(db, command)
    assert db.scalar(select(User.id).where(User.email == command.email)) is None


def test_managed_role_drift_does_not_grant_additional_access(db, world, operator_setup):
    account = execute(db, create_command(world))
    db.add(Membership(user_id=account["user_id"], journal_id=world.journal.id, role="chief_editor"))
    db.commit()
    with pytest.raises(TrialAccessError, match="roles changed"):
        execute(db, change_command(account, "rotate-password"))
    assert check_password(PARTICIPANT_PASSWORD, db.get(User, account["user_id"]).password_hash)


def test_another_operator_cannot_take_over_original_roster(db, world, operator_setup, monkeypatch):
    account = execute(db, create_command(world))
    other = world.users["chief_editor"]
    other.password_hash = hash_password(OPERATOR_PASSWORD)
    db.add(Membership(user_id=other.id, journal_id=world.journal.id, role="editor"))
    db.commit()
    monkeypatch.setenv("PIVOT_OPERATOR_EMAIL", other.email)
    assert execute(db, TrialCommand(action="list"))["accounts"] == []
    with pytest.raises(TrialAccessError, match="not managed"):
        execute(db, change_command(account))
