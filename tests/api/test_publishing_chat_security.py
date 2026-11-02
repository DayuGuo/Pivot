"""Publishing chat security exercised with scripted, credential-free provider calls."""

import json

import pytest
from sqlalchemy import delete, event, func, select, update

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.models import (
    Assignment,
    HumanConfirmation,
    ManuscriptVersion,
    PublishingChatTurn,
)
from apps.api.publishing.models import LoginSession, Manuscript, Membership, now
from tests.api.test_publishing_intake import (
    URL,
    detail,
    draft,
    fill,
    prepare,
    request_id,
)


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "private-files"))


def call(name, arguments=None):
    return {
        "id": "tool_" + request_id().replace("-", ""),
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments or {})},
    }


def respond(content="已读取当前材料。", evidence_ids=None):
    return call("respond", {"content": content, "evidence_ids": evidence_ids or []})


@pytest.fixture
def scripted_provider(monkeypatch):
    class ScriptedProvider:
        name = "deepseek"
        last_telemetry = None

        def __init__(self, rounds):
            self.rounds = iter(rounds)
            self.calls = []

        def completion(self, messages, tools):
            self.calls.append({"messages": list(messages), "tools": tools})
            value = next(self.rounds)
            if callable(value):
                value = value(messages, tools)
            return {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {"role": "assistant", "content": None, "tool_calls": value},
                    }
                ]
            }

    def install(rounds):
        provider = ScriptedProvider(rounds)
        monkeypatch.setattr(chat, "get_editorial_provider", lambda: provider)
        return provider

    return install


def post_chat(client, message, manuscript_id=None):
    return client.post(
        URL + "/chat",
        json={
            "request_id": request_id(),
            "message": message,
            "context": {
                "scope": "case" if manuscript_id else "journal",
                "manuscript_id": manuscript_id,
            },
        },
    )


def turn_count(db):
    return db.scalar(select(func.count()).select_from(PublishingChatTurn))


def submit_for_precheck(client, login):
    login("author")
    data = fill(client, draft(client))
    proposal = prepare(client, data)
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text
    return data


def test_failed_final_protocol_rolls_back_created_draft_and_chat(
    client, login, db, scripted_provider
):
    login("author")
    manuscripts = db.scalar(select(func.count()).select_from(Manuscript))
    turns = turn_count(db)
    provider = scripted_provider([[call("create_draft")], [call("confirm_proposal", {})]])
    response = post_chat(client, "创建一篇私人测试准备稿")
    assert response.status_code == 502, response.text
    assert db.scalar(select(func.count()).select_from(Manuscript)) == manuscripts
    assert turn_count(db) == turns
    forbidden = {"confirm_proposal", "send_email", "approve_email", "accept", "reject", "publish"}
    for request in provider.calls:
        names = {t["function"]["name"] for t in request["tools"]}
        assert names.isdisjoint(forbidden)


@pytest.mark.parametrize(
    "message",
    ["不要创建新稿件，只告诉我当前工作情况。", "Do not create a draft; only show my work."],
)
def test_explicit_request_not_to_create_cannot_be_overridden_by_model_tool(
    client, login, db, scripted_provider, message
):
    login("author")
    before = db.scalar(select(func.count()).select_from(Manuscript))
    before_turns = turn_count(db)
    scripted_provider([[call("create_draft"), respond()]])
    response = post_chat(client, message)
    assert response.status_code in {422, 502}, response.text
    assert db.scalar(select(func.count()).select_from(Manuscript)) == before
    assert turn_count(db) == before_turns


def test_ninth_tool_call_exceeds_total_budget_and_saves_nothing(
    client, login, db, scripted_provider
):
    login("author")
    before = turn_count(db)
    provider = scripted_provider(
        [
            [call("list_my_work") for _ in range(4)],
            [call("list_my_work") for _ in range(4)],
            [respond()],
        ]
    )
    response = post_chat(client, "查看我的工作")
    assert response.status_code == 502, response.text
    assert len(provider.calls) == 3
    assert [tool["function"]["name"] for tool in provider.calls[-1]["tools"]] == ["respond"]
    assert turn_count(db) == before


def test_provider_failure_does_not_apply_staged_intake(client, login, db, scripted_provider):
    login("author")
    before_turns = turn_count(db)
    created = draft(client)
    before = detail(client, created["manuscript_id"])
    scripted_provider(
        [[call("propose_intake", {"candidates": {"title": "模型候选，不能部分落库"}})], []]
    )
    response = post_chat(client, "帮我整理投稿标题", before["id"])
    assert response.status_code == 502, response.text
    after = detail(client, before["id"])
    assert after["revision"] == before["revision"]
    assert after["version"]["data"] == before["version"]["data"]
    assert turn_count(db) == before_turns


