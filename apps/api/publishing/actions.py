"""Only deterministic application actions may mutate publication state."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .models import EditorialTask, Manuscript, Membership, User
from .policy import require_editor
from .security import Actor
from .workflow import transition

CREATE_TOOL = "create_test_manuscript_and_assign_screening"


def create_and_assign(db: Session, actor: Actor, arguments: dict) -> Manuscript:
    require_editor(actor)
    # Ignore model-supplied identity, roles, status or recipients; arguments are untrusted.
    if set(arguments) - {"title"}:
        raise HTTPException(422, "工具参数超出授权范围")
    author = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.journal_id == actor.journal_id,
            Membership.role == "author",
            User.email == "author@publishing.test",
        )
    )
    if not author:
        raise HTTPException(409, "期刊尚未配置合成测试作者")
    title = arguments.get("title", "测试稿件：开放科学出版工作流验证")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 240:
        raise HTTPException(422, "稿件标题无效")
    manuscript = Manuscript(
        journal_id=actor.journal_id,
        author_id=author.id,
        editor_id=actor.user.id,
        title=title.strip(),
        status="draft",
    )
    db.add(manuscript)
    db.flush()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="manuscript.created",
        entity_id=manuscript.id,
        details={"synthetic": True},
    )
    transition(db, actor, manuscript, "submitted")
    transition(db, actor, manuscript, "screening")
    task = EditorialTask(manuscript_id=manuscript.id, assignee_id=actor.user.id)
    db.add(task)
    db.flush()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="editorial_task.assigned",
        entity_id=manuscript.id,
        details={"task_id": task.id, "assignee_id": actor.user.id, "kind": task.kind},
    )
    return manuscript
