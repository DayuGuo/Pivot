"""API-level inference recovery never repeats tools or weakens human concurrency guards.

Only httpx.MockTransport is used. Each recovery repeats the exact inference payload,
not the action gateway, and all records live in the shared rolled-back PG fixtures.
"""

import json
import time

import httpx
import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.models import (
    ActionProposal,
    ActionReceipt,
    ManuscriptVersion,
    PublishingChatTurn,
)
from apps.api.publishing.models import AuditEvent, Manuscript, Membership
from packages.model_gateway import editorial
from packages.model_gateway.editorial import EditorialDeepSeekProvider
from tests.api.test_publishing_chat_security import call, respond
from tests.api.test_publishing_failure_audit import completion
from tests.api.test_publishing_intake import URL, complete_data, detail, draft, fill, request_id


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def model(monkeypatch, actions, *, handler_mode="sync"):
    """The adapter, including real retry/timeout code, runs on a fake HTTP transport."""
    sequence = iter(actions)
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        action = next(sequence)
        if callable(action):
            action = action(request)
        if action == "timeout":
            raise httpx.ReadTimeout("PRIVATE-TRANSPORT-ERROR cookie=synthetic", request=request)
        if action == "network":
            raise httpx.ConnectError("PRIVATE-TRANSPORT-ERROR cookie=synthetic", request=request)
        if type(action) is int:
            return httpx.Response(action, text="PRIVATE-PROVIDER-BODY credential=synthetic")
        return httpx.Response(200, json=completion(action))

    async def async_handle(request):
        return handle(request)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-only-recovery-credential")
    # Timing/backoff policy is tested at the transport boundary; these integration
    # cases exercise retry cardinality and transaction safety without sleeping.
    monkeypatch.setattr(editorial, "RETRY_DELAY_SECONDS", 0)
    provider = EditorialDeepSeekProvider(
        live_enabled=True,
        transport=httpx.MockTransport(async_handle if handler_mode == "async" else handle),
    )
    monkeypatch.setattr(chat, "get_editorial_provider", lambda: provider)
    return provider, requests


def track_tools(monkeypatch, after=None):
    original = chat.Runtime.execute
    calls = []

    def execute(runtime, name, arguments):
        calls.append(name)
        result = original(runtime, name, arguments)
        if after:
            after(runtime, name, result)
        return result

    monkeypatch.setattr(chat.Runtime, "execute", execute)
    return calls


def body(message, mid=None):
    return {
        "request_id": request_id(),
        "message": message,
        "context": {"scope": "case" if mid else "journal", "manuscript_id": mid},
    }


def audit(db, world, action, rid):
    rows = db.scalars(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing." + action,
        )
    ).all()
    found = [row for row in rows if row.details.get("request_id") == rid]
    assert len(found) == 1
    return found[0].details


def assert_no_turn_or_receipt(db, rid):
    assert db.scalar(select(PublishingChatTurn).where(PublishingChatTurn.request_id == rid)) is None
    assert db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == rid)) is None


def assert_safe(details, prompt):
    encoded = json.dumps(details)
    for private in (
        prompt,
        "PRIVATE-PROVIDER-BODY",
        "PRIVATE-TRANSPORT-ERROR",
        "synthetic-only-recovery-credential",
        "cookie=synthetic",
    ):
        assert private not in encoded


@pytest.mark.parametrize("handler_mode", ["sync", "async"])
def test_503_recovery_creates_one_draft_receipt_and_turn_and_preserves_each_attempt(
    client, login, db, world, monkeypatch, handler_mode
):
    login("author")
    provider, requests = model(
        monkeypatch,
        [503, [call("create_draft")], [respond("已建立私人准备稿，仍需本人确认投稿。")]],
        handler_mode=handler_mode,
    )
    tools = track_tools(monkeypatch)
    request = body("创建一篇测试准备稿。PRIVATE-RECOVERY-PROMPT")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 200, response.text
    assert len(requests) == 3 and requests[0] == requests[1]
    assert tools == ["create_draft", "respond"]
    assert (
        db.scalar(
            select(func.count())
            .select_from(Manuscript)
            .where(Manuscript.journal_id == world.journal.id)
        )
        == 1
    )
    rid = request["request_id"]
    assert len(db.scalars(select(ActionReceipt).where(ActionReceipt.request_id == rid)).all()) == 1
    assert (
        len(
            db.scalars(select(PublishingChatTurn).where(PublishingChatTurn.request_id == rid)).all()
        )
        == 1
    )
    details = audit(db, world, "chat_completed", rid)
    assert [metric["success"] for metric in details["telemetry"]] == [False, True, True]
    assert sum(metric["input_tokens"] or 0 for metric in details["telemetry"]) == 34
    assert_safe(details, request["message"])
    assert len(provider.last_attempt_telemetry) == 1 and provider.last_telemetry.success
    assert client.post(URL + "/chat", json=request).json() == response.json()
    assert len(requests) == 3 and tools == ["create_draft", "respond"]


