from fastapi import HTTPException

from .models import Manuscript
from .security import Actor

EDITOR_ROLES = {"editor", "chief_editor"}


def require_editor(actor: Actor) -> None:
    if actor.role not in EDITOR_ROLES:
        raise HTTPException(403, "只有编辑或主编可以创建测试稿件并分派初筛")


def can_view_manuscript(actor: Actor, manuscript: Manuscript) -> bool:
    if actor.journal_id != manuscript.journal_id:
        return False
    return actor.role in EDITOR_ROLES or (
        actor.role == "author" and manuscript.author_id == actor.user.id
    )
