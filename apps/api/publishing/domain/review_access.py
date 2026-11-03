"""One peer-review policy/projection boundary for API, UI, files and model context."""

from fastapi import HTTPException
from sqlalchemy import and_, exists, select

from ..models import Manuscript, Membership, User, now
from . import core
from .models import (
    Assignment,
    FileObject,
    FormDraft,
    ManuscriptVersion,
    VersionFile,
    WorkItem,
)
from .review_models import ReviewInvitation, ReviewReport, ReviewRound, ReviewRoundFile
from .review_schemas import FORM
from .stages import checked_blob


def invitation_query(actor, manuscript_id):
    return (
        select(ReviewInvitation)
        .join(ReviewRound, ReviewRound.id == ReviewInvitation.round_id)
        .where(
            ReviewInvitation.manuscript_id == manuscript_id,
            ReviewInvitation.journal_id == actor.journal_id,
            ReviewInvitation.reviewer_id == actor.user.id,
        )
        .order_by(ReviewRound.round_no.desc(), ReviewInvitation.attempt_no.desc())
        .execution_options(populate_existing=True)
    )


def own_invitation(db, actor, manuscript_id):
    if actor.role != "reviewer":
        return None
    return db.scalar(invitation_query(actor, manuscript_id).limit(1))


def visible_condition(actor):
    return (
        exists(
            select(ReviewInvitation.id).where(
                ReviewInvitation.manuscript_id == Manuscript.id,
                ReviewInvitation.journal_id == actor.journal_id,
                ReviewInvitation.reviewer_id == actor.user.id,
            )
        )
        if actor.role == "reviewer"
        else and_(False)
    )


def current_round(db, manuscript_id):
    return db.scalar(
        select(ReviewRound)
        .where(ReviewRound.manuscript_id == manuscript_id)
        .order_by(ReviewRound.round_no.desc())
        .limit(1)
    )


def grant_active(db, actor, invitation):
    if (
        actor.role != "reviewer"
        or invitation.reviewer_id != actor.user.id
        or invitation.journal_id != actor.journal_id
    ):
        return False
    round = db.get(ReviewRound, invitation.round_id, populate_existing=True)
    if not round or round.status != "open" or invitation.status not in {"accepted", "submitted"}:
        return False
    manuscript = db.get(Manuscript, invitation.manuscript_id)
    if core.is_conflicted(db, manuscript, actor.user):
        return False
    return bool(
        db.scalar(
            select(Assignment.id)
            .where(
                Assignment.manuscript_id == invitation.manuscript_id,
                Assignment.journal_id == actor.journal_id,
                Assignment.user_id == actor.user.id,
                Assignment.capability == "reviewer",
                Assignment.review_invitation_id == invitation.id,
                Assignment.starts_at <= now(),
                (Assignment.ends_at.is_(None) | (Assignment.ends_at > now())),
            )
            .limit(1)
        )
    )


def require_invitation(db, actor, invitation_id, manuscript_id=None):
    row = db.get(ReviewInvitation, invitation_id, populate_existing=True)
    if (
        not row
        or actor.role != "reviewer"
        or row.journal_id != actor.journal_id
        or row.reviewer_id != actor.user.id
        or (manuscript_id and row.manuscript_id != manuscript_id)
    ):
        raise HTTPException(404, "邀请不存在或不属于当前账号")
    return row


def require_report(db, actor, report_id, *, write=False):
    report = db.get(ReviewReport, report_id, populate_existing=True)
    if not report:
        raise HTTPException(404, "报告不存在或无权访问")
    invitation = require_invitation(db, actor, report.invitation_id)
    if write and (
        not grant_active(db, actor, invitation)
        or invitation.status != "accepted"
        or report.status != "draft"
    ):
        raise HTTPException(403, "当前没有可编辑的本人有效评审报告")
    return report, invitation


def round_summary(db, round):
    invitations = db.scalars(
        select(ReviewInvitation).where(ReviewInvitation.round_id == round.id)
    ).all()
    return {
        "id": round.id,
        "round_no": round.round_no,
        "version_id": round.version_id,
        "status": round.status,
        "required_reports": round.required_reports,
        "submitted_reports": sum(inv.status == "submitted" for inv in invitations),
        "accepted_count": sum(inv.status == "accepted" for inv in invitations),
        "pending_count": sum(inv.status == "pending" for inv in invitations),
    }


def materials(db, round):
    pairs = db.execute(
        select(ReviewRoundFile, VersionFile, FileObject)
        .join(VersionFile, VersionFile.id == ReviewRoundFile.version_file_id)
        .join(FileObject, FileObject.id == VersionFile.file_object_id)
        .where(ReviewRoundFile.round_id == round.id)
        .order_by(ReviewRoundFile.version_file_id)
    ).all()
    return [
        {
            "id": link.id,
            "round_file_id": rf.id,
            "purpose": "blinded_manuscript",
            "visibility": "reviewer",
            "name": rf.display_name,
            "sha256": blob.sha256,
            "byte_size": blob.byte_size,
            "media_type": blob.media_type,
            "check_method": blob.check_method,
            "scan_status": blob.scan_status,
            "download_url": f"/api/publishing/review-materials/{rf.id}",
        }
        for rf, link, blob in pairs
    ]


