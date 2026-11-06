"""Bounded single-step agent runtime: proposal → deterministic action → receipt."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .actions import CREATE_TOOL, create_and_assign
from .audit import record
from .conversations import command_conversation, owned_conversation
from .models import CommandReceipt, Message, now
from .policy import require_editor
from .security import Actor, ensure_current_actor
from .serialization import manuscript_json, message_json


def execute_command(
    db: Session,
    actor: Actor,
    message: str,
    request_id: str,
    provider,
    conversation_id: str | None = None,
) -> dict:
    require_editor(actor)
    payload = f"{conversation_id}\0{message}" if conversation_id else message
    digest = hashlib.sha256(payload.encode()).hexdigest()
    # Serialize duplicate requests across API workers; released on commit/rollback.
    key = int.from_bytes(
        hashlib.sha256(f"{actor.user.id}:{request_id}".encode()).digest()[:8], signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    previous = db.scalar(
        select(CommandReceipt).where(
            CommandReceipt.user_id == actor.user.id, CommandReceipt.request_id == request_id
        )
    )
    if previous:
        if previous.input_hash != digest:
            raise HTTPException(409, "请求 ID 已用于不同内容")
        target_id = previous.response.get("conversation_id")
        if target_id:
            owned_conversation(db, actor, target_id)
        else:
            historical_reply = db.get(Message, previous.response.get("message", {}).get("id", ""))
            if historical_reply:
                owned_conversation(db, actor, historical_reply.conversation_id)
        return previous.response
    conversation = command_conversation(db, actor, conversation_id)
    proposal = provider.propose(message)
    if proposal.tool not in {None, CREATE_TOOL}:
        raise HTTPException(422, "模型提出了未授权工具；操作已阻止")
    manuscript = create_and_assign(db, actor, proposal.arguments) if proposal.tool else None
    db.add(
        Message(
            user_id=actor.user.id,
            conversation_id=conversation.id,
            role="user",
            content=message,
            provider=proposal.provider,
        )
    )
    prefix = "[模拟结果 · Mock] " if proposal.provider == "mock" else ""
    content = (
        f"已创建《{manuscript.title}》，提交至编辑初筛，并分派给{actor.user.name}。"
        "稿件、初筛任务和审计记录已保存。"
        if manuscript
        else "当前原型支持：创建一篇测试稿件，并交给编辑初筛。请输入该指令以创建合成测试数据。"
    )
    reply = Message(
        user_id=actor.user.id,
        conversation_id=conversation.id,
        role="assistant",
        content=prefix + content,
        provider=proposal.provider,
        manuscript_id=manuscript.id if manuscript else None,
    )
    db.add(reply)
    conversation.updated_at = now()
    if manuscript and conversation.title == "新对话":
        conversation.title = "测试稿件初筛"
    db.flush()
    response = {
        "message": message_json(reply),
        "manuscript": manuscript_json(db, manuscript) if manuscript else None,
        "provider": proposal.provider,
        "conversation_id": conversation.id,
    }
    db.add(
        CommandReceipt(
            user_id=actor.user.id, request_id=request_id, input_hash=digest, response=response
        )
    )
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="agent.command_completed",
        entity_id=manuscript.id if manuscript else None,
        details={
            "request_id": request_id,
            "provider": proposal.provider,
            "tool": proposal.tool,
            "conversation_id": conversation.id,
        },
    )
    ensure_current_actor(db, actor, for_commit=True)
    db.commit()
    return response
