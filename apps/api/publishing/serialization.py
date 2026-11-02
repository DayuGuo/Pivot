from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EditorialTask, Manuscript, Message, User
from .security import Actor


def user_json(actor: Actor) -> dict:
    return {
        "id": actor.user.id,
        "email": actor.user.email,
        "name": actor.user.name,
        "role": actor.role,
    }


def manuscript_json(db: Session, item: Manuscript) -> dict:
    task = db.scalar(select(EditorialTask).where(EditorialTask.manuscript_id == item.id))
    author = db.get(User, item.author_id)
    editor = db.get(User, item.editor_id)
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "author_name": author.name,
        "editor_name": editor.name,
        "task": {"id": task.id, "status": task.status, "kind": task.kind} if task else None,
    }


def message_json(item: Message) -> dict:
    return {
        "id": item.id,
        "role": item.role,
        "conversation_id": item.conversation_id,
        "content": item.content,
        "provider": item.provider,
        "manuscript_id": item.manuscript_id,
        "created_at": item.created_at.isoformat(),
    }
