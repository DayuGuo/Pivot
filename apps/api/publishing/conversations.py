"""Owned conversation records; creation is an audited application action."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .audit import record
from .models import Conversation, Message
from .security import Actor


def owned_conversation(db: Session, actor: Actor, conversation_id: str) -> Conversation:
    item = db.get(Conversation, conversation_id)
    if not item or item.user_id != actor.user.id or item.journal_id != actor.journal_id:
        raise HTTPException(404, "对话不存在或无权访问")
    return item


def latest_conversation(db: Session, actor: Actor) -> Conversation | None:
    return db.scalar(
        select(Conversation)
        .where(
            Conversation.user_id == actor.user.id,
            Conversation.journal_id == actor.journal_id,
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(1)
    )


def create_conversation(db: Session, actor: Actor, title: str = "新对话") -> Conversation:
    item = Conversation(user_id=actor.user.id, journal_id=actor.journal_id, title=title)
    db.add(item)
    db.flush()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="conversation.created",
        entity_id=item.id,
    )
    return item


def command_conversation(db: Session, actor: Actor, conversation_id: str | None) -> Conversation:
    if conversation_id:
        return owned_conversation(db, actor, conversation_id)
    key = int.from_bytes(
        hashlib.sha256(
            f"conversation-default:{actor.user.id}:{actor.journal_id}".encode()
        ).digest()[:8],
        signed=True,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    return latest_conversation(db, actor) or create_conversation(db, actor)


def conversation_json(db: Session, item: Conversation) -> dict:
    count = db.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == item.id)
    )
    return {
        "id": item.id,
        "title": item.title,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "message_count": count,
    }