def test_retry_after_read_does_not_repeat_read_or_prepare_tool(
    client, login, db, world, monkeypatch
):
    login("author")
    data = fill(client, draft(client))
    mid = data["id"]
    provider, requests = model(
        monkeypatch,
        [
            [call("read_submission", {"manuscript_id": mid})],
            503,
            [call("prepare_review", {"action_type": "submit"})],
            [respond("已准备独立审核，尚未确认投稿。")],
        ],
    )
    tools = track_tools(monkeypatch)
    request = body("读取本稿资料后，准备作者本人投稿审核。", mid)
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 200, response.text
    assert len(requests) == 4 and requests[1] == requests[2]
    assert tools == ["read_submission", "prepare_review", "respond"]
    assert count_proposals(db, mid) == 1
    assert detail(client, mid)["stage"] == "author_draft"
    details = audit(db, world, "chat_completed", request["request_id"])
    assert [metric["success"] for metric in details["telemetry"]] == [True, False, True, True]
    assert len(provider.last_attempt_telemetry) == 1


def count_proposals(db, mid):
    return db.scalar(
        select(func.count()).select_from(ActionProposal).where(ActionProposal.manuscript_id == mid)
    )


def test_exhausted_retry_rolls_back_previously_created_draft_and_retains_safe_attempts(
    client, login, db, world, monkeypatch
):
    login("author")
    provider, requests = model(monkeypatch, [[call("create_draft")], 503, 503])
    tools = track_tools(monkeypatch)
    request = body("创建私人准备稿，失败时不得留下部分业务。")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 502, response.text
    assert len(requests) == 3 and requests[1] == requests[2]
    assert tools == ["create_draft"]
    assert db.scalar(select(Manuscript).where(Manuscript.journal_id == world.journal.id)) is None
    assert_no_turn_or_receipt(db, request["request_id"])
    details = audit(db, world, "chat_failed", request["request_id"])
    assert [metric["success"] for metric in details["telemetry"]] == [True, False, False]
    assert details["error_code"] == "editorial_provider_unavailable"
    assert_safe(details, request["message"])
    assert len(provider.last_attempt_telemetry) == 2
    assert provider.last_telemetry == provider.last_attempt_telemetry[-1]


def test_one_recovery_budget_is_shared_across_rounds_not_reset_per_completion(
    client, login, db, world, monkeypatch
):
    login("author")
    _, requests = model(
        monkeypatch, [503, [call("create_draft")], 503, [respond("不应发起第四次调用")]]
    )
    tools = track_tools(monkeypatch)
    request = body("创建一个测试准备稿。")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 502, response.text
    assert len(requests) == 3 and tools == ["create_draft"]
    assert db.scalar(select(Manuscript).where(Manuscript.journal_id == world.journal.id)) is None
    assert_no_turn_or_receipt(db, request["request_id"])
    details = audit(db, world, "chat_failed", request["request_id"])
    assert [metric["success"] for metric in details["telemetry"]] == [False, True, False]


@pytest.mark.parametrize("status", [401, 402, 429])
def test_nontransient_provider_failure_never_uses_recovery_budget(
    client, login, db, world, monkeypatch, status
):
    login("author")
    _, requests = model(monkeypatch, [status, [respond("不允许重试此错误")]])
    request = body("查看目前的工作状态")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 502 and len(requests) == 1
    assert_no_turn_or_receipt(db, request["request_id"])
    details = audit(db, world, "chat_failed", request["request_id"])
    assert len(details["telemetry"]) == 1 and details["telemetry"][0]["success"] is False
    assert_safe(details, request["message"])


@pytest.mark.parametrize("failure", ["timeout", "network"])
def test_transient_transport_recovery_preserves_failed_and_successful_attempts(
    client, login, db, world, monkeypatch, failure
):
    login("author")
    _, requests = model(monkeypatch, [failure, [respond("仅恢复推理请求，没有执行业务动作。")]])
    request = body("解释当前工作状态")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 200, response.text
    assert len(requests) == 2 and requests[0] == requests[1]
    details = audit(db, world, "chat_completed", request["request_id"])
    assert [metric["success"] for metric in details["telemetry"]] == [False, True]
    assert_safe(details, request["message"])