def report_data(report):
    return {
        "id": report.id,
        "status": report.status,
        "revision": report.revision,
        "author_text": report.author_text,
        "editor_private_text": report.editor_private_text,
        "answers_json": {
            key: report.answers_json.get(key, "") for key in ("rigor", "confidential_assessment")
        },
        "recommendation": report.recommendation,
        "submitted_at": report.submitted_at.isoformat() if report.submitted_at else None,
    }


def note_candidates(db, actor, version_id, report_id):
    form = db.scalar(
        select(FormDraft).where(
            FormDraft.owner_id == actor.user.id,
            FormDraft.version_id == version_id,
            FormDraft.schema_key == "report_" + report_id,
        )
    )
    return {**form.data_json, **form.sources_json} if form else None


def eligible_reviewers(db, manuscript, round=None):
    rows = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.journal_id == manuscript.journal_id, Membership.role == "reviewer")
        .order_by(User.email)
    ).all()
    active = (
        set(
            db.scalars(
                select(ReviewInvitation.reviewer_id).where(
                    ReviewInvitation.round_id == round.id,
                    ReviewInvitation.status.in_(["pending", "accepted", "submitted"]),
                )
            )
        )
        if round
        else set()
    )
    return [
        {"id": u.id, "name": u.name, "email": u.email}
        for u in rows
        if u.id not in active and not core.is_conflicted(db, manuscript, u)
    ]


def staff_projection(db, actor, manuscript, flow):
    if not core.capabilities(db, actor, manuscript) & {
        "handling_editor",
        "chief",
    } or core.is_conflicted(db, manuscript, actor.user):
        return None
    if flow.stage not in {
        "reviewer_selection",
        "peer_review",
        "editor_recommendation",
        "chief_decision",
        "author_revision",
        "revision_assessment",
    }:
        return None
    round = current_round(db, manuscript.id)
    invitations = (
        db.scalars(
            select(ReviewInvitation)
            .where(ReviewInvitation.round_id == round.id)
            .order_by(ReviewInvitation.invited_at, ReviewInvitation.id)
        ).all()
        if round
        else []
    )
    reports = []
    for inv in invitations:
        report = db.scalar(select(ReviewReport).where(ReviewReport.invitation_id == inv.id))
        if report and report.status == "submitted":
            reports.append(
                {**report_data(report), "reviewer_name": db.get(User, inv.reviewer_id).name}
            )
    return {
        "mode": "staff",
        "round": round_summary(db, round) if round else None,
        "eligible_reviewers": eligible_reviewers(
            db, manuscript, round if round and round.status == "open" else None
        ),
        "invitations": [
            {
                "id": i.id,
                "reviewer_id": i.reviewer_id,
                "reviewer_name": db.get(User, i.reviewer_id).name,
                "reviewer_email": db.get(User, i.reviewer_id).email,
                "status": i.status,
                "attempt_no": i.attempt_no,
                "round_no": round.round_no,
                "response_due_at": i.response_due_at.isoformat(),
                "report_due_at": i.report_due_at.isoformat(),
                "notes": i.response_notes,
                "conflict_status": i.conflict_status,
            }
            for i in invitations
        ],
        "reports": reports,
        "materials": materials(db, round) if round else [],
        "form": round.form_snapshot if round else FORM,
    }


