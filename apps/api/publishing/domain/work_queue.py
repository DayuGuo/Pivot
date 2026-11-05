"""Small authorized list DTOs, independent from material/action projections.

Recent browsing is bounded to 200; every currently assigned visible task and an
explicitly authorized conversation target remain reachable even when older.
No files, author metadata, action permissions or visibility grants are issued.
"""

from sqlalchemy import and_, case, exists, or_, select

from ..models import Manuscript, now
from . import core
from .models import Assignment, ManuscriptVersion, SubmissionWorkflow, WorkItem
from .review_access import visible_condition
from .review_models import ReviewInvitation, ReviewRound


def workspace(db, actor, include_id=None):
    core.ensure_actor(db, actor)
    if include_id:
        core.load_submission(db, actor, include_id)
    role_caps = {
        "author": {"author"},
        "editor": {"author", "precheck", "handling_editor"},
        "chief_editor": {"author", "chief"},
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
        Manuscript.author_id == actor.user.id,
        and_(
            SubmissionWorkflow.stage != "author_draft",
            or_(actor.role == "chief_editor", assigned, visible_condition(actor)),
        ),
    )
    base = (
        select(Manuscript.id)
        .join(SubmissionWorkflow, SubmissionWorkflow.manuscript_id == Manuscript.id)
        .where(Manuscript.journal_id == actor.journal_id, visible)
    )
    recent = base.order_by(SubmissionWorkflow.updated_at.desc(), Manuscript.id).limit(200).cte()
    own_work = exists(
        select(WorkItem.id).where(
            WorkItem.manuscript_id == Manuscript.id,
            WorkItem.journal_id == actor.journal_id,
            WorkItem.assignee_id == actor.user.id,
            WorkItem.status.in_(["pending", "waiting"]),
            SubmissionWorkflow.is_legacy.is_(False),
        )
    )
    selected_version = case(
        (
            and_(
                Manuscript.author_id == actor.user.id,
                SubmissionWorkflow.draft_version_id.is_not(None),
            ),
            SubmissionWorkflow.draft_version_id,
        ),
        else_=SubmissionWorkflow.current_version_id,
    )
    rows = db.execute(
        select(Manuscript, SubmissionWorkflow, ManuscriptVersion.title)
        .join(SubmissionWorkflow, SubmissionWorkflow.manuscript_id == Manuscript.id)
        .outerjoin(ManuscriptVersion, ManuscriptVersion.id == selected_version)
        .where(
            Manuscript.journal_id == actor.journal_id,
            visible,
            or_(
                Manuscript.id.in_(select(recent.c.id)),
                own_work,
                Manuscript.id == include_id if include_id else False,
            ),
        )
        .order_by(SubmissionWorkflow.updated_at.desc(), Manuscript.id)
    ).all()
    invitations = {}
    if actor.role == "reviewer" and rows:
        invitations = {
            invitation.manuscript_id: invitation.invitation_snapshot["title"]
            for invitation in db.scalars(
                select(ReviewInvitation)
                .join(ReviewRound, ReviewRound.id == ReviewInvitation.round_id)
                .where(
                    ReviewInvitation.journal_id == actor.journal_id,
                    ReviewInvitation.reviewer_id == actor.user.id,
                    ReviewInvitation.manuscript_id.in_([m.id for m, _, _ in rows]),
                )
                .distinct(ReviewInvitation.manuscript_id)
                .order_by(
                    ReviewInvitation.manuscript_id,
                    ReviewRound.round_no.desc(),
                    ReviewInvitation.attempt_no.desc(),
                )
            )
        }
    summaries, allowed = [], {}
    for manuscript, flow, title in rows:
        if actor.role == "reviewer" and manuscript.author_id != actor.user.id:
            if manuscript.id not in invitations:
                continue
            title = invitations[manuscript.id]
        summary = {
            "id": manuscript.id,
            "number": flow.number,
            "title": title if title is not None else manuscript.title,
            "stage": flow.stage,
            "stage_label": core.STAGE_LABELS[flow.stage],
            "revision": flow.revision,
            "is_legacy": flow.is_legacy,
            "is_owner": manuscript.author_id == actor.user.id,
        }
        summaries.append(summary)
        allowed[manuscript.id] = manuscript, flow, summary["title"]
    tasks = []
    if allowed:
        for task in db.scalars(
            select(WorkItem)
            .where(
                WorkItem.manuscript_id.in_(allowed),
                WorkItem.journal_id == actor.journal_id,
                WorkItem.assignee_id == actor.user.id,
                WorkItem.status.in_(["pending", "waiting"]),
            )
            .order_by(
                WorkItem.priority.desc(),
                WorkItem.due_at.asc().nullslast(),
                WorkItem.created_at,
                WorkItem.id,
            )
        ):
            manuscript, flow, title = allowed[task.manuscript_id]
            if not flow.is_legacy:
                tasks.append(core.task_projection(task, flow, manuscript) | {"title": title})
    core.ensure_actor(db, actor)
    return {
        "submissions": summaries,
        "tasks": tasks,
        "counts": {
            "actionable": sum(t["status"] == "pending" for t in tasks),
            "waiting": sum(t["status"] == "waiting" for t in tasks),
        },
        "synthetic_only": True,
    }
