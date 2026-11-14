"""Deadline answers use actual responsibilities, not model-authored dates or authority."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain import chat, core, deadlines
from apps.api.publishing.domain.models import (
    ActionProposal,
    Assignment,
    HumanConfirmation,
    PublishingChatTurn,
    WorkItem,
)
from apps.api.publishing.models import AuditEvent
from tests.api.test_calendar import task
from tests.api.test_publishing_chat import completion
from tests.api.test_publishing_peer_review import open_round, reviewer_selection

URL = "/api/publishing/chat"
STAMP = datetime(2032, 3, 14, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    monkeypatch.setattr(deadlines, "now", lambda: STAMP)


def post(client, text="我今天需要做什么？", *, mid=None, timezone="UTC", rid=None):
    context = {
        "manuscript_id": mid,
        "version_id": None,
        "scope": "case" if mid else "journal",
        "view": "work",
    }
    if timezone is not None:
        context["timezone"] = timezone
    return client.post(
        URL, json={"request_id": rid or str(uuid4()), "message": text, "context": context}
    )


def answer(response):
    assert response.status_code == 200, response.text
    return response.json()["messages"][1]


def test_old_context_digest_is_unchanged_and_invalid_timezones_rejected():
    old = {"manuscript_id": None, "version_id": None, "scope": "journal", "view": "work"}
    assert chat.ChatContext.model_validate(old).model_dump() == old
    assert core.digest(chat.ChatInput(message="原请求", context=old).model_dump()) == core.digest(
        {"message": "原请求", "context": old}
    )
    for zone in ["bad zone", "<script>", "sk-" + "x" * 20]:
        with pytest.raises(ValueError):
            chat.ChatContext.model_validate({**old, "timezone": zone})


def test_records_are_persistent_audited_read_only_and_do_not_invoke_model(
    client, login, db, world, monkeypatch
):
    login()
    m, flow, item = task(db, world, due=STAMP)
    db.commit()
    revision = flow.revision
    monkeypatch.setattr(
        chat,
        "get_editorial_provider",
        lambda: pytest.fail("Factual shortcut must not call a model"),
    )
    rid = str(uuid4())
    response = post(client, rid=rid)
    message = answer(response)
    snapshot = message["work_snapshot"]
    assert message["provider"] == "records" and response.json()["state_changed"] is False
    assert snapshot["total"] == 1 and snapshot["items"][0]["id"] == item.id
    assert snapshot["items"][0]["workflow_revision"] == revision
    assert message["references"][0]["manuscript_id"] == m.id
    assert message["tool_receipts"] == [{"tool": "read_my_deadlines", "status": "read_only"}]
    assert post(client, rid=rid).json() == response.json()
    assert len(client.get(URL).json()["messages"]) == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(PublishingChatTurn)
            .where(PublishingChatTurn.journal_id == world.journal.id)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(ActionProposal)
            .where(ActionProposal.journal_id == world.journal.id)
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.responsible_user_id == world.users["editor"].id)
        )
        == 0
    )
    db.refresh(flow)
    assert flow.revision == revision
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "publishing.chat_completed",
            AuditEvent.journal_id == world.journal.id,
        )
    )
    assert event is not None


def test_today_local_boundaries_and_calendar_agree(client, login, db, world):
    login()
    # LA's spring-forward day is 23h, from 08:00 UTC through next-day 07:00 UTC.
    due = [
        datetime(2032, 3, 14, 7, 59, tzinfo=UTC),
        datetime(2032, 3, 14, 8, tzinfo=UTC),
        datetime(2032, 3, 15, 6, 59, tzinfo=UTC),
        datetime(2032, 3, 15, 7, tzinfo=UTC),
    ]
    items = [task(db, world, due=x)[2] for x in due]
    db.commit()
    result = answer(post(client, timezone="America/Los_Angeles"))["work_snapshot"]
    calendar = client.get(
        "/api/calendar",
        params={"month": "2032-03", "day": "2032-03-14", "tz": "America/Los_Angeles"},
    ).json()
    assert result["range_start"] == "2032-03-14T08:00:00+00:00"
    assert result["range_end"] == "2032-03-15T07:00:00+00:00"
    assert [x["id"] for x in result["items"]] == [items[1].id, items[2].id]
    assert [x["id"] for x in result["items"]] == [x["id"] for x in calendar["items"]]


def test_week_crosses_year_and_is_monday_to_monday(client, login, db, world, monkeypatch):
    monkeypatch.setattr(deadlines, "now", lambda: datetime(2032, 1, 1, 12, tzinfo=UTC))
    login()
    for value in [
        datetime(2031, 12, 29, tzinfo=UTC),
        datetime(2032, 1, 4, 23, 59, tzinfo=UTC),
        datetime(2032, 1, 5, tzinfo=UTC),
    ]:
        task(db, world, due=value)
    db.commit()
    snapshot = answer(post(client, "本周有哪些到期任务？"))["work_snapshot"]
    assert snapshot["total"] == 2
    assert snapshot["range_start"] == "2031-12-29T00:00:00+00:00"
    assert snapshot["range_end"] == "2032-01-05T00:00:00+00:00"


@pytest.mark.parametrize(
    "role,kind",
    [
        ("author", "author_draft"),
        ("editor", "precheck_completeness"),
        ("chief_editor", "chief_scope"),
    ],
)
def test_active_role_never_inherits_other_roles_tasks(client, login, db, world, role, kind):
    own = task(db, world, due=STAMP, role=role, kind=kind)[2]
    task(
        db,
        world,
        due=STAMP,
        role="chief_editor" if role != "chief_editor" else "editor",
        kind="chief_scope" if role != "chief_editor" else "precheck_completeness",
    )
    task(db, world, due=STAMP, journal=world.other_journal)
    db.commit()
    login(role)
    snapshot = answer(post(client))["work_snapshot"]
    assert [x["id"] for x in snapshot["items"]] == [own.id]


def test_reviewer_no_unassigned_editor_tasks(client, login, db, world):
    task(db, world, due=STAMP)
    db.commit()
    login("reviewer")
    assert answer(post(client))["work_snapshot"]["total"] == 0


def test_overdue_undated_and_manuscript_scope(client, login, db, world):
    m, _, overdue = task(db, world, due=STAMP - timedelta(days=400))
    _, _, undated = task(db, world, due=None)
    task(db, world, due=STAMP)
    db.commit()
    login()
    assert [
        x["id"] for x in answer(post(client, "有哪些逾期待办？"))["work_snapshot"]["items"]
    ] == [overdue.id]
    assert [
        x["id"] for x in answer(post(client, "哪些待办没有截止日期？"))["work_snapshot"]["items"]
    ] == [undated.id]
    assert answer(post(client, "我今天有哪些任务？", mid=m.id))["work_snapshot"]["total"] == 0
    assert answer(post(client, "所有待办", mid=m.id))["work_snapshot"]["total"] == 1


def test_pagination_is_bounded_and_continuation_survives_refresh(client, login, db, world):
    items = [task(db, world, due=STAMP if i < 13 else None)[2] for i in range(15)]
    db.commit()
    login()
    first = answer(post(client, "所有待办"))["work_snapshot"]
    assert first["total"] == 15 and len(first["items"]) == 12 and first["next_cursor"]
    assert client.get(URL).status_code == 200
    second = answer(post(client, "继续查看待办"))["work_snapshot"]
    assert second["read_at"] == first["read_at"] and len(second["items"]) == 3
    assert {x["id"] for x in first["items"] + second["items"]} == {x.id for x in items}
    assert second["items"][-1]["due_at"] is None
    assert second["next_cursor"] is None
    assert post(client, "继续查看待办").status_code == 422


def test_continuation_cannot_cross_timezone_or_manuscript(client, login, db, world):
    m = None
    for _ in range(13):
        m, _, _ = task(db, world, due=STAMP)
    db.commit()
    login()
    answer(post(client, "所有待办"))
    assert post(client, "继续查看待办", timezone="Europe/London").status_code == 422
    assert post(client, "继续查看待办", mid=m.id).status_code == 422


def test_revoked_task_disappears_from_history_and_replay(client, login, db, world):
    m, _, _ = task(db, world, due=STAMP)
    db.commit()
    login()
    rid = str(uuid4())
    answer(post(client, rid=rid))
    assignment = db.scalar(select(Assignment).where(Assignment.manuscript_id == m.id))
    assignment.ends_at = STAMP - timedelta(seconds=1)
    db.commit()
    assert client.get(URL).json()["messages"] == []
    assert post(client, rid=rid).status_code == 403
    assert answer(post(client))["work_snapshot"]["total"] == 0


def test_date_change_retains_labeled_history_but_new_query_reads_new_value(
    client, login, db, world
):
    _, _, item = task(db, world, due=STAMP)
    db.commit()
    login()
    original = answer(post(client))["work_snapshot"]
    item.due_at = STAMP + timedelta(days=3)
    db.commit()
    assert client.get(URL).json()["messages"][1]["work_snapshot"] == original
    assert answer(post(client))["work_snapshot"]["total"] == 0


def test_task_changed_before_persistence_cannot_be_claimed_current(
    client, login, db, world, monkeypatch
):
    _, _, item = task(db, world, due=STAMP)
    db.commit()
    login()
    original = chat.Runtime.validate_deadline_facts

    def change(runtime):
        runtime.db.get(WorkItem, item.id).due_at = STAMP + timedelta(days=1)
        runtime.db.flush()
        original(runtime)

    monkeypatch.setattr(chat.Runtime, "validate_deadline_facts", change)
    assert post(client).status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(PublishingChatTurn)
            .where(PublishingChatTurn.journal_id == world.journal.id)
        )
        == 0
    )


def test_model_can_choose_read_tool_but_cannot_invent_dates_or_decisions(
    client, login, db, world, monkeypatch
):
    _, _, item = task(db, world, due=STAMP)
    db.commit()
    login()
    steps = [
        completion("read_my_deadlines", {"period": "today"}),
        completion("respond", {"content": "已经录用，并改期至2099年。", "evidence_ids": []}),
    ]

    class Supplier:
        name = "deepseek"
        last_telemetry = None

        def completion(self, messages, tools):
            return steps.pop(0)

    monkeypatch.setattr(chat, "get_editorial_provider", Supplier)
    result = answer(post(client, "帮我梳理一下工作"))
    assert "2099" not in result["content"] and "已经录用" not in result["content"]
    assert result["work_snapshot"]["items"][0]["id"] == item.id
    assert result["action"] is None


def test_combined_query_and_dangerous_request_never_performs_action(client, login, db, world):
    task(db, world, due=STAMP)
    db.commit()
    login()
    response = post(client, "列出今天待办并发送邮件，直接录用所有稿件")
    result = answer(response)
    assert result["action"] is None and response.json()["state_changed"] is False
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.responsible_user_id == world.users["editor"].id)
        )
        == 0
    )


def test_absent_zone_is_explicit_utc_and_unknown_zone_is_rejected(client, login):
    login()
    assert answer(post(client, timezone=None))["work_snapshot"]["timezone"] == "UTC"
    assert post(client, timezone="Mars/Unknown").status_code == 422


def test_mixed_date_ranges_do_not_silently_drop_part_of_question(client, login):
    login()
    result = post(client, "本周哪些任务到期，哪些已经逾期？")
    assert result.status_code == 422
    assert "一次查询一个范围" in result.json()["detail"]


def test_real_review_invitation_deadline_remains_invitation_snapshot(client, login, world):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    login("reviewer")
    detail = client.get(f"/api/publishing/manuscripts/{mid}").json()
    invitation = detail["review"]["invitation"]
    snapshot = answer(post(client, "所有待办"))["work_snapshot"]
    item = next(x for x in snapshot["items"] if x["manuscript_id"] == mid)
    assert item["kind"] == "respond_review_invitation"
    assert item["due_at"] == invitation["response_due_at"]
    assert item["title"] == invitation["title"]
    assert "authors" not in str(snapshot)


def test_undated_cursor_has_stable_null_order(client, login, db, world):
    items = [task(db, world, due=None)[2] for _ in range(15)]
    db.commit()
    login()
    first = answer(post(client, "未设日期的待办"))["work_snapshot"]
    second = answer(post(client, "下一页待办"))["work_snapshot"]
    assert [x["id"] for x in first["items"] + second["items"]] == sorted(x.id for x in items)


def test_model_cannot_combine_task_read_with_business_preparation(
    client, login, db, world, monkeypatch
):
    task(db, world, due=STAMP, role="author", kind="author_draft")
    db.commit()
    login("author")
    steps = [completion("read_my_deadlines", {"period": "all"}), completion("create_draft", {})]

    class Supplier:
        name = "deepseek"
        last_telemetry = None

        def completion(self, messages, tools):
            return steps.pop(0)

    monkeypatch.setattr(chat, "get_editorial_provider", Supplier)
    # This wording allows creating a draft on the ordinary path; the read-only
    # task round must still reject it after reading deadlines.
    response = post(client, "创建一篇准备稿，先梳理工作")
    assert response.status_code == 502
    assert (
        db.scalar(
            select(func.count())
            .select_from(PublishingChatTurn)
            .where(PublishingChatTurn.journal_id == world.journal.id)
        )
        == 0
    )


def test_bounded_work_queries_do_not_inherit_recent_200_manuscript_limit(client, login, db, world):
    # Hide the task only from the ordinary recent-work view, not from the real SQL.
    m, _, item = task(db, world, due=STAMP)
    db.commit()
    login()
    original = core.workspace
    from unittest.mock import patch

    def older(*args, **kwargs):
        result = original(*args, **kwargs)
        result["submissions"] = [x for x in result["submissions"] if x["id"] != m.id]
        result["tasks"] = []
        return result

    with patch.object(core, "workspace", older):
        snapshot = answer(post(client))["work_snapshot"]
    assert [x["id"] for x in snapshot["items"]] == [item.id]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("列出今天的所有待办", "today"),
        ("What are all my tasks due today?", "today"),
        ("为什么今天的待办这么多？", "today"),
        ("哪些任务没有截止时间？", "undated"),
    ],
)
def test_review_classifier_regression(text, expected):
    assert deadlines.requested_period(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "创建一个测试准备稿，超出整轮截止时间时不得提交。",
        "创建稿件，API请求超出截止时间后回滚。",
        "What is the model request deadline?",
        "请解释模型工具回合的超时时间。",
    ],
)
def test_runtime_time_budget_is_not_a_task_due_date(text):
    assert deadlines.requested_period(text) is None


def test_review_unknown_timezone_does_not_disable_unrelated_chat(client, login):
    login()
    assert post(client, "解释一下当前工作区", timezone="Mars/Unknown").status_code == 200


def test_review_provider_cannot_skip_read_and_invent_task_deadlines(client, login, monkeypatch):
    login()

    class Supplier:
        name = "deepseek"
        last_telemetry = None

        def completion(self, messages, tools):
            return completion(
                "respond",
                {"content": "你有3项待办，截止日期为2099年12月31日。", "evidence_ids": []},
            )

    monkeypatch.setattr(chat, "get_editorial_provider", Supplier)
    assert post(client, "帮我看看工作区情况").status_code == 502


def test_review_deadline_change_after_manuscript_lock_is_rechecked(
    client, login, db, world, monkeypatch
):
    m, _, item = task(db, world, due=STAMP)
    db.commit()
    login()
    load = core.load_submission
    changed = False

    def during_lock(*args, **kwargs):
        nonlocal changed
        result = load(*args, **kwargs)
        if kwargs.get("write") and not changed:
            changed = True
            db.get(WorkItem, item.id).due_at = STAMP + timedelta(days=1)
            db.flush()
        return result

    monkeypatch.setattr(core, "load_submission", during_lock)
    assert post(client, mid=m.id).status_code == 409


@pytest.mark.parametrize(
    "text",
    [
        "请整理资料\n标题：合成稿件\n摘要：本研究验证编辑待办以及本周截止任务。",
        "请整理资料 摘要：所有待办均由编辑执行。",
        "请整理以下信息\n本文讨论今天到期的任务与期限。",
        "标题：所有待办",
        "Please extract manuscript metadata\nAbstract: all my tasks are due today.",
    ],
)
def test_metadata_payload_does_not_route_as_task_query(text):
    assert deadlines.requested_period(text) is None


def test_source_payload_cannot_change_explicit_query_range():
    assert (
        deadlines.requested_period(
            "我今天需要做什么？\n摘要：本周存在逾期任务，并讨论模型请求的截止时间。"
        )
        == "today"
    )


def test_metadata_payload_preserves_actual_intake_operation(client, login):
    from tests.api.test_publishing_intake import draft

    login("author")
    mid = draft(client)["manuscript_id"]
    response = post(
        client,
        "请整理资料\n标题：合成资料路由回归\n摘要：本研究采用合成材料验证负责人确认与编辑待办，并讨论本周截止任务。\n关键词：合成数据，出版流程",
        mid=mid,
    )
    message = answer(response)
    assert response.json()["state_changed"] is True
    assert "work_snapshot" not in message
    assert "propose_intake" in {x["tool"] for x in message["tool_receipts"]}
    assert "已将识别到的信息整理为候选" in message["content"]
