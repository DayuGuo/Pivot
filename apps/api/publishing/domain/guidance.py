"""Cheap read-only context hints; no model call on page load, no permissions granted."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import core
from .claim_review_models import ClaimReview
from .dossier_chat_models import DossierAnswer
from .dossier_views import projection
from .guidance_rules import dossier_rules, publishing_rules, suggestion
from .models import PublishingChatTurn

router = APIRouter(tags=["contextual next steps"])


@router.get("/api/dossiers/{dossier_id}/guidance")
def dossier_guidance(
    dossier_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    detail = projection(db, actor, str(dossier_id))
    answer = db.scalar(
        select(DossierAnswer)
        .where(
            DossierAnswer.dossier_id == str(dossier_id),
            DossierAnswer.journal_id == actor.journal_id,
            DossierAnswer.version_id == detail["version_id"],
        )
        .order_by(DossierAnswer.created_at.desc(), DossierAnswer.id.desc())
        .limit(1)
    )
    flagged = False
    withheld = []
    if answer:
        latest = db.scalars(
            select(ClaimReview)
            .where(ClaimReview.answer_id == answer.id)
            .distinct(ClaimReview.claim_bucket, ClaimReview.claim_index)
            .order_by(
                ClaimReview.claim_bucket, ClaimReview.claim_index, ClaimReview.review_no.desc()
            )
        ).all()
        flagged = any(r.verdict in {"unsupported", "uncertain"} for r in latest)
        withheld = answer.result_json.get("withheld_claims", [])
    return {
        "schema": "next-steps.v1",
        "object_id": str(dossier_id),
        "version_id": detail["version_id"],
        "revision": detail["revision"],
        "role": actor.role,
        "basis": "saved_context_not_quality_certification",
        "suggestions": dossier_rules(detail, withheld=withheld, human_flagged=flagged),
    }


@router.get("/api/publishing/guidance")
def journal_guidance(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    core.ensure_actor(db, actor)
    return {
        "schema": "next-steps.v1",
        "object_id": None,
        "version_id": None,
        "revision": None,
        "role": actor.role,
        "basis": "current_role",
        "suggestions": publishing_rules(actor.role, None),
    }


@router.get("/api/publishing/manuscripts/{manuscript_id}/guidance")
def manuscript_guidance(
    manuscript_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    detail = core.submission_projection(db, actor, str(manuscript_id))
    hints = publishing_rules(actor.role, detail)
    previous = db.scalar(
        select(PublishingChatTurn)
        .where(
            PublishingChatTurn.manuscript_id == str(manuscript_id),
            PublishingChatTurn.user_id == actor.user.id,
            PublishingChatTurn.journal_id == actor.journal_id,
            PublishingChatTurn.context_snapshot["role"].astext == actor.role,
            PublishingChatTurn.response["messages"][1]["revision_comparison"].is_not(None),
        )
        .order_by(PublishingChatTurn.created_at.desc(), PublishingChatTurn.id.desc())
        .limit(1)
    )
    if previous:
        report = previous.response["messages"][1].get("revision_comparison")
        if (
            report
            and detail.get("version")
            and report.get("revised_version_id") == detail["version"]["id"]
            and report.get("workflow_revision") == detail["revision"]
        ):
            pending = [
                r for r in report["rows"] if r["status"] not in {"resolved", "not_applicable"}
            ]
            if pending:
                offset = report.get("point_offset", 0)
                offset = offset if type(offset) is int and 0 <= offset < 1000000 else 0
                hints = [
                    suggestion(
                        "revision-followup",
                        "核对待核实项",
                        f"请从第{offset + 1}项开始，逐条比对本次修回，优先核对最近一批仍待核实的意见；引用作者回复与修改后原文，不能把声称已修改当成落实。",
                        f"最近一批有{len(pending)}项待核对，其他批次请分别检查",
                    )
                ] + hints[:2]
    return {
        "schema": "next-steps.v1",
        "object_id": str(manuscript_id),
        "version_id": detail["version"]["id"] if detail.get("version") else None,
        "revision": detail["revision"],
        "role": actor.role,
        "basis": "authorized_stage_and_tasks",
        "suggestions": hints,
    }
