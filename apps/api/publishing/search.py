"""Bounded metadata search under the current session's existing object policy.

Matching is literal case-insensitive substring matching, with whitespace tokens
combined by AND. Hidden versions, author fields and message bodies never become
search signals. This read-only route has no model, file, audit or mutation work.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, exists, false, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from .db import get_db
from .domain.decision_models import EditorialDecision
from .domain.dossier_models import Dossier, DossierVersion
from .domain.models import Assignment, ManuscriptVersion, SubmissionWorkflow, VersionAuthor
from .domain.review_access import visible_condition
from .domain.review_models import ReviewInvitation, ReviewRound
from .models import Conversation, Manuscript, now
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
    """SQL form of core.can_view and the current version's safe title projection.

    Ownership remains available in every registered role. Production is narrowed
    to production.source/can_produce prerequisites, and reviewer matching uses
    only the same latest personal invitation as reviewer_projection.
    """
    owner = Manuscript.author_id == actor.user.id
    role_caps = {
        "author": {"author"},
        "editor": {"author", "precheck", "handling_editor"},
        "chief_editor": {"author", "chief"},
        "reviewer": {"author"},
        "production_editor": {"author", "production"},
    }.get(actor.role, set())
    assigned = exists(
        select(Assignment.id).where(
            Assignment.manuscript_id == Manuscript.id,
            Assignment.journal_id == actor.journal_id,
            Assignment.user_id == actor.user.id,
            Assignment.capability.in_(role_caps),
            Assignment.starts_at <= now(),
            or_(Assignment.ends_at.is_(None), Assignment.ends_at > now()),
        )
    )
    visible = or_(
        owner,
        and_(
            SubmissionWorkflow.stage != "author_draft",
            or_(actor.role == "chief_editor", assigned, visible_condition(actor)),
        ),
    )
    selected_version = case(
        (
            and_(owner, SubmissionWorkflow.draft_version_id.is_not(None)),
            SubmissionWorkflow.draft_version_id,
        ),
        (and_(~owner, actor.role == "production_editor"), SubmissionWorkflow.accepted_version_id),
        else_=SubmissionWorkflow.current_version_id,
    )
    invitation_title = (
        select(ReviewInvitation.invitation_snapshot["title"].as_string())
        .join(ReviewRound, ReviewRound.id == ReviewInvitation.round_id)
        .where(
            ReviewInvitation.manuscript_id == Manuscript.id,
            ReviewInvitation.journal_id == actor.journal_id,
            ReviewInvitation.reviewer_id == actor.user.id,
        )
        .order_by(ReviewRound.round_no.desc(), ReviewInvitation.attempt_no.desc())
        .limit(1)
        .correlate(Manuscript)
        .scalar_subquery()
    )
    title = case(
        (and_(~owner, actor.role == "reviewer"), invitation_title),
        else_=ManuscriptVersion.title,
    )
    statement = (
        select(
            Manuscript.id,
            title.label("title"),
            SubmissionWorkflow.updated_at.label("at"),
            literal("formal").label("route"),
        )
        .join(
            SubmissionWorkflow,
            and_(
                SubmissionWorkflow.manuscript_id == Manuscript.id,
                SubmissionWorkflow.journal_id == Manuscript.journal_id,
            ),
        )
        .outerjoin(
            ManuscriptVersion,
            and_(
                ManuscriptVersion.id == selected_version,
                ManuscriptVersion.manuscript_id == Manuscript.id,
            ),
        )
        .where(
            Manuscript.journal_id == actor.journal_id,
            visible,
            title.is_not(None),
            _matches(
                tokens,
                title,
                Manuscript.id,
                func.concat("#", Manuscript.id),
                SubmissionWorkflow.number,
            ),
        )
    )
    if actor.role == "production_editor":
        production_assignment = exists(
            select(Assignment.id).where(
                Assignment.manuscript_id == Manuscript.id,
                Assignment.journal_id == actor.journal_id,
                Assignment.user_id == actor.user.id,
                Assignment.capability == "production",
                Assignment.starts_at <= now(),
                or_(Assignment.ends_at.is_(None), Assignment.ends_at > now()),
            )
        )
        conflict = exists(
            select(VersionAuthor.id).where(
                VersionAuthor.manuscript_id == Manuscript.id,
                or_(
                    VersionAuthor.linked_user_id == actor.user.id,
                    func.lower(VersionAuthor.email) == actor.user.email.casefold(),
                ),
            )
        )
        acceptance = exists(
            select(EditorialDecision.id).where(
                EditorialDecision.manuscript_id == Manuscript.id,
                EditorialDecision.journal_id == actor.journal_id,
                EditorialDecision.version_id == SubmissionWorkflow.accepted_version_id,
                EditorialDecision.decision_code == "accept",
            )
        )
        statement = statement.where(
            or_(
                owner,
                and_(
                    production_assignment,
                    ~conflict,
                    Manuscript.status == "accepted",
                    ManuscriptVersion.frozen_at.is_not(None),
                    acceptance,
                ),
            )
        )
    return statement


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
