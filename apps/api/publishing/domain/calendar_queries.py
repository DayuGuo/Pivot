"""Role-scoped SQL projection of existing work-item responsibilities.

No HTTP, model, file access or mutations are performed here.
"""

from sqlalchemy import and_, case, exists, func, or_, select

from ..models import Manuscript
from . import core
from .metadata_access import formal_metadata_statement
from .models import Assignment, StepRun, SubmissionWorkflow, VersionAuthor, WorkItem
from .review_models import ReviewInvitation, ReviewReport, ReviewRound

ROLE_CAPS = {
    "author": {"author"},
    "editor": {"precheck", "handling_editor"},
    "chief_editor": {"chief"},
    "production_editor": {"production"},
}


def personal_task_statement(actor, stamp):
    visible = formal_metadata_statement(actor).subquery()
    caps = ROLE_CAPS.get(actor.role, set())
    kinds = [kind for kind, cap in core.CAPABILITIES.items() if cap in caps]
    capability = case(*[(WorkItem.kind == k, v) for k, v in core.CAPABILITIES.items()])
    assigned = exists(
        select(Assignment.id).where(
            Assignment.manuscript_id == WorkItem.manuscript_id,
            Assignment.journal_id == actor.journal_id,
            Assignment.user_id == actor.user.id,
            Assignment.capability == capability,
            Assignment.starts_at <= stamp,
            or_(Assignment.ends_at.is_(None), Assignment.ends_at > stamp),
        )
    )
    conflict = exists(
        select(VersionAuthor.id).where(
            VersionAuthor.manuscript_id == WorkItem.manuscript_id,
            or_(
                VersionAuthor.linked_user_id == actor.user.id,
                func.lower(VersionAuthor.email) == actor.user.email.casefold(),
            ),
        )
    )
    conflict = conflict.correlate(WorkItem)
    normal = and_(
        WorkItem.kind.in_(kinds),
        WorkItem.step_run_id == SubmissionWorkflow.current_step_id,
        or_(
            and_(actor.role == "author", Manuscript.author_id == actor.user.id),
            and_(
                actor.role != "author", Manuscript.author_id != actor.user.id, assigned, ~conflict
            ),
        ),
    )
    response = exists(
        select(ReviewInvitation.id)
        .join(ReviewRound, ReviewRound.id == ReviewInvitation.round_id)
        .where(
            ReviewInvitation.id == WorkItem.review_invitation_id,
            ReviewInvitation.manuscript_id == WorkItem.manuscript_id,
            ReviewInvitation.journal_id == actor.journal_id,
            ReviewInvitation.reviewer_id == actor.user.id,
            ReviewInvitation.status == "pending",
            ReviewRound.status == "open",
        )
    )
    review_assigned = exists(
        select(Assignment.id).where(
            Assignment.manuscript_id == WorkItem.manuscript_id,
            Assignment.journal_id == actor.journal_id,
            Assignment.user_id == actor.user.id,
            Assignment.capability == "reviewer",
            Assignment.review_invitation_id == ReviewInvitation.id,
            Assignment.starts_at <= stamp,
            or_(Assignment.ends_at.is_(None), Assignment.ends_at > stamp),
        )
    ).correlate(ReviewInvitation, WorkItem)
    report = exists(
        select(ReviewReport.id)
        .join(ReviewInvitation, ReviewInvitation.id == ReviewReport.invitation_id)
        .join(ReviewRound, ReviewRound.id == ReviewInvitation.round_id)
        .where(
            ReviewReport.id == WorkItem.review_report_id,
            ReviewReport.manuscript_id == WorkItem.manuscript_id,
            ReviewInvitation.journal_id == actor.journal_id,
            ReviewInvitation.reviewer_id == actor.user.id,
            ReviewInvitation.status == "accepted",
            ReviewReport.status == "draft",
            review_assigned,
            ReviewRound.status == "open",
            ~conflict,
        )
    )
    review = and_(
        actor.role == "reviewer",
        Manuscript.author_id != actor.user.id,
        or_(
            and_(WorkItem.kind == "respond_review_invitation", response),
            and_(WorkItem.kind == "submit_review", report),
        ),
    )
    return (
        select(
            WorkItem.id,
            WorkItem.manuscript_id,
            visible.c.title,
            SubmissionWorkflow.number,
            WorkItem.kind,
            WorkItem.status,
            WorkItem.due_at,
        )
        .join(visible, visible.c.id == WorkItem.manuscript_id)
        .join(Manuscript, Manuscript.id == WorkItem.manuscript_id)
        .join(SubmissionWorkflow, SubmissionWorkflow.manuscript_id == WorkItem.manuscript_id)
        .join(StepRun, StepRun.id == WorkItem.step_run_id)
        .where(
            WorkItem.journal_id == actor.journal_id,
            WorkItem.assignee_id == actor.user.id,
            WorkItem.status.in_(["pending", "waiting"]),
            SubmissionWorkflow.is_legacy.is_(False),
            StepRun.status == "pending",
            or_(normal, review),
        )
    )
