"""Failed model turns roll back business state and retain safe, authorized diagnostics."""

import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete, func, select, update

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.models import ActionReceipt, PublishingChatTurn
from apps.api.publishing.models import AuditEvent, LoginSession, Manuscript, Membership
from packages.model_gateway.editorial import EditorialDeepSeekProvider
from packages.model_gateway.gateway import GatewayError, Telemetry
from tests.api.test_publishing_chat_security import call, respond
from tests.api.test_publishing_intake import URL, detail, draft, request_id


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def post(client, message="说明我的当前工作", mid=None):
    rid = request_id()
    response = client.post(
        URL + "/chat",
        json={
            "request_id": rid,
            "message": message,
            "context": {"scope": "case" if mid else "journal", "manuscript_id": mid},
        },
    )
    return rid, response


def completion(calls):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": calls},
            }
        ],
        "usage": {"prompt_tokens": 17, "completion_tokens": 9},
    }


def transport(monkeypatch, actions):
    sequence = iter(actions)
    requests = []

    def handle(request):
        requests.append(request)
        action = next(sequence)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, int):
            return httpx.Response(action, text="PRIVATE-SUPPLIER-BODY cookie=not-for-audit")
        return httpx.Response(200, json=completion(action))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-only-failure-credential")
    adapter = EditorialDeepSeekProvider(live_enabled=True, transport=httpx.MockTransport(handle))
    monkeypatch.setattr(chat, "get_editorial_provider", lambda: adapter)
    return adapter, requests


def failed(db, world, rid):
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing.chat_failed",
        )
    ).all()
    assert len(events) == 1
    event = events[0]
    assert set(event.details) == {"request_id", "error_code", "telemetry", "synthetic"}
    assert event.details["request_id"] == rid and event.details["synthetic"] is True
    assert event.actor_id == world.users["author"].id
    assert db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == rid)) is None
    assert db.scalar(select(PublishingChatTurn).where(PublishingChatTurn.request_id == rid)) is None
    return event.details


def test_partial_created_draft_is_rolled_back_but_failed_supplier_telemetry_is_committed(
    client, login, db, world, monkeypatch
):
    login("author")
    adapter, requests = transport(monkeypatch, [[call("create_draft")], 503, 503])
    prompt = "创建一个私人测试准备稿。PRIVATE-PROMPT-CANARY"
    rid, response = post(client, prompt)
    assert response.status_code == 502, response.text
    assert len(requests) == 3 and adapter.last_telemetry.success is False
    assert (
        db.scalar(
            select(func.count())
            .select_from(Manuscript)
            .where(Manuscript.journal_id == world.journal.id)
        )
        == 0
    )
    details = failed(db, world, rid)
    assert details["error_code"] == "editorial_provider_unavailable"
    assert [item["success"] for item in details["telemetry"]] == [True, False, False]
    assert details["telemetry"][0]["input_tokens"] == 17
    assert details["telemetry"][1]["error_code"] == "editorial_provider_unavailable"
    db.expire_all()
    assert (
        db.get(
            AuditEvent,
            db.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.journal_id == world.journal.id,
                    AuditEvent.action == "publishing.chat_failed",
                )
            ),
        ).action
        == "publishing.chat_failed"
    )
    encoded = json.dumps(details)
    for secret in (
        prompt,
        "PRIVATE-SUPPLIER-BODY",
        "synthetic-only-failure-credential",
        "not-for-audit",
        "https://api.deepseek.com",
    ):
        assert secret not in encoded
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing.draft_created",
        )
    )


def test_timeout_has_distinct_safe_code_and_no_sensitive_exception_text(
    client, login, db, world, monkeypatch
):
    login("author")
    transport(
        monkeypatch,
        [httpx.ReadTimeout("PRIVATE-TIMEOUT session=secret prompt=private")] * 2,
    )
    rid, response = post(client)
    assert response.status_code == 502
    details = failed(db, world, rid)
    assert details["error_code"] == "editorial_provider_timeout"
    assert len(details["telemetry"]) == 2
    assert details["telemetry"][0]["success"] is False
    assert details["telemetry"][0]["error_code"] == "editorial_provider_timeout"
    assert "PRIVATE-TIMEOUT" not in json.dumps(details) and "PRIVATE-TIMEOUT" not in response.text


