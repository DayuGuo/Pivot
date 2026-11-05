"""Session ownership and mailbox boundaries against isolated PostgreSQL transactions."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.models import (
    AuditEvent,
    Conversation,
    MailAccount,
    Manuscript,
    Message,
)

from .conftest import PROMPT


def create_conversation(client, title=None):
    response = client.post("/api/conversations", json={} if title is None else {"title": title})
    assert response.status_code == 200, response.text
    return response.json()


def command(client, conversation_id=None, *, message=PROMPT, request_id=None):
    body = {"message": message, "request_id": request_id or str(uuid4())}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    return client.post("/api/conversations/commands", json=body)


def smtp_input(**overrides):
    return {
        "provider": "smtp",
        "address": "editor@publishing.test",
        "display_name": "合成编辑部",
        "smtp_host": "mailpit",
        "smtp_port": 1025,
        "tls_mode": "none",
        "auth_mode": "none",
        **overrides,
    }


def save_account(client, **overrides):
    response = client.post("/api/mail/accounts", json=smtp_input(**overrides))
    assert response.status_code == 200, response.text
    return response.json()


def test_conversations_require_authentication_and_csrf(client, login):
    assert client.post("/api/conversations", json={}).status_code == 401
    login()
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/conversations", json={}).status_code == 403


def test_empty_workspace_get_does_not_create_conversation(client, login, db, world):
    login()
    for _ in range(2):
        response = client.get("/api/workspace")
        assert response.status_code == 200
        assert response.json()["conversations"] == []
        assert response.json()["active_conversation_id"] is None
        assert response.json()["messages"] == []
    assert (
        db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == world.users["editor"].id)
        )
        == 0
    )


def test_create_conversation_and_restore_selected_workspace(client, login, db, world):
    login()
    first = create_conversation(client)
    second = create_conversation(client, "另一项工作")
    assert first["title"] == "新对话"
    assert first["message_count"] == second["message_count"] == 0
    assert first["created_at"] and first["updated_at"]
    selected = client.get("/api/workspace", params={"conversation_id": first["id"]})
    assert selected.status_code == 200
    data = selected.json()
    assert data["active_conversation_id"] == first["id"]
    assert {item["id"] for item in data["conversations"]} == {first["id"], second["id"]}
    assert data["messages"] == []
    stored = db.get(Conversation, first["id"])
    assert stored.user_id == world.users["editor"].id
    assert stored.journal_id == world.journal.id
    assert client.get("/api/workspace").json()["active_conversation_id"] == second["id"]


def test_commands_belong_to_selected_session_and_default_title_changes(client, login, db):
    login()
    first = create_conversation(client)
    second = create_conversation(client, "保留标题")
    result = command(client, first["id"])
    assert result.status_code == 200, result.text
    assert result.json()["conversation_id"] == first["id"]
    selected = client.get("/api/workspace", params={"conversation_id": first["id"]}).json()
    assert len(selected["messages"]) == 2
    assert any(item["content"] == PROMPT for item in selected["messages"])
    summaries = {item["id"]: item for item in selected["conversations"]}
    assert summaries[first["id"]]["title"] == "测试稿件初筛"
    assert summaries[first["id"]]["message_count"] == 2
    assert summaries[second["id"]]["message_count"] == 0
    empty = client.get("/api/workspace", params={"conversation_id": second["id"]}).json()
    assert empty["messages"] == []
    other = command(client, second["id"])
    assert other.status_code == 200
    assert other.json()["manuscript"] is not None
    assert (
        len(
            client.get("/api/workspace", params={"conversation_id": second["id"]}).json()[
                "messages"
            ]
        )
        == 2
    )
    assert db.get(Conversation, second["id"]).title == "保留标题"
    rows = db.scalars(select(Message).where(Message.conversation_id == first["id"])).all()
    assert len(rows) == 2
    assert {row.id for row in rows} == {row["id"] for row in selected["messages"]}


def test_command_without_target_creates_then_reuses_real_session(client, login, db, world):
    login()
    first = command(client)
    assert first.status_code == 200, first.text
    session_id = first.json()["conversation_id"]
    second = command(client, message="你好")
    assert second.status_code == 200
    assert second.json()["conversation_id"] == session_id
    assert (
        db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == world.users["editor"].id)
        )
        == 1
    )
    assert len(client.get("/api/workspace").json()["messages"]) == 4


def test_target_is_part_of_command_idempotence_and_replay_keeps_session(client, login, db, world):
    login()
    first = create_conversation(client)
    second = create_conversation(client)
    request_id = str(uuid4())
    original = command(client, first["id"], request_id=request_id)
    replay = command(client, first["id"], request_id=request_id)
    assert original.status_code == replay.status_code == 200
    assert replay.json() == original.json()
    assert command(client, second["id"], request_id=request_id).status_code == 409
    assert (
        command(client, first["id"], request_id=request_id, message="不同内容").status_code == 409
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Manuscript)
            .where(Manuscript.journal_id == world.journal.id)
        )
        == 1
    )
    assert (
        len(
            client.get("/api/workspace", params={"conversation_id": first["id"]}).json()["messages"]
        )
        == 2
    )
    assert (
        client.get("/api/workspace", params={"conversation_id": second["id"]}).json()["messages"]
        == []
    )


def test_implicit_command_replay_keeps_original_after_new_session(client, login):
    login()
    request_id = str(uuid4())
    original = command(client, request_id=request_id)
    assert original.status_code == 200
    newer = create_conversation(client)
    replay = command(client, request_id=request_id)
    assert replay.status_code == 200
    assert replay.json() == original.json()
    assert replay.json()["conversation_id"] != newer["id"]


def test_other_users_and_journals_cannot_read_or_target_conversations(client, login, db, world):
    login()
    owned = create_conversation(client)
    foreign = Conversation(
        user_id=world.users["chief_editor"].id,
        journal_id=world.other_journal.id,
        title="其他期刊",
    )
    db.add(foreign)
    db.commit()
    login("chief_editor")
    for session_id in (owned["id"], foreign.id, str(uuid4())):
        assert (
            client.get("/api/workspace", params={"conversation_id": session_id}).status_code == 404
        )
        assert command(client, session_id).status_code == 404
    assert client.get("/api/workspace").json()["conversations"] == []


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_non_editor_can_create_session_but_intake_remains_forbidden(client, login, db, world, role):
    login(role)
    conversation = create_conversation(client)
    assert command(client, conversation["id"]).status_code == 403
    data = client.get("/api/workspace", params={"conversation_id": conversation["id"]}).json()
    assert data["active_conversation_id"] == conversation["id"]
    assert data["messages"] == []
    assert (
        db.scalar(
            select(func.count())
            .select_from(Manuscript)
            .where(Manuscript.journal_id == world.journal.id)
        )
        == 0
    )


def test_mail_requires_authenticated_editor_and_csrf(client, login):
    assert client.get("/api/mail/accounts").status_code == 401
    assert client.post("/api/mail/accounts", json=smtp_input()).status_code == 401
    login()
    account = save_account(client)
    client.headers.pop("X-CSRF-Token")
    for path, payload in (
        ("/api/mail/accounts", smtp_input()),
        (f"/api/mail/accounts/{account['id']}/verify", None),
        (f"/api/mail/accounts/{account['id']}/disconnect", None),
    ):
        assert client.post(path, json=payload).status_code == 403


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_mail_forbidden_to_non_editors(client, login, role):
    login()
    account = save_account(client)
    login(role)
    assert client.get("/api/mail/accounts").status_code == 403
    assert client.post("/api/mail/accounts", json=smtp_input()).status_code == 403
    assert client.post(f"/api/mail/accounts/{account['id']}/verify").status_code == 403
    assert client.post(f"/api/mail/accounts/{account['id']}/disconnect").status_code == 403


@pytest.mark.parametrize("role", ["editor", "chief_editor"])
def test_save_is_not_verification_and_get_is_read_only(client, login, db, world, monkeypatch, role):
    from apps.api.publishing import mail_accounts

    def no_probe(*args, **kwargs):
        pytest.fail("Saving and listing mailbox metadata must not probe external services")

    monkeypatch.setattr(mail_accounts, "probe", no_probe)
    login(role)
    account = save_account(client)
    assert account["status"] == "unverified"
    assert account["last_checked_at"] is None
    assert account["credentials_configured"] is False
    event_count = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.journal_id == world.journal.id)
    )
    for _ in range(2):
        listed = client.get("/api/mail/accounts")
        assert listed.status_code == 200
        assert listed.json() == {"accounts": [account], "email_send_enabled": False}
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.journal_id == world.journal.id)
        )
        == event_count
    )
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "unverified"


def test_mail_other_journal_ids_are_hidden_and_mutations_fail_404(
    client, login, db, world, monkeypatch
):
    from apps.api.publishing import mail_accounts

    monkeypatch.setattr(mail_accounts, "probe", lambda *a, **k: pytest.fail("Unauthorized probe"))
    login()
    account = save_account(client)
    stored = db.get(MailAccount, account["id"])
    stored.journal_id = world.other_journal.id
    db.commit()
    assert client.get("/api/mail/accounts").json()["accounts"] == []
    for account_id in (account["id"], str(uuid4())):
        assert client.post(f"/api/mail/accounts/{account_id}/verify").status_code == 404
        assert client.post(f"/api/mail/accounts/{account_id}/disconnect").status_code == 404
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "unverified"


@pytest.mark.parametrize("field", ["password", "token", "access_token", "refresh_token"])
def test_mail_raw_credentials_are_rejected(client, login, db, world, field):
    login()
    response = client.post(
        "/api/mail/accounts", json=smtp_input(**{field: "synthetic-never-store"})
    )
    assert response.status_code == 422
    assert "synthetic-never-store" not in response.text
    assert (
        db.scalar(
            select(func.count())
            .select_from(MailAccount)
            .where(MailAccount.journal_id == world.journal.id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "ref",
    ["editorial", "../EDITORIAL", "$EDITORIAL", "A" * 33, "MAIL_CREDENTIAL_EDITORIAL_PASSWORD"],
)
def test_mail_credential_ref_cannot_name_arbitrary_environment_paths(client, login, ref):
    login()
    response = client.post("/api/mail/accounts", json=smtp_input(credential_ref=ref))
    assert response.status_code == 422


def test_smtp_defaults_are_secure(client, login):
    login()
    response = client.post(
        "/api/mail/accounts",
        json={
            "provider": "smtp",
            "address": "editor@publishing.test",
            "display_name": "编辑部",
            "smtp_host": "smtp.publishing.test",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["smtp_port"] == 587
    assert response.json()["tls_mode"] == "starttls"
    assert response.json()["status"] == "unverified"


def test_plaintext_non_mailpit_is_rejected_or_blocked(client, login, monkeypatch):
    import smtplib

    def no_network(*args, **kwargs):
        pytest.fail("Plaintext non-Mailpit targets must be blocked before SMTP connection")

    monkeypatch.setattr(smtplib, "SMTP", no_network)
    login()
    monkeypatch.setenv("MAIL_SMTP_ALLOWLIST", "smtp.publishing.test:1025")
    response = client.post("/api/mail/accounts", json=smtp_input(smtp_host="smtp.publishing.test"))
    if response.status_code == 422:
        return
    assert response.status_code == 200, response.text
    checked = client.post(f"/api/mail/accounts/{response.json()['id']}/verify")
    assert checked.status_code == 200
    assert checked.json()["status"] == "blocked"


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_cloud_missing_credentials_persists_required_without_network(
    client, login, db, monkeypatch, provider
):
    import httpx

    def no_network(*args, **kwargs):
        pytest.fail("Missing server credentials must be detected before any HTTP request")

    # TestClient also uses httpx.Client; guard only real outbound HTTP transport.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.delenv("MAIL_CREDENTIAL_SYNTHETIC_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SYNTHETIC", "synthetic-unrelated-env-value")
    login()
    account = save_account(
        client,
        provider=provider,
        smtp_host=None,
        smtp_port=None,
        tls_mode="starttls",
        auth_mode="oauth2",
        credential_ref="SYNTHETIC",
    )
    assert account["status"] == "unverified"
    assert account["credentials_configured"] is False
    response = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert response.status_code == 200, response.text
    checked = response.json()
    assert checked["status"] == "credentials_required"
    assert checked["last_checked_at"]
    assert checked["last_error"]
    assert "synthetic-unrelated-env-value" not in response.text
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "credentials_required"
    assert client.get("/api/mail/accounts").json()["accounts"] == [checked]


@pytest.mark.parametrize(
    "status,error_code",
    [("verified", None), ("blocked", "smtp_target_blocked"), ("error", "network_error")],
)
def test_probe_status_is_persisted_and_secrets_never_returned_or_audited(
    client, login, db, world, monkeypatch, status, error_code
):
    from apps.api.publishing import mail_accounts
    from packages.mail_adapters import ProbeResult

    secret = "synthetic-probe-credential-never-return"
    monkeypatch.setenv("MAIL_CREDENTIAL_EDITORIAL_PASSWORD", secret)
    monkeypatch.setenv("MAIL_CREDENTIAL_EDITORIAL_JOURNAL_ID", world.journal.id)
    calls = []

    def probe(*args, **kwargs):
        calls.append((args, kwargs))
        return ProbeResult(status=status, error_code=error_code)

    monkeypatch.setattr(mail_accounts, "probe", probe)
    login()
    account = save_account(
        client,
        auth_mode="password",
        tls_mode="starttls",
        username="editor",
        credential_ref="EDITORIAL",
    )
    assert account["status"] == "unverified"
    assert account["credentials_configured"] is True
    response = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert response.status_code == 200, response.text
    checked = response.json()
    assert checked["status"] == status
    assert checked["last_checked_at"]
    if status == "verified":
        assert checked["last_error"] is None
    else:
        assert checked["last_error"]
    assert len(calls) == 1
    db.expire_all()
    stored = db.get(MailAccount, account["id"])
    assert stored.status == status
    assert stored.last_checked_at is not None
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == account["id"])).all()
    assert len(events) >= 2
    assert all(event.journal_id == world.journal.id for event in events)
    assert secret not in json.dumps([event.details for event in events])
    assert secret not in json.dumps(
        {column.name: getattr(stored, column.name) for column in MailAccount.__table__.columns},
        default=str,
    )
    assert secret not in response.text
    assert not {"password", "token", "access_token", "refresh_token"}.intersection(checked)


def test_disconnect_is_persistent_idempotent_and_never_probes(client, login, db, monkeypatch):
    from apps.api.publishing import mail_accounts

    monkeypatch.setattr(
        mail_accounts, "probe", lambda *a, **k: pytest.fail("Disconnect must be local")
    )
    login()
    account = save_account(client)
    first = client.post(f"/api/mail/accounts/{account['id']}/disconnect")
    second = client.post(f"/api/mail/accounts/{account['id']}/disconnect")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "disconnected"
    assert first.json()["enabled"] is False
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "disconnected"
    assert db.get(MailAccount, account["id"]).enabled is False
    assert client.get("/api/mail/accounts").json()["accounts"] == [first.json()]


def test_unknown_probe_error_is_mapped_to_safe_server_text(client, login, db, monkeypatch):
    from apps.api.publishing import mail_accounts
    from packages.mail_adapters import ProbeResult

    raw_error = "synthetic-provider-payload-with-credential"
    monkeypatch.setattr(mail_accounts, "probe", lambda *a, **k: ProbeResult("error", raw_error))
    login()
    account = save_account(client)
    response = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "error"
    assert response.json()["last_error"]
    assert raw_error not in response.text
    db.expire_all()
    assert raw_error not in db.get(MailAccount, account["id"]).last_error
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == account["id"])).all()
    assert raw_error not in json.dumps([event.details for event in events])


def test_disconnected_account_can_be_rebound_without_network(client, login, db, monkeypatch):
    from apps.api.publishing import mail_accounts
    from packages.mail_adapters import ProbeResult

    monkeypatch.setattr(mail_accounts, "probe", lambda *a, **k: ProbeResult("verified"))
    login()
    account = save_account(client)
    verified = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"
    assert verified.json()["last_checked_at"]
    monkeypatch.setattr(
        mail_accounts, "probe", lambda *a, **k: pytest.fail("Rebinding only saves metadata")
    )
    assert client.post(f"/api/mail/accounts/{account['id']}/disconnect").status_code == 200
    rebound = save_account(client, display_name="重新绑定的编辑部")
    assert rebound["id"] == account["id"]
    assert rebound["display_name"] == "重新绑定的编辑部"
    assert rebound["enabled"] is True
    assert rebound["status"] == "unverified"
    assert rebound["last_checked_at"] is None
    assert rebound["last_error"] is None
    assert client.get("/api/mail/accounts").json()["accounts"] == [rebound]
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "unverified"
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == account["id"])).all()
    assert "mail.account_rebound" in {event.action for event in events}


@pytest.mark.parametrize("scoped_to_other_journal", [True, False])
def test_unowned_credential_reference_cannot_be_reused(
    client, login, db, world, monkeypatch, scoped_to_other_journal
):
    import httpx

    secret = "synthetic-other-journal-oauth-token"
    monkeypatch.setenv("MAIL_CREDENTIAL_SHARED_ACCESS_TOKEN", secret)
    if scoped_to_other_journal:
        monkeypatch.setenv("MAIL_CREDENTIAL_SHARED_JOURNAL_ID", world.other_journal.id)
    else:
        monkeypatch.delenv("MAIL_CREDENTIAL_SHARED_JOURNAL_ID", raising=False)
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "handle_request",
        lambda *a, **k: pytest.fail("Other-journal credentials must never reach a provider"),
    )
    login()
    account = save_account(
        client,
        provider="gmail",
        smtp_host=None,
        smtp_port=None,
        auth_mode="oauth2",
        credential_ref="SHARED",
    )
    assert account["credentials_configured"] is False
    response = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "credentials_required"
    assert response.json()["credentials_configured"] is False
    assert secret not in response.text
    db.expire_all()
    assert db.get(MailAccount, account["id"]).status == "credentials_required"
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == account["id"])).all()
    assert secret not in json.dumps([event.details for event in events])


@pytest.mark.parametrize("change", ["role", "journal", "session"])
def test_mail_probe_cannot_save_after_original_authority_changes(
    client, login, db, world, monkeypatch, change
):
    from datetime import timedelta

    from sqlalchemy import update

    from apps.api.publishing import mail_accounts
    from apps.api.publishing.models import LoginSession, Membership, now
    from packages.mail_adapters import ProbeResult

    login()
    account = save_account(client)

    def revoked_during_probe(*args, **kwargs):
        if change == "session":
            db.execute(
                update(LoginSession)
                .where(LoginSession.user_id == world.users["editor"].id)
                .values(expires_at=now() - timedelta(seconds=1))
            )
        else:
            db.execute(
                update(Membership)
                .where(Membership.user_id == world.users["editor"].id)
                .values(
                    **(
                        {"role": "author"}
                        if change == "role"
                        else {"journal_id": world.other_journal.id}
                    )
                )
            )
        db.flush()
        return ProbeResult("verified")

    monkeypatch.setattr(mail_accounts, "probe", revoked_during_probe)
    response = client.post(f"/api/mail/accounts/{account['id']}/verify")
    assert response.status_code == 403
    db.expire_all()
    stored = db.get(MailAccount, account["id"])
    assert stored.status == "unverified" and stored.last_checked_at is None
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == account["id"], AuditEvent.action == "mail.account_verified"
        )
    )