def test_authority_withdrawal_between_attempts_prevents_retry_and_candidate_commit(
    client, login, db, world, monkeypatch
):
    login("author")
    mid = draft(client)["manuscript_id"]
    before = detail(client, mid)

    def withdraw(request):
        db.execute(
            update(Membership)
            .where(Membership.user_id == world.users["author"].id)
            .values(role="reviewer")
            .execution_options(synchronize_session=False)
        )
        # An independently committed authority change must survive the failed turn.
        # Only a staged candidate exists at this point; no draft business write is committed.
        db.commit()
        return 503

    _, requests = model(
        monkeypatch,
        [
            [call("propose_intake", {"candidates": {"title": "撤权后禁止提交的模型候选"}})],
            withdraw,
            [respond("权限已经撤销，此请求不应到达供应商")],
        ],
    )
    tools = track_tools(monkeypatch)
    request = body("整理作者提供的标题信息", mid)
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 403, response.text
    assert len(requests) == 2 and tools == ["propose_intake"]
    assert_no_turn_or_receipt(db, request["request_id"])
    assert detail(client, mid)["version"]["data"] == before["version"]["data"]
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id, AuditEvent.action == "publishing.chat_failed"
        )
    )


def test_human_edit_during_recovery_wins_over_staged_model_candidate(
    client, login, db, world, monkeypatch
):
    login("author")
    mid = draft(client)["manuscript_id"]
    original = detail(client, mid)
    human = complete_data()
    human["title"] = "作者在模型等待期间亲自保存的合成标题"

    def edit_then_fail(request):
        saved = client.patch(
            f"{URL}/manuscripts/{mid}/intake",
            json={
                "request_id": request_id(),
                "expected_revision": original["revision"],
                "data": human,
            },
        )
        assert saved.status_code == 200, saved.text
        return 503

    _, requests = model(
        monkeypatch,
        [
            [call("propose_intake", {"candidates": {"title": "不能覆盖人工修改的模型标题"}})],
            edit_then_fail,
            [respond("不能向用户返回本条过期结果")],
        ],
    )
    tools = track_tools(monkeypatch)
    request = body("整理当前稿件标题", mid)
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 409, response.text
    assert len(requests) == 3 and requests[1] == requests[2]
    assert tools == ["propose_intake", "respond"]
    assert_no_turn_or_receipt(db, request["request_id"])
    current = detail(client, mid)
    assert current["version"]["data"]["title"] == human["title"]
    assert current["field_sources"]["title"]["source"] == "human_edit"


def test_expired_turn_after_tool_rolls_back_without_another_network_attempt(
    client, login, db, world, monkeypatch
):
    login("author")
    provider, requests = model(monkeypatch, [[call("create_draft")], [respond("不应继续等待模型")]])

    def expire(runtime, name, result):
        if name == "create_draft":
            provider.set_deadline(time.monotonic() - 1)

    tools = track_tools(monkeypatch, expire)
    request = body("创建一个测试准备稿，超出整轮截止时间时不得提交。")
    response = client.post(URL + "/chat", json=request)
    assert response.status_code == 502, response.text
    assert len(requests) == 1 and tools == ["create_draft"]
    assert db.scalar(select(Manuscript).where(Manuscript.journal_id == world.journal.id)) is None
    assert_no_turn_or_receipt(db, request["request_id"])
    details = audit(db, world, "chat_failed", request["request_id"])
    assert details["error_code"] == "editorial_provider_deadline"


def test_deadline_after_actual_candidate_apply_rolls_back_all_turn_writes(
    client, login, db, world, monkeypatch
):
    login("author")
    mid = draft(client)["manuscript_id"]
    before = detail(client, mid)
    candidate = "本研究使用完全合成材料验证数据库事务；此摘要仅在事务内应用，超时之后必须完整回滚，不涉及真实研究数据。"
    provider, requests = model(
        monkeypatch,
        [
            [call("propose_intake", {"candidates": {"abstract": candidate}})],
            [respond("本条超时结果不得提交或展示给用户。")],
        ],
    )
    original = chat.Runtime.apply
    applied = []

    def apply_then_expire(runtime):
        original(runtime)
        # Observe a real gateway write before the simulated lock/apply deadline.
        # This distinguishes rollback from merely never applying the candidate.
        abstract = db.scalar(
            select(ManuscriptVersion.abstract).where(
                ManuscriptVersion.id == before["version"]["id"]
            )
        )
        applied.append(abstract)
        provider.set_deadline(time.monotonic() - 1)

    monkeypatch.setattr(chat.Runtime, "apply", apply_then_expire)
    request = body("整理当前稿件的摘要候选", mid)
    response = client.post(URL + "/chat", json=request)
    assert applied == [candidate]
    assert response.status_code == 502, response.text
    assert len(requests) == 2
    assert_no_turn_or_receipt(db, request["request_id"])
    current = detail(client, mid)
    assert current["revision"] == before["revision"]
    assert current["version"]["data"] == before["version"]["data"]
    assert current["field_sources"] == before["field_sources"]
    assert not db.scalar(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action == "publishing.intake_saved",
        )
    )
    details = audit(db, world, "chat_failed", request["request_id"])
    assert details["error_code"] == "editorial_provider_deadline"
    assert [metric["success"] for metric in details["telemetry"]] == [True, True]
