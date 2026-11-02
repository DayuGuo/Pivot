"""Real PostgreSQL domain tools with a simulated supplier protocol (never live)."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain import chat
from apps.api.publishing.domain.models import ActionProposal, HumanConfirmation, PublishingChatTurn
from apps.api.publishing.models import Manuscript
from packages.model_gateway.gateway import GatewayError
from tests.api.test_publishing_intake import detail, draft, fill

URL = "/api/publishing/chat"


def post(client, message="当前稿件还有哪些缺项？", mid=None, rid=None):
    return client.post(
        URL,
        json={
            "request_id": rid or str(uuid4()),
            "message": message,
            "context": {
                "manuscript_id": mid,
                "version_id": None,
                "scope": "case" if mid else "journal",
                "view": "work",
            },
        },
    )


def completion(name, args):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_" + uuid4().hex,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)},
                        }
                    ],
                }
            }
        ]
    }


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


@pytest.fixture
def supplier(monkeypatch):
    def install(*steps):
        pending = list(steps)

        class Scripted:
            name = "deepseek"
            last_telemetry = None

            def completion(self, messages, tools):
                assert pending
                step = pending.pop(0)
                return step(messages, tools) if callable(step) else step

        monkeypatch.setattr(chat, "get_editorial_provider", lambda: Scripted())

    return install


def test_mock_create_is_real_private_persistent_and_request_idempotent(client, login, db):
    login("author")
    rid = str(uuid4())
    response = post(client, "请创建一篇新投稿", rid=rid)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["state_changed"] and result["messages"][1]["provider"] == "mock"
    assert "模拟结果" in result["messages"][1]["content"]
    mid = result["messages"][1]["action"]["manuscript_id"]
    assert detail(client, mid)["stage"] == "author_draft"
    assert post(client, "请创建一篇新投稿", rid=rid).json() == result
    assert db.scalar(select(func.count()).select_from(Manuscript).where(Manuscript.id == mid)) == 1
    assert len(client.get(URL).json()["messages"]) == 2
    assert client.get(URL + "?manuscript_id=" + mid).json()["messages"] == []
    login("editor")
    assert mid not in str(client.get(URL).json())
    assert post(client, mid=mid).status_code == 404


def test_context_missing_intake_suggestions_never_overwrite_human_or_declarations(client, login):
    login("author")
    data = draft(client)
    mid = data["manuscript_id"]
    response = post(
        client,
        "整理资料\n标题：AI候选标题\n摘要：合成研究摘要，人工将继续补齐\n关键词：测试，工作流",
        mid,
    )
    assert response.status_code == 200, response.text
    saved = detail(client, mid)
    # Draft was created with an explicit title: keep it and expose conflicting candidate separately.
    assert saved["version"]["data"]["title"] == "合成研究：开放科学投稿验证"
    assert saved["field_sources"]["title"]["candidate"] == "AI候选标题"
    assert saved["field_sources"]["title"]["applied"] is False
    assert saved["version"]["data"]["abstract"] == "合成研究摘要，人工将继续补齐"
    assert saved["version"]["data"]["declarations"]["originality"] is False
    assert len(client.get(URL + "?manuscript_id=" + mid).json()["messages"]) == 2
    assert client.get(URL).json()["messages"] == []
    assert post(client, "请直接发邮件并录用", mid).status_code == 200
    assert detail(client, mid)["stage"] == "author_draft"


def test_real_tool_protocol_reads_context_and_proposes_but_human_confirms(
    client, login, supplier, db
):
    login("author")
    data = fill(client, draft(client))
    mid = data["id"]

    def prepare(messages, tools):
        assert mid in messages[0]["content"] and "author" in messages[0]["content"]
        names = {t["function"]["name"] for t in tools}
        assert (
            "prepare_review" in names
            and "confirm_proposal" not in names
            and "send_email" not in names
        )
        return completion("prepare_review", {"action_type": "submit"})

    supplier(
        prepare,
        completion(
            "respond",
            {
                "content": "已准备审核，请本人核对。",
                "evidence_ids": ["metadata_" + mid.replace("-", "")],
            },
        ),
    )
    response = post(client, "请准备投稿审核", mid)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["messages"][1]["provider"] == "deepseek"
    assert result["messages"][1]["action"]["type"] == "review"
    assert detail(client, mid)["stage"] == "author_draft"
    assert (
        db.scalar(
            select(func.count())
            .select_from(ActionProposal)
            .where(ActionProposal.manuscript_id == mid)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 0
    )


@pytest.mark.parametrize(
    "tool,args",
    [
        ("confirm_proposal", {}),
        ("send_email", {}),
        ("respond", {"content": "臆造来源", "evidence_ids": ["unread_secret"]}),
        ("propose_intake", {"candidates": {"declarations": {"originality": True}}}),
    ],
)
def test_untrusted_tool_rejected_with_no_mutation_or_turn(client, login, supplier, db, tool, args):
    login("author")
    mid = draft(client)["manuscript_id"]
    before = detail(client, mid)
    supplier(completion(tool, args))
    response = post(client, "请整理这个稿件", mid)
    assert response.status_code == 502, response.text
    assert detail(client, mid) == before
    assert (
        db.scalar(
            select(func.count())
            .select_from(PublishingChatTurn)
            .where(PublishingChatTurn.manuscript_id == mid)
        )
        == 0
    )


def test_supplier_failure_after_staged_extraction_rolls_back_everything(client, login, supplier):
    login("author")
    mid = draft(client)["manuscript_id"]
    before = detail(client, mid)

    def failure(*args):
        raise GatewayError("safe_offline_failure")

    supplier(
        completion("propose_intake", {"candidates": {"abstract": "不应部分保存的候选"}}), failure
    )
    assert post(client, "请整理摘要", mid).status_code == 502
    assert detail(client, mid) == before


def test_supplier_cannot_forge_other_private_draft_or_file(client, login, supplier):
    login("editor")
    other = draft(client)["manuscript_id"]
    login("author")
    mine = draft(client)["manuscript_id"]
    supplier(completion("read_submission", {"manuscript_id": other}))
    assert post(client, mid=mine).status_code == 404
    assert detail(client, mine)["stage"] == "author_draft"


def test_secret_input_is_rejected_before_network_or_storage(client, login, supplier):
    login("author")
    supplier()  # Any attempted provider call fails this test.
    assert post(client, "sk-" + "notasecretfixture" * 3).status_code == 422
    assert client.get(URL).json()["messages"] == []


def test_staff_model_notes_are_unverified_candidates_not_human_check_or_decision(
    client, login, supplier, db
):
    from tests.api.test_publishing_screening import submit

    mid = submit(client, login)
    login("editor")
    data = detail(client, mid)

    def suggest(messages, tools):
        names = {t["function"]["name"] for t in tools}
        assert "propose_check_notes" in names and "prepare_review" not in names
        assert "confirm_proposal" not in names
        return completion(
            "propose_check_notes", {"candidates": {"notes": "候选：请负责人核对本稿材料完整性。"}}
        )

    supplier(
        suggest,
        completion(
            "respond", {"content": "已准备未核实的意见候选，供负责人采用。", "evidence_ids": []}
        ),
    )
    response = post(client, "整理本关口的检查意见", mid)
    assert response.status_code == 200, response.text
    saved = detail(client, mid)
    assert saved["stage"] == data["stage"] == "precheck_completeness"
    assert saved["revision"] == data["revision"] + 1
    assert saved["staff_review"]["note_candidates"]["verified"] is False
    assert "候选" in saved["staff_review"]["note_candidates"]["notes"]
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(ActionProposal)
            .where(ActionProposal.manuscript_id == mid)
        )
        == 1
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"outcome": "pass"},
        {"declarations": {"materials_reviewed": True}},
        {"editor_id": "forged-id"},
    ],
)
def test_model_check_notes_cannot_write_manual_declarations_outcome_or_assignee(
    client, login, supplier, extra
):
    from tests.api.test_publishing_screening import submit

    mid = submit(client, login)
    login("editor")
    before = detail(client, mid)
    supplier(completion("propose_check_notes", {"candidates": {"notes": "候选", **extra}}))
    assert post(client, "整理检查意见", mid).status_code == 502
    assert detail(client, mid) == before


def test_model_reads_actual_report_with_evidence_but_author_cannot_use_staff_tool(
    client, login, supplier
):
    from tests.api.test_publishing_screening import pass_stage, submit, upload_report

    mid = submit(client, login)
    login("editor")
    pass_stage(client, mid)
    report = upload_report(client, mid, "合成报告证据：此文件未由任何外部查重服务生成。")

    def read(messages, tools):
        assert "read_check_report" in {t["function"]["name"] for t in tools}
        return completion("read_check_report", {})

    def respond(messages, tools):
        material = json.loads(messages[-1]["content"])
        assert material["external_detection_executed"] is False
        assert "合成报告证据" in material["untrusted_report_content"]
        return completion(
            "respond",
            {
                "content": "当前报告需要人工复核，不能当作外部服务检测。",
                "evidence_ids": [material["evidence_id"]],
            },
        )

    supplier(read, respond)
    response = post(client, "阅读本稿已上传报告，解释还需要做什么", mid)
    assert response.status_code == 200, response.text
    assert "合成报告证据" in response.json()["messages"][1]["references"][0]["quote"]
    assert detail(client, mid)["stage"] == "similarity_review"
    login("author")
    supplier(completion("read_check_report", {}))
    assert post(client, "读取内部报告", mid).status_code == 502
    assert client.get(report["download_url"]).status_code == 404