def test_staged_intake_candidate_is_not_saved_when_later_provider_call_fails(
    client, login, db, world, monkeypatch
):
    login("author")
    mid = draft(client)["manuscript_id"]
    before = detail(client, mid)
    transport(
        monkeypatch,
        [
            [call("propose_intake", {"candidates": {"title": "PRIVATE-UNSAVED-CANDIDATE"}})],
            503,
            503,
        ],
    )
    rid, response = post(client, "整理我提供的私人资料", mid)
    assert response.status_code == 502
    after = detail(client, mid)
    assert after["revision"] == before["revision"]
    assert after["version"] == before["version"]
    assert after["field_sources"] == before["field_sources"]
    details = failed(db, world, rid)
    assert "PRIVATE-UNSAVED-CANDIDATE" not in json.dumps(details)
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing.intake_saved",
        )
    )


def test_arbitrary_gateway_message_and_telemetry_fields_are_not_a_diagnostic_channel(
    client, login, db, world, monkeypatch
):
    login("author")
    sensitive = "sk-synthetic-error-only-cookie-prompt-body"
    adapter = SimpleNamespace(name="deepseek", last_telemetry=None)

    def fail(messages, tools):
        adapter.last_telemetry = Telemetry(
            sensitive,
            sensitive,
            False,
            sensitive,
            sensitive,
            sensitive,
            cost_usd=sensitive,
            cost_basis=sensitive,
            rework_count=sensitive,
            error_code=sensitive,
        )
        raise GatewayError(sensitive)

    adapter.completion = fail
    monkeypatch.setattr(chat, "get_editorial_provider", lambda: adapter)
    rid, response = post(client)
    assert response.status_code == 502
    details = failed(db, world, rid)
    assert details["error_code"] == "publishing_turn_failed"
    assert details["telemetry"][0]["provider"] == "unavailable"
    assert details["telemetry"][0]["error_code"] == "editorial_provider_request_failed"
    assert details["telemetry"][0]["input_tokens"] is None
    assert sensitive not in json.dumps(details) and sensitive not in response.text


def test_each_round_resets_last_telemetry_instead_of_duplicating_prior_usage(
    client, login, db, world, monkeypatch
):
    login("author")
    adapter = SimpleNamespace(name="deepseek", last_telemetry=None, calls=0)

    def complete(messages, tools):
        assert adapter.last_telemetry is None
        adapter.calls += 1
        if adapter.calls == 1:
            adapter.last_telemetry = Telemetry("deepseek", "deepseek-flash", True, 3, 17, 9)
            return completion([call("list_my_work")])
        raise GatewayError("editorial_provider_timeout")  # This fake has no second usage data.

    adapter.completion = complete
    monkeypatch.setattr(chat, "get_editorial_provider", lambda: adapter)
    rid, response = post(client)
    assert response.status_code == 502 and adapter.calls == 2
    details = failed(db, world, rid)
    assert len(details["telemetry"]) == 1
    assert details["telemetry"][0]["input_tokens"] == 17


@pytest.mark.parametrize("withdrawal", ["role", "session"])
def test_failed_turn_cannot_restore_old_authority_to_append_an_audit(
    client, login, db, world, monkeypatch, withdrawal
):
    login("author")
    adapter = SimpleNamespace(name="deepseek", last_telemetry=None)

    def revoke(messages, tools):
        user_id = world.users["author"].id
        statement = (
            update(Membership).where(Membership.user_id == user_id).values(role="reviewer")
            if withdrawal == "role"
            else delete(LoginSession).where(LoginSession.user_id == user_id)
        )
        db.execute(statement.execution_options(synchronize_session=False))
        # Commit the external authority change before failure, so business rollback
        # cannot undo it. The fixture's outer transaction still removes all test data.
        db.commit()
        adapter.last_telemetry = Telemetry(
            "deepseek", "deepseek-flash", False, 4, error_code="editorial_provider_timeout"
        )
        raise GatewayError("editorial_provider_timeout")

    adapter.completion = revoke
    monkeypatch.setattr(chat, "get_editorial_provider", lambda: adapter)
    rid, response = post(client)
    assert response.status_code == 502
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id, AuditEvent.action == "publishing.chat_failed"
        )
    )
    assert not db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == rid))
    assert not db.scalar(select(PublishingChatTurn).where(PublishingChatTurn.request_id == rid))
    if withdrawal == "role":
        assert (
            db.scalar(select(Membership.role).where(Membership.user_id == world.users["author"].id))
            == "reviewer"
        )
    else:
        assert not db.scalar(
            select(LoginSession).where(LoginSession.user_id == world.users["author"].id)
        )


def test_success_audit_is_correlated_without_a_failure_event(client, login, db, world, monkeypatch):
    login("author")
    transport(monkeypatch, [[respond("安全的合成查询回答。")]])
    rid, response = post(client)
    assert response.status_code == 200, response.text
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing.chat_completed",
        )
    )
    assert event.details["request_id"] == rid
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id, AuditEvent.action == "publishing.chat_failed"
        )
    )
