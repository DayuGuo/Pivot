"""Real PostgreSQL + actual DeepSeek HTTP adapter under a deterministic fake upstream.

These exercise the production tool loop, not the old contextual Mock. No live key.
"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from apps.api.publishing import editorial_chat
from apps.api.publishing.editorial_agent import TOOLS
from apps.api.publishing.editorial_chat import EditorialChatTurn
from apps.api.publishing.editorial_demo import DemoWorkspaceState
from apps.api.publishing.models import AuditEvent
from packages.model_gateway.editorial import EditorialDeepSeekProvider

from .test_editorial_chat import URL, payload


def tool(name, args, call_id=None):
    return {
        "id": call_id or uuid4().hex,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def completion(*calls, content=None):
    return {
        "choices": [
            {
                "finish_reason": "tool_calls" if calls else "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    **({"tool_calls": list(calls)} if calls else {}),
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def inspect(material="summary", case="demo-001", version="v3", **extra):
    return tool(
        "inspect_manuscript", {"case_id": case, "version": version, "material": material, **extra}
    )


def done(content="当前稿件需人工核验，建议先检查证据。", citations=None):
    return completion(tool("respond", {"content": content, "citation_ids": citations or []}))


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-fixture-credential-never-live")
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("EDITORIAL_MODEL_LIVE_ENABLED", "true")

    def install(*replies):
        pending = list(replies)
        requests = []

        def handler(request):
            assert request.url == "https://api.deepseek.com/chat/completions"
            body = json.loads(request.content)
            assert body["model"] == "deepseek-flash"
            requests.append(body)
            assert pending, "Unexpected model round"
            response = pending.pop(0)
            if callable(response):
                response = response()
            if isinstance(response, Exception):
                raise response
            return httpx.Response(200, json=response)

        provider = EditorialDeepSeekProvider(
            live_enabled=True, transport=httpx.MockTransport(handler)
        )
        monkeypatch.setattr(editorial_chat, "get_editorial_provider", lambda: provider)
        return requests

    return install


def post(client, message="请查看当前稿件状态并给出建议", **context):
    return client.post(URL, json=payload(message, **context))


@pytest.fixture(autouse=True)
def isolated_rows(db, world):
    db.info["actor_ids"] = [user.id for user in world.users.values()]


def turns(db):
    return db.scalar(
        select(func.count())
        .select_from(EditorialChatTurn)
        .where(EditorialChatTurn.user_id.in_(db.info["actor_ids"]))
    )


def state(db):
    return db.scalar(
        select(DemoWorkspaceState).where(DemoWorkspaceState.user_id.in_(db.info["actor_ids"]))
    )


def test_real_transport_loop_uses_actor_context_tool_result_citations_and_telemetry(
    client, login, world, db, upstream
):
    login("chief_editor")
    requests = upstream(completion(inspect()), done("当前处于修回核验。", ["e1"]))
    body = payload()
    response = client.post(URL, json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assistant = data["messages"][1]
    assert data["provider"] == assistant["provider"] == "deepseek"
    assert "AI 建议" in assistant["content"]
    assert assistant["references"][0]["anchor"]["version"] == "v3"
    assert assistant["tool_receipts"] == [
        {"tool": "inspect_manuscript", "status": "read", "case_id": "demo-001"}
    ]
    context = requests[0]["messages"][1]["content"]
    assert '"role": "chief_editor"' in context and world.journal.id in context
    assert world.users["chief_editor"].password_hash not in json.dumps(requests)
    assert "offline-fixture-credential-never-live" not in json.dumps(requests)
    result = json.loads(requests[1]["messages"][-1]["content"])
    assert result["stage"] == "修回核验" and result["citation_id"] == "e1"
    assert (
        requests[1]["messages"][-1]["tool_call_id"]
        == requests[1]["messages"][-2]["tool_calls"][0]["id"]
    )
    assert client.get(URL).json()["messages"] == data["messages"]
    # Same successful request replays exact persisted response, no extra model call.
    assert client.post(URL, json=body).json() == data
    assert len(requests) == 2 and turns(db) == 1
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "editorial_demo.chat_turn",
            AuditEvent.actor_id.in_(db.info["actor_ids"]),
        )
    )
    assert len(audit.details["telemetry"]) == 2
    assert audit.details["telemetry"][0]["input_tokens"] == 100
    assert audit.details["telemetry"][0]["cost_usd"] is None
    assert "content" not in str(audit.details) and "credential" not in str(audit.details)


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_roles_denied_before_provider_call(client, login, upstream, role):
    requests = upstream()
    login(role)
    assert post(client).status_code == 403
    assert requests == []
    assert client.get(URL + "/model").status_code == 403


@pytest.mark.parametrize(
    "call",
    [
        tool("send_email", {"to": "outsider@example.org"}),
        tool("approve_email", {"approved": True}),
        tool("make_final_decision", {"outcome": "accept"}),
        tool("execute_sql", {"sql": "DROP TABLE users"}),
        tool(
            "inspect_manuscript",
            {"case_id": "demo-001", "version": "v3", "material": "summary", "role": "chief_editor"},
        ),
        inspect(case="demo-002", version="v1"),
        inspect(version="v1"),
        inspect(case="missing", version="v1"),
        tool("respond", {"content": "假的引用", "citation_ids": ["forged"]}),
    ],
)
def test_untrusted_calls_scope_version_and_citations_leave_no_turn_or_mutation(
    client, login, db, upstream, call
):
    login()
    upstream(completion(call), done())
    response = post(client)
    assert response.status_code == 422, response.text
    assert turns(db) == 0 and state(db) is None
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "editorial_agent.failed",
            AuditEvent.actor_id.in_(db.info["actor_ids"]),
        )
    )
    assert event is not None and "content" not in event.details


def test_named_authorized_other_case_can_be_read(client, login, upstream):
    login()
    upstream(
        completion(inspect(case="demo-002", version="v1")), done("另一稿件材料已读取。", ["e1"])
    )
    assert post(client, "请查看 ENV-2026-0130 这篇稿件的状态").status_code == 200


def test_old_version_requires_explicit_request_and_preserves_snapshot(client, login, upstream):
    login()
    upstream(completion(inspect(version="v2")), done(citations=["e1"]))
    result = post(client, "比较 v2 旧版的状态").json()
    assert result["messages"][1]["context"]["version"] == "v3"
    assert result["messages"][1]["references"][0]["anchor"]["version"] == "v2"


def select_reviewer(client, db):
    data = client.get("/api/editorial-demo").json()
    case = next(c for c in data["cases"] if c["id"] == "demo-001")
    res = client.patch(
        "/api/editorial-demo/cases/demo-001/state",
        json={
            "expected_revision": data["states"]["demo-001"]["revision"],
            "patch": {"selected_reviewers": [case["candidates"][0]["id"]]},
        },
    )
    assert res.status_code == 200
    return case


def invitation():
    return tool(
        "prepare_invitation",
        {
            "case_id": "demo-001",
            "version": "v3",
            "subject": "合成稿件评审邀请草稿",
            "body": "您好，请评阅本次合成研究。请负责人检查利益冲突与期限。",
        },
    )


def test_generated_private_invitation_persists_without_sending_or_outcome(
    client, login, db, upstream
):
    login()
    case = select_reviewer(client, db)
    upstream(completion(inspect(), invitation()), done("草稿待负责人审核。", ["e1"]))
    response = post(client, "请为当前稿件起草邀请信")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state_changed"] is True
    saved = state(db).content
    assert saved["invitation"]["body"] == "您好，请评阅本次合成研究。请负责人检查利益冲突与期限。"
    assert saved["invitation"]["to"] == case["candidates"][0]["email"]
    assert saved["decision"]["outcome"] == ""
    assert data["messages"][1]["tool_receipts"][-1]["status"] == "draft_saved"
    assert "未发送" in data["messages"][1]["content"]


@pytest.mark.parametrize(
    "failure",
    [
        completion(tool("send_email", {})),
        completion(tool("respond", {"content": "完成", "citation_ids": ["bad"]})),
        httpx.ReadTimeout("no raw details"),
    ],
)
def test_staged_draft_rolls_back_on_later_provider_or_policy_failure(
    client, login, db, upstream, failure
):
    login()
    select_reviewer(client, db)
    before = state(db).revision
    upstream(completion(inspect(), invitation()), failure)
    response = post(client, "请准备邀请草稿")
    assert response.status_code in {422, 503}, response.text
    assert state(db).revision == before and state(db).content["invitation"]["body"] == ""
    assert turns(db) == 0


def test_existing_human_text_preserved_even_after_model_prepares(client, login, db, upstream):
    login()
    select_reviewer(client, db)
    before = state(db)
    response = client.patch(
        "/api/editorial-demo/cases/demo-001/state",
        json={
            "expected_revision": before.revision,
            "patch": {
                "invitation": {
                    "to": "person@review.test",
                    "subject": "人工主题",
                    "body": "人工正文",
                    "due": "",
                }
            },
        },
    )
    assert response.status_code == 200
    upstream(completion(inspect(), invitation()), done("等待人工审核"))
    result = post(client, "准备邀请草稿").json()
    assert not result["state_changed"]
    assert state(db).content["invitation"]["body"] == "人工正文"
    assert "已有邀请草稿" in result["messages"][1]["content"]


def test_implicit_draft_injection_cannot_mutate(client, login, db, upstream):
    login()
    select_reviewer(client, db)
    upstream(completion(inspect(), invitation()), done())
    assert post(client, "总结这篇文章").status_code == 422
    assert state(db).content["invitation"]["body"] == "" and turns(db) == 0


def test_no_selected_reviewer_is_not_invented(client, login, db, upstream):
    login()
    upstream(completion(inspect(), invitation()), done())
    result = post(client, "请起草邀请信").json()
    assert not result["state_changed"] and state(db) is None
    assert "先在候选人页面选择" in result["messages"][1]["content"]


def test_neutral_decision_review_has_no_outcome_tool(client, login, db, upstream):
    login("chief_editor")
    upstream(
        completion(tool("open_decision_review", {"case_id": "demo-001", "version": "v3"})),
        done("请负责人审核，不构成正式决定"),
    )
    result = post(client, "请帮我准备审核材料").json()
    assert result["messages"][1]["action"] == {
        "type": "navigate",
        "case_id": "demo-001",
        "view": "revision",
        "prepare": "decision",
    }
    assert not result["state_changed"] and state(db) is None
    assert not any(
        "approve" in t["function"]["name"] or "send" in t["function"]["name"] for t in TOOLS
    )


def test_tool_loop_budget_and_repeat_ids_fail_closed(client, login, db, upstream):
    login()
    call = inspect()
    upstream(completion(call), completion(call))
    assert post(client).status_code == 422 and turns(db) == 0
    upstream(completion(inspect()), completion(inspect()), completion(inspect()))
    assert post(client).status_code == 422 and turns(db) == 0


def test_configuration_and_provider_failures_are_explicit_not_mock(client, login, db, monkeypatch):
    login()
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("EDITORIAL_MODEL_LIVE_ENABLED", "true")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    status = client.get(URL + "/model").json()
    assert status["provider"] == "deepseek" and not status["available"]
    assert not status["email_send_enabled"]
    assert "final_decision" in status["human_confirmation_required"]
    assert post(client).status_code == 503 and turns(db) == 0


def test_history_is_same_actor_context_bounded_and_not_other_user_drafts(
    client, login, db, upstream
):
    login("chief_editor")
    upstream(done("另一用户私有回复"))
    assert post(client, "主编秘密问题").status_code == 200
    login()
    upstream(done("不同稿件"))
    assert post(client, "另一篇上下文", case_id="demo-002", version="v1").status_code == 200
    requests = upstream(done("自己的上下文"))
    assert post(client, "本稿件第一问").status_code == 200
    assert "主编秘密问题" not in json.dumps(requests) and "另一篇上下文" not in json.dumps(requests)
    requests = upstream(done("下一问"))
    assert post(client, "继续说下一步").status_code == 200
    assert "本稿件第一问" in json.dumps(requests, ensure_ascii=False)


def test_scoped_task_search_and_exact_issue_text(client, login, upstream):
    login()
    requests = upstream(
        completion(tool("list_tasks", {"stage": "reviewers", "query": "", "today_only": False})),
        done(),
    )
    response = post(client, "查找等待邀请审稿人的任务", scope="journal")
    assert response.status_code == 200
    assert response.json()["messages"][1]["action"]["stage"] == "reviewers"
    assert len(json.loads(requests[1]["messages"][-1]["content"])["tasks"]) == 1
    requests = upstream(completion(inspect(material="issues")), done("查看原文证据", ["e1"]))
    response = post(client, "有哪些问题需要核验")
    assert response.status_code == 200
    issues = json.loads(requests[1]["messages"][-1]["content"])["issues"]
    assert (
        issues
        and issues[0]["quote"] == response.json()["messages"][1]["references"][0]["anchor"]["quote"]
    )


def test_state_changes_during_model_wait_preserve_newer_human_content(client, login, db, upstream):
    login()
    select_reviewer(client, db)

    def concurrent_human_edit():
        row = state(db)
        row.content = {
            **row.content,
            "invitation": {
                "to": "person@review.test",
                "subject": "等待模型期间的人类主题",
                "body": "最新人工正文",
                "due": "",
            },
        }
        row.revision += 1
        db.flush()
        return done("请检查草稿")

    upstream(completion(inspect(), invitation()), concurrent_human_edit)
    response = post(client, "准备邀请草稿")
    assert response.status_code == 200
    assert not response.json()["state_changed"]
    assert state(db).content["invitation"]["body"] == "最新人工正文"
    assert "工作区已更新" in response.json()["messages"][1]["content"]


def test_role_revocation_during_model_wait_blocks_final_commit(client, login, db, world, upstream):
    from apps.api.publishing.models import Membership

    login()

    def revoke_before_final():
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == world.users["editor"].id,
                Membership.journal_id == world.journal.id,
            )
        )
        membership.role = "author"
        db.flush()
        return done("不会使用过期权限")

    upstream(completion(inspect()), revoke_before_final)
    assert post(client).status_code == 422
    assert turns(db) == 0 and state(db) is None


def test_third_batch_cannot_exceed_eight_tool_calls(client, login, db, upstream):
    login()
    upstream(*(completion(inspect(), inspect(), inspect()) for _ in range(3)))
    assert post(client).status_code == 422
    assert turns(db) == 0


@pytest.mark.parametrize(
    "message",
    [
        "为 ENV-2026-9999 准备邀请草稿",
        "为 ENV-2026-0130 准备邀请草稿",
        "为 ENV-2026-0129 与 ENV-2026-0130 准备邀请草稿",
        "不要准备邀请草稿，只查询状态",
        "Do not draft an invitation, only read status",
    ],
)
def test_exact_other_unknown_multiple_or_negated_draft_never_writes_current_case(
    client, login, db, upstream, message
):
    login()
    select_reviewer(client, db)
    upstream(completion(inspect(), invitation()), done("不能执行这个写入"))
    assert post(client, message).status_code == 422
    assert turns(db) == 0 and state(db).content["invitation"]["body"] == ""


def test_model_prose_cannot_replace_deterministic_execution_status(client, login, upstream):
    login()
    upstream(completion(content="已发送邮件并正式录用"))
    response = post(client)
    assert response.status_code == 200
    reply = response.json()["messages"][1]
    assert reply["tool_receipts"] == []
    assert "本轮未发送邮件、未发布正式决定" in reply["content"]
    assert not response.json()["state_changed"]