def reviewer_projection(db, actor, manuscript, flow, *, detail=True):
    inv = own_invitation(db, actor, manuscript.id)
    if not inv:
        raise HTTPException(404, "稿件不存在或无权访问")
    round = db.get(ReviewRound, inv.round_id)
    accessible = grant_active(db, actor, inv)
    files = materials(db, round) if accessible else []
    invitation_ids = list(
        db.scalars(
            select(ReviewInvitation.id).where(
                ReviewInvitation.manuscript_id == manuscript.id,
                ReviewInvitation.reviewer_id == actor.user.id,
            )
        )
    )
    own_reports = list(
        db.scalars(
            select(ReviewReport.id)
            .join(ReviewInvitation, ReviewInvitation.id == ReviewReport.invitation_id)
            .where(
                ReviewInvitation.manuscript_id == manuscript.id,
                ReviewInvitation.reviewer_id == actor.user.id,
            )
        )
    )
    visibility_scope = {
        "role": actor.role,
        "invitation_ids": sorted(invitation_ids),
        "own_report_ids": sorted(own_reports),
        "files": sorted(f["id"] for f in files),
    }
    scope = core.digest(visibility_scope)
    report = db.scalar(select(ReviewReport).where(ReviewReport.invitation_id == inv.id))
    tasks = db.scalars(
        select(WorkItem)
        .where(
            WorkItem.manuscript_id == manuscript.id,
            WorkItem.assignee_id == actor.user.id,
            WorkItem.status.in_(["pending", "waiting"]),
        )
        .order_by(WorkItem.created_at)
    ).all()
    actions = []
    can_respond = round.status == "open" and inv.status == "pending" and inv.response_due_at > now()
    can_edit = (
        accessible and inv.status == "accepted" and report is not None and report.status == "draft"
    )
    if can_respond:
        actions.append(
            {
                "action": "respond_review_invitation",
                "label": "准备邀请回应审核",
                "requires_human": True,
            }
        )
    if can_edit:
        actions.append(
            {"action": "submit_review", "label": "准备报告提交审核", "requires_human": True}
        )
    result = {
        "id": manuscript.id,
        "number": flow.number,
        "title": inv.invitation_snapshot["title"],
        "stage": flow.stage,
        "stage_label": core.STAGE_LABELS[flow.stage],
        "revision": flow.revision,
        "is_legacy": False,
        "is_owner": False,
        "capabilities": ["reviewer"] if accessible else ["invited_reviewer"],
        "current_version_id": round.version_id,
        "draft_version_id": None,
        "accepted_version_id": None,
        "own_tasks": [
            core.task_projection(t, flow, manuscript) | {"title": inv.invitation_snapshot["title"]}
            for t in tasks
        ],
        "created_at": inv.invited_at.isoformat(),
        "submitted_at": None,
        "allowed_actions": actions,
        "visibility_fingerprint": scope,
        "visibility_scope": visibility_scope,
    }
    if not detail:
        return result
    version = db.get(ManuscriptVersion, round.version_id)
    # Explicit anonymous DTO; never serialize version authors/declarations/funding.
    snapshot = (
        {
            "id": version.id,
            "version_no": version.version_no,
            "data": {
                "title": inv.invitation_snapshot["title"],
                "abstract": inv.invitation_snapshot["abstract"],
                "language": version.language,
                "article_type": version.article_type,
                "keywords": list(version.metadata_json.get("keywords", [])),
            },
            "files": files,
            "frozen_at": version.frozen_at.isoformat(),
            "provenance": "anonymous_review",
        }
        if accessible
        else None
    )
    result.update(
        {
            "versions": [
                {
                    "id": version.id,
                    "version_no": version.version_no,
                    "title": inv.invitation_snapshot["title"],
                    "frozen_at": version.frozen_at.isoformat(),
                    "provenance": "anonymous_review",
                }
            ]
            if accessible
            else [],
            "version": snapshot,
            "missing": [],
            "can_edit_intake": False,
            "field_sources": {},
            "staff_review": None,
            "return_request": None,
            "timeline": [],
            "review": {
                "mode": "reviewer",
                "round": round_summary(db, round),
                "invitation": {
                    "id": inv.id,
                    "status": inv.status,
                    "attempt_no": inv.attempt_no,
                    "title": inv.invitation_snapshot["title"],
                    "abstract": inv.invitation_snapshot["abstract"],
                    "instructions": inv.invitation_snapshot["instructions"],
                    "response_due_at": inv.response_due_at.isoformat(),
                    "report_due_at": inv.report_due_at.isoformat(),
                    "conflict_status": inv.conflict_status,
                    "response_notes": inv.response_notes,
                },
                "report": report_data(report) if report else None,
                "materials": files,
                "form": round.form_snapshot,
                "can_respond": can_respond,
                "can_edit_report": can_edit,
                "report_candidates": note_candidates(db, actor, round.version_id, report.id)
                if report
                else None,
            },
        }
    )
    return result


def download_material(db, actor, round_file_id):
    file = db.get(ReviewRoundFile, round_file_id)
    if not file:
        raise HTTPException(404, "评审材料不存在或无权访问")
    manuscript, flow = core.load_submission(db, actor, file.manuscript_id)
    if actor.role == "reviewer" and manuscript.author_id != actor.user.id:
        invitation = db.scalar(
            select(ReviewInvitation)
            .where(
                ReviewInvitation.round_id == file.round_id,
                ReviewInvitation.reviewer_id == actor.user.id,
            )
            .order_by(ReviewInvitation.attempt_no.desc())
            .limit(1)
        )
        # A later declined attempt never revives an earlier grant.
        if not invitation or not grant_active(db, actor, invitation):
            raise HTTPException(404, "评审材料不存在或无权访问")
    elif not core.capabilities(db, actor, manuscript) & {
        "handling_editor",
        "chief",
    } or core.is_conflicted(db, manuscript, actor.user):
        raise HTTPException(404, "评审材料不存在或无权访问")
    link = db.get(VersionFile, file.version_file_id)
    blob = db.get(FileObject, link.file_object_id)
    return blob, file.display_name, checked_blob(blob)
