"""Bounded single-step agent runtime: proposal → deterministic action → receipt."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .actions import CREATE_TOOL, create_and_assign
from .audit import record
from .models import CommandReceipt, Message
from .policy import require_editor
from .security import Actor
from .serialization import manuscript_json, message_json


def execute_command(db: Session, actor: Actor, message: str, request_id: str, provider) -> dict:
    require_editor(actor)
    digest = hashlib.sha256(message.encode()).hexdigest()
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
        return previous.response
    proposal = provider.propose(message)
    if proposal.tool not in {None, CREATE_TOOL}:
        raise HTTPException(422, "模型提出了未授权工具；操作已阻止")
    manuscript = create_and_assign(db, actor, proposal.arguments) if proposal.tool else None
    db.add(Message(user_id=actor.user.id, role="user", content=message, provider=proposal.provider))
    prefix = "[模拟结果 · Mock] " if proposal.provider == "mock" else ""
    content = (
        f"已创建《{manuscript.title}》，提交至编辑初筛，并分派给{actor.user.name}。"
        "稿件、初筛任务和审计记录已保存。"
        if manuscript
        else "当前原型支持：创建一篇测试稿件，并交给编辑初筛。请输入该指令以创建合成测试数据。"
    )
    reply = Message(
        user_id=actor.user.id,
        role="assistant",
        content=prefix + content,
        provider=proposal.provider,
        manuscript_id=manuscript.id if manuscript else None,
    )
    db.add(reply)
    db.flush()
    response = {
        "message": message_json(reply),
        "manuscript": manuscript_json(db, manuscript) if manuscript else None,
        "provider": proposal.provider,
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
        details={"request_id": request_id, "provider": proposal.provider, "tool": proposal.tool},
    )
    db.commit()
    return response
