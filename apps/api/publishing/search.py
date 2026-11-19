"""Bounded metadata search under the current session's existing object policy.

Matching is literal case-insensitive substring matching, with whitespace tokens
combined by AND. Hidden versions, author fields and message bodies never become
search signals. This read-only route has no model, file, audit or mutation work.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, false, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from .db import get_db
from .domain.dossier_models import Dossier, DossierVersion
from .domain.metadata_access import formal_metadata_statement
from .domain.models import SubmissionWorkflow
from .models import Conversation, Manuscript
from .policy import EDITOR_ROLES
from .security import Actor, ensure_current_actor, get_actor

router = APIRouter(prefix="/api", tags=["private metadata search"])


def _matches(tokens, *fields):
    return and_(
        *(
            or_(*(func.coalesce(field, "").icontains(token, autoescape=True) for field in fields))
            for token in tokens
        )
    )


def _conversation_rows(db, actor, tokens, limit):
    return db.execute(
        select(Conversation.id, Conversation.title)
        .where(
            Conversation.user_id == actor.user.id,
            Conversation.journal_id == actor.journal_id,
            _matches(tokens, Conversation.title, Conversation.id),
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit + 1)
    ).all()


def _formal_statement(actor, tokens):
    statement = formal_metadata_statement(actor)
    return statement.where(
        _matches(
            tokens,
            statement.selected_columns.title,
            Manuscript.id,
            func.concat("#", Manuscript.id),
            SubmissionWorkflow.number,
        )
    )


def _manuscript_rows(db, actor, tokens, limit):
    # Legacy records without a normalized workflow retain policy.can_view_manuscript.
    legacy_visible = (
        True
        if actor.role in EDITOR_ROLES
        else Manuscript.author_id == actor.user.id
        if actor.role == "author"
        else false()
    )
    legacy = select(
        Manuscript.id,
        Manuscript.title,
        Manuscript.created_at.label("at"),
        literal("legacy").label("route"),
    ).where(
        Manuscript.journal_id == actor.journal_id,
        Manuscript.workflow_kind == "legacy",
        ~exists(
            select(SubmissionWorkflow.manuscript_id).where(
                SubmissionWorkflow.manuscript_id == Manuscript.id
            )
        ),
        legacy_visible,
        _matches(tokens, Manuscript.title, Manuscript.id, func.concat("#", Manuscript.id)),
    )
    combined = union_all(_formal_statement(actor, tokens), legacy).subquery()
    return db.execute(
        select(combined.c.id, combined.c.title, combined.c.route)
        .order_by(combined.c.at.desc(), combined.c.id.desc())
        .limit(limit + 1)
    ).all()


def _dossier_rows(db, actor, tokens, limit):
    if actor.role not in EDITOR_ROLES:
        return []
    title = DossierVersion.data_json["title"].as_string()
    return db.execute(
        select(Dossier.id, title.label("title"))
        .join(
            DossierVersion,
            and_(
                DossierVersion.id == Dossier.current_version_id,
                DossierVersion.dossier_id == Dossier.id,
                DossierVersion.journal_id == Dossier.journal_id,
            ),
        )
        .where(
            Dossier.created_by == actor.user.id,
            Dossier.journal_id == actor.journal_id,
            _matches(tokens, title, Dossier.id),
        )
        .order_by(Dossier.updated_at.desc(), Dossier.id.desc())
        .limit(limit + 1)
    ).all()


@router.get("/search")
def search(
    q: str = Query("", max_length=160),
    limit: int = Query(8, ge=1, le=20),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    if "\x00" in q:
        raise HTTPException(422, "搜索内容不能包含空字符")
    query = " ".join(q.split())
    tokens = query.split()
    ensure_current_actor(db, actor)
    conversations = _conversation_rows(db, actor, tokens, limit) if tokens else []
    manuscripts = _manuscript_rows(db, actor, tokens, limit) if tokens else []
    dossiers = _dossier_rows(db, actor, tokens, limit) if tokens else []
    ensure_current_actor(db, actor)
    groups = []
    for kind, label, rows in (
        ("conversation", "对话", conversations),
        ("manuscript", "稿件", manuscripts),
        ("dossier", "内部资料", dossiers),
    ):
        items = []
        for row in rows[:limit]:
            identifier = quote(row.id, safe="")
            if kind == "conversation":
                href = f"/?conversation={identifier}"
            elif kind == "dossier":
                href = f"/library?dossier={identifier}"
            else:
                href = f"{'/publishing' if row.route == 'formal' else '/'}?manuscript={identifier}"
            items.append({"id": row.id, "title": row.title or "未命名", "href": href})
        groups.append({"kind": kind, "label": label, "items": items, "has_more": len(rows) > limit})
    return {"query": query, "groups": groups}
