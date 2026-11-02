"""Private persistent contextual Mock turns and allowlisted draft preparation.

No model, network, workflow transition, or mail capability is reachable here.
The response is stored atomically with its request digest before it is returned.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from packages.editorial_demo import load_cases

from .audit import record
from .db import get_db
from .editorial_demo import (
    DemoWorkspaceState,
    Identifier,
    Invitation,
    StatePatch,
    TypedInput,
    case_record,
    default_state,
    editor,
    lock_workspace,
    state_query,
    validated_state,
)
from .models import Base, now, uid
from .security import Actor

router = APIRouter(prefix="/api/editorial-demo/chat", tags=["private contextual mock chat"])
View = Literal["work", "read", "reviewers", "revision"]
Stage = Literal["all", "screening", "assignment", "reviewers", "review", "decision", "production"]


class EditorialChatTurn(Base):
    __tablename__ = "editorial_chat_turns"
    __table_args__ = (
        UniqueConstraint("user_id", "journal_id", "request_id"),
        Index("ix_editorial_chat_history", "user_id", "journal_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    input_digest: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatContext(TypedInput):
    scope: Literal["case", "queue", "journal"]
    case_id: Identifier
    version: Identifier
    view: View
    stage: Stage
    query: str = Field(max_length=200)
    today_only: bool


class ChatInput(TypedInput):
    request_id: Annotated[UUID, Field(strict=False)]
    message: str = Field(min_length=1, max_length=2000)
    context: ChatContext

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请输入问题")
        return value


class Anchor(TypedInput):
    version: Identifier
    section: Identifier
    quote: str
    file: Identifier
    location: str


class ChatReference(TypedInput):
    label: str
    case_id: Identifier
    anchor: Anchor | None = None


class Navigate(TypedInput):
    type: Literal["navigate"] = "navigate"
    view: View
    case_id: Identifier
    prepare: Literal["invitation", "decision"] | None = None


class Filter(TypedInput):
    type: Literal["filter"] = "filter"
    stage: Stage
    today_only: bool
    query: str = Field(max_length=200)


class ChatMessage(TypedInput):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    context: ChatContext
    references: list[ChatReference]
    action: Annotated[Navigate | Filter, Field(discriminator="type")] | None = None


class ChatTurn(TypedInput):
    request_id: str
    messages: list[ChatMessage]
    state_changed: bool
    provider: Literal["mock"] = "mock"


class ChatHistory(TypedInput):
    messages: list[ChatMessage]
    provider: Literal["mock"] = "mock"


def owned_turns(actor: Actor):
    return select(EditorialChatTurn).where(
        EditorialChatTurn.user_id == actor.user.id,
        EditorialChatTurn.journal_id == actor.journal_id,
    )


def validate_context(context: ChatContext) -> dict:
    case = case_record(context.case_id)
    if context.version not in {v["id"] for v in case["versions"]}:
        raise HTTPException(422, "对话上下文版本不存在")
    return case


def scoped_cases(context: ChatContext, cases: list[dict]) -> list[dict]:
    if context.scope == "case":
        return [c for c in cases if c["id"] == context.case_id]
    if context.scope == "journal":
        return cases
    query = context.query.strip().casefold()
    today = now().date().isoformat()
    return [
        c
        for c in cases
        if (context.stage == "all" or c["stage_key"] == context.stage)
        and (not context.today_only or c["due"][:10] <= today)
        and query
        in f"{c['title']} {c['title_en']} {c['number']} {' '.join(c['authors'])} {c['task']}".casefold()
    ]


def current_state(db: Session, actor: Actor, case: dict) -> dict:
    row = db.scalar(state_query(actor, case["id"]))
    return {**row.content, "revision": row.revision} if row else default_state(case)


def navigation(case: dict, view: View) -> Navigate:
    return Navigate(view=view, case_id=case["id"])


def citation(case: dict, version: str, anchor: dict | None = None) -> ChatReference:
    if anchor is None:
        v = next(v for v in case["versions"] if v["id"] == version)
        section = v["sections"][0]
        anchor = {
            "version": version,
            "section": section["id"],
            "quote": section["paragraphs"][0],
            "file": v["original"],
            "location": f"{section['title']} · 第1段",
        }
    return ChatReference(
        label=f"{case['number']} · {anchor['version']} · {anchor['location']}",
        case_id=case["id"],
        anchor=Anchor.model_validate(anchor),
    )


def validate_outputs(references: list[ChatReference], action: Navigate | Filter | None) -> None:
    """Revalidate all generated references against exact permitted fixture content."""
    for reference in references:
        case = case_record(reference.case_id)
        if reference.anchor is None:
            continue
        anchor = reference.anchor
        version = next((v for v in case["versions"] if v["id"] == anchor.version), None)
        section = (
            next((s for s in version["sections"] if s["id"] == anchor.section), None)
            if version
            else None
        )
        file = next((f for f in case["attachments"] if f["id"] == anchor.file), None)
        if (
            not section
            or not file
            or file["version"] != anchor.version
            or anchor.quote not in section["paragraphs"]
            or anchor.quote not in file["content"]
        ):
            raise HTTPException(422, "对话引用必须指向已有版本与原文")
    if isinstance(action, Navigate):
        case_record(action.case_id)


def prepare_invitation(db: Session, actor: Actor, case: dict, version: str):
    # Same lock, typed validator, private ownership and audit as the existing state gateway.
    lock_workspace(db, actor, case["id"])
    row = db.scalar(state_query(actor, case["id"]).with_for_update())
    state = {**row.content, "revision": row.revision} if row else default_state(case)
    selected = [c for c in case["candidates"] if c["id"] in state["selected_reviewers"]]
    if not selected:
        return "请先在候选人页面选择审稿人，再准备邀请草稿；不会替你选择或联系候选人。", False
    recipients = ", ".join(c["email"] for c in selected)
    existing = state["invitation"]
    selected_addresses = {candidate["email"] for candidate in selected}
    stored_addresses = {address.strip() for address in existing["to"].split(",") if address.strip()}
    # Selecting a candidate fills only recipient metadata in the UI. It is not a
    # written letter; preserve those recipients while preparing the empty body.
    if any(existing[key] for key in ("subject", "body", "due")) or (
        stored_addresses and stored_addresses != selected_addresses
    ):
        return "已有邀请草稿，已保留全部人工内容。请在候选人页面继续检查。", False
    invitation = Invitation(
        to=existing["to"] or recipients,
        subject=f"[合成邀请草稿] {case['number']} · {version}",
        body=(
            f"您好：\n邀请您评阅合成稿件《{case['title']}》（{case['number']}，{version}）。\n"
            "请人工核对研究方向、利益冲突、评审期限与完整正文。\n"
            "这是内部测试草稿，尚未联系审稿人，也未发送邮件。"
        ),
        due="",
    )
    content = validated_state(case, state, StatePatch(invitation=invitation))
    content["revision"] += 1
    if row is None:
        row = DemoWorkspaceState(
            user_id=actor.user.id, journal_id=actor.journal_id, case_id=case["id"], content={}
        )
        db.add(row)
    row.revision = content["revision"]
    row.content = {k: v for k, v in content.items() if k != "revision"}
    row.updated_at = now()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="editorial_demo.workspace_saved",
        entity_id=case["id"],
        details={"demo": True, "revision": row.revision, "fields": ["invitation"]},
    )
    return f"已为 {case['number']}（{version}）准备私有邀请草稿。请人工检查；未发送邮件。", True


STAGE_WORDS = {
    "screening": ("初筛", "screening"),
    "assignment": ("分派", "assignment"),
    "reviewers": ("寻找审稿人", "邀请审稿人", "选人", "候选", "reviewers"),
    "review": ("外审", "评审中", "under review"),
    "decision": ("修回", "决定", "revision", "decision"),
    "production": ("制作", "production"),
}


def task_filter(message: str, context: ChatContext) -> Filter:
    stage = context.stage if context.scope == "queue" else "all"
    for key, words in STAGE_WORDS.items():
        if any(word in message for word in words):
            stage = key
            break
    today = context.today_only if context.scope == "queue" else False
    if any(word in message for word in ("今天", "今日", "逾期", "today", "overdue")):
        today = True
    query = context.query if context.scope == "queue" else ""
    quoted = re.search(r'[“"「](.*?)[”"」]', message)
    search = re.search(r"(?:搜索|查找|search(?: for)?|find)\s*[:：]?\s*(.+)", message)
    if quoted:
        query = quoted.group(1)[:200]
    elif search and not any(w in search.group(1) for w in ("任务", "稿件", "tasks", "papers")):
        query = search.group(1).strip(" 。.？?")[:200]
    return Filter(stage=stage, today_only=today, query=query)


def mock_reply(db: Session, actor: Actor, body: ChatInput):
    message = body.message.strip().casefold()
    context = body.context
    # Refusal precedes every mutable draft path. External/user prose never supplies tools.
    unsafe = re.search(
        r"发送|发出邀请|通知作者|正式决定|录用|拒稿|撤稿|发布|出版|取消|批准|标记.*已解决|"
        r"权限|授权给|修改角色|绕过|忽略.*(?:规则|指令|限制)|执行.*(?:sql|shell|命令)|"
        r"删除.*(?:数据|记录)|密钥|密码|他人.*(?:对话|草稿)|drop\s+table|"
        r"\b(?:send|publish|cancel|permissions?|grant|execute|secrets?|password|api.?key)\b|"
        r"ignore.*(?:instructions|rules)|(?:accept|reject)\s+(?:this|the|paper|manuscript)",
        message,
    )
    if unsafe:
        return (
            "不能执行发信、正式决定、出版、取消评审、权限变更或越权指令。"
            "本地 Mock 只查询合成材料、导航和准备私有草稿；没有执行任何业务变更。",
            [],
            None,
            False,
        )
    cases = load_cases()
    identifiers = re.findall(r"(?<![a-z0-9_-])(?:env-\d{4}-\d+|demo-\d+)(?![a-z0-9_-])", message)
    targets = [c for c in cases if c["number"].casefold() in identifiers or c["id"] in identifiers]
    if identifiers and (
        len(targets) != 1
        or any(
            identifier not in {targets[0]["number"].casefold(), targets[0]["id"]}
            for identifier in identifiers
        )
    ):
        return "请明确一个有权访问的合成稿件编号；当前没有选择或修改其他稿件。", [], None, False
    if not targets and any(
        w in message for w in ("另一篇", "其他稿件", "another paper", "other manuscript")
    ):
        return "请明确目标稿件编号；不能把另一篇稿件的操作应用到当前稿件。", [], None, False
    target = targets[0] if targets else None
    scope = [target] if target else scoped_cases(context, cases)
    case = target or (scope[0] if context.scope == "case" else None)
    version = (
        context.version
        if case and case["id"] == context.case_id
        else case["versions"][-1]["id"]
        if case
        else None
    )
    preparing = any(w in message for w in ("准备", "起草", "草稿", "draft", "prepare"))
    invitation = any(w in message for w in ("邀请", "invitation", "invite"))
    decision = any(w in message for w in ("决定", "decision", "录用", "拒稿"))
    if preparing and (invitation or decision):
        # A named, unrecognised recipient manuscript must not fall back to the open paper.
        # Numbers are the deterministic target language; vague names require clarification.
        named_target = re.search(r"(?:为|给|替)(.+?)(?:准备|起草|撰写|生成)", message)
        english_target = re.search(r"\bfor\s+(.+?)(?:[.?!。？！]|$)", message)
        target_text = (
            named_target.group(1).strip()
            if named_target
            else (english_target.group(1).strip() if english_target else None)
        )
        if (
            not target
            and target_text
            and target_text
            not in {
                "我",
                "已选审稿人",
                "选中的审稿人",
                "所选审稿人",
                "当前选中的审稿人",
                "已选候选人",
                "the selected reviewers",
                "selected reviewers",
                "当前稿件",
                "这篇稿件",
                "本稿件",
                "这篇",
                "当前这篇",
                "当前这篇稿件",
                "this paper",
                "this manuscript",
                "the current paper",
                "the current manuscript",
                "me",
            }
        ):
            return "请写出目标稿件编号；没有把未明确的稿件操作应用到当前稿件。", [], None, False
        if case is None:
            return "请先选定一篇稿件，或在问题中写出稿件编号，再准备私有草稿。", [], None, False
        if invitation:
            text, changed = prepare_invitation(db, actor, case, version)
            action = navigation(case, "reviewers")
            if changed or any(current_state(db, actor, case)["invitation"].values()):
                action.prepare = "invitation"
            return text, [citation(case, version)], action, changed
        return (
            f"可以打开 {case['number']} 的决定草稿页。请人工选择结果并撰写理由；"
            "我未选择录用、修回或拒稿结论，也未发布决定。",
            [citation(case, version)],
            Navigate(view="revision", case_id=case["id"], prepare="decision"),
            False,
        )
    task_intent = any(
        w in message
        for w in (
            "任务",
            "待办",
            "队列",
            "搜索",
            "查找",
            "筛选",
            "今天",
            "逾期",
            "tasks",
            "queue",
            "search",
            "find",
            "today",
        )
    )
    if task_intent:
        filters = task_filter(message, context)
        if target or context.scope == "case":
            found = scope
            action = navigation(case, "read") if case else None
        else:
            effective = ChatContext(
                **{**context.model_dump(), "scope": "queue", **filters.model_dump(exclude={"type"})}
            )
            found = scoped_cases(effective, cases)
            action = filters
        found = sorted(found, key=lambda c: (c["due"], c["number"]))
        text = (
            "\n".join(
                f"{c['number']} · {c['title']}\n{c['stage']}；{c['task']}；负责人：{c['owner']}；到期 {c['due']}。"
                for c in found
            )
            or "当前范围内没有匹配的合成任务。"
        )
        return (
            text,
            [ChatReference(label=c["number"], case_id=c["id"]) for c in found],
            action,
            False,
        )
    issue_intent = any(
        w in message for w in ("问题", "证据", "核验", "未解决", "issue", "evidence", "unresolved")
    )
    candidate_intent = any(
        w in message for w in ("候选", "审稿人", "评审", "reviewer", "candidate", "review progress")
    )
    status_intent = any(
        w in message for w in ("状态", "进度", "阶段", "哪一步", "status", "progress", "stage")
    )
    if case is None and (issue_intent or candidate_intent):
        return (
            "当前范围包含多篇稿件。请写出稿件编号，或进入稿件范围查看具体证据与候选人。",
            [ChatReference(label=c["number"], case_id=c["id"]) for c in scope],
            None,
            False,
        )
    if issue_intent and case:
        state = current_state(db, actor, case)
        items = [
            (issue, anchor)
            for issue in case["issues"]
            if state["issue_statuses"].get(issue["id"], issue["initial_status"])
            not in {"resolved", "ignored"}
            for anchor in [
                next(
                    (a for a in (issue["after"], issue["before"]) if a["version"] == version), None
                )
            ]
            if anchor is not None
        ]
        labels = {"unanswered": "待回复", "unverified": "已回复待核验"}
        text = f"{case['number']} · {version} 的未解决问题：\n" + (
            "\n".join(
                f"{issue['title']}（{labels.get(state['issue_statuses'].get(issue['id'], issue['initial_status']), '待核验')}）："
                f"{issue['comment']}\n原文：{anchor['quote']}"
                for issue, anchor in items
            )
            or "此版本没有对应的未解决问题证据；这不代表已通过人工审核。"
        )
        return (
            text,
            [citation(case, version, anchor) for _, anchor in items],
            navigation(case, "revision"),
            False,
        )
    if candidate_intent and case:
        state = current_state(db, actor, case)
        text = f"{case['number']} 的合成候选人与评审记录：\n" + "\n".join(
            f"{c['name']} · {c['affiliation']} · {'、'.join(c['topics'])}；{c['availability']}；"
            f"利益冲突：{c['conflict']}。{'已选入私有草稿' if c['id'] in state['selected_reviewers'] else '未选择'}。"
            for c in case["candidates"]
        )
        tasks = [
            f"{r['label']}：{t['reviewer']} {t['status']}（到期 {t['due']}）"
            for r in case["rounds"]
            for t in r["tasks"]
        ]
        text += "\n" + ("\n".join(tasks) or "尚无已邀请的评审任务。")
        text += "\n仅为合成情景，未实际联系、核实身份或发送邀请。"
        return (
            text,
            [ChatReference(label=f"{case['number']} · 合成候选与轮次", case_id=case["id"])],
            navigation(case, "reviewers"),
            False,
        )
    if status_intent:
        text = (
            "\n".join(
                f"{c['number']} · {c['title']}：当前为{c['stage']}，负责人：{c['owner']}；"
                f"下一项工作：{c['task']}；到期 {c['due']}。"
                + (
                    f" 本次阅读版本为 {version}，最新版本为 {c['versions'][-1]['id']}。"
                    if case
                    else ""
                )
                for c in scope
            )
            or "当前范围内没有匹配的合成稿件。"
        )
        return (
            text,
            [citation(c, version if case else c["versions"][-1]["id"]) for c in scope],
            None,
            False,
        )
    return (
        "这是确定性的本地 Mock，不能分析任意问题。可以询问当前范围的稿件状态、任务搜索、"
        "未解决问题与原文、候选审稿人，或为明确稿件准备邀请／决定草稿。",
        [],
        None,
        False,
    )


@router.get("", response_model=ChatHistory, response_model_exclude_none=True)
def history(actor: Actor = Depends(editor), db: Session = Depends(get_db)):
    rows = db.scalars(
        owned_turns(actor)
        .order_by(EditorialChatTurn.created_at.desc(), EditorialChatTurn.id.desc())
        .limit(50)
    ).all()
    return ChatHistory(messages=[m for row in reversed(rows) for m in row.response["messages"]])


@router.post("", response_model=ChatTurn, response_model_exclude_none=True)
def chat(body: ChatInput, actor: Actor = Depends(editor), db: Session = Depends(get_db)):
    digest = hashlib.sha256(
        json.dumps(
            {"message": body.message, "context": body.context.model_dump()},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    # All actor turns serialize so chronological history remains deterministic, as do retries.
    lock_workspace(db, actor, "chat-turns")
    existing = db.scalar(
        owned_turns(actor).where(EditorialChatTurn.request_id == str(body.request_id))
    )
    if existing:
        if existing.input_digest != digest:
            raise HTTPException(409, "请求编号已用于不同的问题或上下文")
        return ChatTurn.model_validate(existing.response)
    validate_context(body.context)
    content, references, action, changed = mock_reply(db, actor, body)
    validate_outputs(references, action)
    timestamp = now()
    messages = [
        ChatMessage(
            id=uid(),
            role="user",
            content=body.message,
            created_at=timestamp.isoformat(),
            context=body.context,
            references=[],
        ),
        ChatMessage(
            id=uid(),
            role="assistant",
            content=content,
            created_at=timestamp.isoformat(),
            context=body.context,
            references=references,
            action=action,
        ),
    ]
    result = ChatTurn(request_id=str(body.request_id), messages=messages, state_changed=changed)
    db.add(
        EditorialChatTurn(
            user_id=actor.user.id,
            journal_id=actor.journal_id,
            request_id=str(body.request_id),
            input_digest=digest,
            response=result.model_dump(exclude_none=True),
            created_at=timestamp,
        )
    )
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="editorial_demo.chat_turn",
        entity_id=str(body.request_id),
        details={"demo": True, "provider": "mock", "state_changed": changed},
    )
    db.commit()
    return result
