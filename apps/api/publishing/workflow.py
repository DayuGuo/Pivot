from fastapi import HTTPException
from sqlalchemy.orm import Session

from .audit import record
from .models import Manuscript
from .policy import require_editor
from .security import Actor

TRANSITIONS = {"draft": {"submitted"}, "submitted": {"screening"}}


def transition(db: Session, actor: Actor, manuscript: Manuscript, target: str) -> None:
    require_editor(actor)
    if manuscript.journal_id != actor.journal_id:
        raise HTTPException(403, "跨期刊操作被禁止")
    if target not in TRANSITIONS.get(manuscript.status, set()):
        raise HTTPException(409, "不允许的出版状态转换；重大决定必须由人类审批流程处理")
    previous = manuscript.status
    manuscript.status = target
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="manuscript.transitioned",
        entity_id=manuscript.id,
        details={"from": previous, "to": target},
    )