@pytest.mark.parametrize("revocation", ["session", "role"])
def test_revocation_during_provider_call_rejects_whole_turn(
    client, login, db, world, scripted_provider, revocation
):
    login("author")
    before_turns = turn_count(db)
    created = draft(client)
    mid = created["manuscript_id"]
    before = detail(client, mid)

    def revoke_during_network(messages, tools):
        uid = world.users["author"].id
        statement = (
            delete(LoginSession).where(LoginSession.user_id == uid)
            if revocation == "session"
            else update(Membership).where(Membership.user_id == uid).values(role="reviewer")
        )
        db.execute(statement.execution_options(synchronize_session=False))
        return [respond()]

    scripted_provider(
        [
            [call("propose_intake", {"candidates": {"title": "撤权期间禁止保存"}})],
            revoke_during_network,
        ]
    )
    response = post_chat(client, "整理我提供的标题", mid)
    assert response.status_code in {401, 403}, response.text
    db.expire_all()
    version = db.get(ManuscriptVersion, before["version"]["id"])
    assert version.title == before["version"]["data"]["title"]
    assert turn_count(db) == before_turns


@pytest.mark.parametrize("exposure", ["read_submission", "list_my_work", "initial_tasks"])
def test_journal_history_rechecks_every_read_object_even_without_final_citations(
    client, login, db, world, scripted_provider, exposure
):
    data = submit_for_precheck(client, login)
    login("editor")
    mid = data["id"]
    canary = "仅当前分派编辑可读取的正文 " + request_id()
    rounds = {
        "read_submission": [[call("read_submission", {"manuscript_id": mid})], [respond(canary)]],
        "list_my_work": [[call("list_my_work")], [respond(canary)]],
        "initial_tasks": [[respond(canary)]],
    }
    scripted_provider(rounds[exposure])
    response = post_chat(client, "从我的工作中读取稿件并回答")
    assert response.status_code == 200, response.text
    assert canary in client.get(URL + "/chat").text
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.user_id == world.users["editor"].id)
        .values(ends_at=now())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert client.get(f"{URL}/manuscripts/{mid}").status_code == 404
    response = client.get(URL + "/chat")
    assert response.status_code == 200, response.text
    assert canary not in response.text


def test_revoked_role_cannot_read_more_material_or_send_second_provider_request(
    client, login, db, world, scripted_provider
):
    data = submit_for_precheck(client, login)
    login("chief_editor")
    before_turns = turn_count(db)

    def revoke_before_returning_tool(messages, tools):
        db.execute(
            update(Membership)
            .where(Membership.user_id == world.users["chief_editor"].id)
            .values(role="reviewer")
            .execution_options(synchronize_session=False)
        )
        return [call("read_submission", {"manuscript_id": data["id"]})]

    provider = scripted_provider([revoke_before_returning_tool, [respond()]])
    response = post_chat(client, "读取当前工作中的稿件材料")
    assert response.status_code == 403, response.text
    assert len(provider.calls) == 1, "No new material may be sent to the provider after revocation"
    assert turn_count(db) == before_turns


def test_idempotent_journal_reply_cannot_bypass_assignment_revocation(
    client, login, db, world, scripted_provider
):
    data = submit_for_precheck(client, login)
    login("editor")
    mid = data["id"]
    scripted_provider(
        [[call("read_submission", {"manuscript_id": mid})], [respond("保密稿件内容")]]
    )
    body = {
        "request_id": request_id(),
        "message": "读取当前工作中的稿件",
        "context": {"scope": "journal", "manuscript_id": None},
    }
    first = client.post(URL + "/chat", json=body)
    assert first.status_code == 200, first.text
    assert client.post(URL + "/chat", json=body).json() == first.json()
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.user_id == world.users["editor"].id)
        .values(ends_at=now())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert client.get(f"{URL}/manuscripts/{mid}").status_code == 404
    replay = client.post(URL + "/chat", json=body)
    assert replay.status_code in {403, 404}, replay.text
    assert "保密稿件内容" not in replay.text


def test_full_human_form_values_survive_ai_candidates_including_unchanged_defaults(
    client, login, scripted_provider
):
    login("author")
    data = fill(client, draft(client))
    human_data = data["version"]["data"]
    assert human_data["language"] == "zh"
    scripted_provider(
        [
            [
                call(
                    "propose_intake",
                    {"candidates": {"title": "模型另写的标题", "language": "en"}},
                )
            ],
            [respond()],
        ]
    )
    response = post_chat(client, "整理提供的资料，保留我已经填写的内容", data["id"])
    assert response.status_code == 200, response.text
    saved = detail(client, data["id"])["version"]["data"]
    assert saved["title"] == human_data["title"]
    assert saved["language"] == human_data["language"]
    assert saved["declarations"] == human_data["declarations"]
    assert saved["authors"] == human_data["authors"]


def test_no_existing_manuscript_row_lock_is_held_during_provider_network(
    client, login, db, scripted_provider
):
    login("author")
    created = draft(client)
    locks = []
    connection = db.connection()

    def observe(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement.upper() and "manuscripts" in statement:
            locks.append(statement)

    def network(messages, tools):
        assert locks == [], "Existing manuscript was row-locked before supplier network"
        return [respond()]

    event.listen(connection, "before_cursor_execute", observe)
    try:
        scripted_provider([network])
        response = post_chat(client, "当前稿件进展到哪一步？", created["manuscript_id"])
        assert response.status_code == 200, response.text
        assert locks, "Post-network revision/permission check must lock the read manuscript"
        assert (
            db.scalar(
                select(func.count())
                .select_from(HumanConfirmation)
                .where(HumanConfirmation.manuscript_id == created["manuscript_id"])
            )
            == 0
        )
    finally:
        event.remove(connection, "before_cursor_execute", observe)
