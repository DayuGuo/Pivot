"""SQL-only safe manuscript title projection shared by metadata readers.

This does not grant actions or file access; actual mutations retain core policy.
"""

from sqlalchemy import and_, case, exists, func, literal, or_, select

from ..models import Manuscript, now
from .decision_models import EditorialDecision
from .models import Assignment, ManuscriptVersion, SubmissionWorkflow, VersionAuthor
from .review_access import visible_condition
from .review_models import ReviewInvitation, ReviewRound


def formal_metadata_statement(actor):
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
