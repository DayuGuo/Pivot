"""Private revision checks: exact sources, read-only AI and explicit human judgements."""

import json
import time
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.model_gateway.editorial import TURN_TIMEOUT_SECONDS, get_editorial_provider
from packages.model_gateway.gateway import GatewayError

from ..audit import record
from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .chat import failure_code
from .dossier_actions import event, gateway
from .dossier_revision_models import DossierRevisionCheck, DossierRevisionReview
from .dossier_revision_schemas import DossierRevisionInput, DossierRevisionReviewInput
from .dossier_revision_sources import (
    material_input,
    packet_digest,
    private_report,
    source,
    verified_packet,
)
from .pagination import cursor_position, next_cursor, older_than, scope_key
from .revision_compare import compare

router = APIRouter(prefix="/api/dossiers", tags=["internal revision checks"])


def load_check(db, actor, dossier_id, check_id):
    access.load(db, actor, str(dossier_id))
    check = db.scalar(
        select(DossierRevisionCheck).where(
            DossierRevisionCheck.id == str(check_id),
            DossierRevisionCheck.dossier_id == str(dossier_id),
            DossierRevisionCheck.journal_id == actor.journal_id,
        )
    )
    if not check:
        raise HTTPException(404, "修回核对不存在或无权访问")
    verified_packet(db, actor, str(dossier_id), check)
    return check


def review_projection(review):
    return {
        key: getattr(review, key)
        for key in (
            "id",
            "point_id",
            "response_verdict",
            "implementation_verdict",
            "editor_verdict",
            "reason",
            "review_no",
            "reviewed_by",
        )
    } | {"created_at": review.created_at.isoformat()}


def latest_reviews(db, check):
    return db.scalars(
        select(DossierRevisionReview)
        .where(DossierRevisionReview.check_id == check.id)
        .distinct(DossierRevisionReview.point_id)
        .order_by(DossierRevisionReview.point_id, DossierRevisionReview.review_no.desc())
    ).all()


def projection(db, actor, check):
    row, sources = verified_packet(db, actor, check.dossier_id, check)
    return {
        "schema": "dossier-revision-check.v1",
        "id": check.id,
        "dossier_id": row.id,
        "digest": check.digest,
        "base_version_id": check.base_version_id,
        "revised_version_id": check.revised_version_id,
        "base_version_no": sources["files"]["base"]["version_no"],
        "revised_version_no": sources["files"]["revised"]["version_no"],
        "revision": check.revision,
        "is_current": row.current_version_id == check.revised_version_id
        and row.revision == check.revision,
        "materials": check.materials_json,
        "report": check.report_json,
        "reviews": {r.point_id: review_projection(r) for r in latest_reviews(db, check)},
        "created_at": check.created_at.isoformat(),
        "created_by": check.created_by,
        "human_feedback_is_not_publication_approval": True,
    }


@router.post("/{dossier_id}/revision-checks")
def create_check(
    dossier_id: UUID,
    body: DossierRevisionInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)
    check_id = str(
        uuid5(
            NAMESPACE_URL,
            f"pivot:revision-check:{actor.journal_id}:{actor.user.id}:{body.request_id}",
        )
    )
    materials = material_input(body)
    deadline = time.monotonic() + TURN_TIMEOUT_SECONDS
    telemetry = []

    def execute():
        _, sources = source(
            db, actor, target, materials, check_id, body.expected_revision, current=True
        )
        fingerprint = sources["source_fingerprint"]

        def validate():
            if time.monotonic() >= deadline:
                raise GatewayError("editorial_provider_deadline")
            _, latest = source(
                db, actor, target, materials, check_id, body.expected_revision, current=True
            )
            if latest["source_fingerprint"] != fingerprint:
                raise HTTPException(409, "修回核对所依据的版本或原件已变化")

        provider = get_editorial_provider()
        provider.before_attempt = validate
        if getattr(provider, "set_deadline", None):
            provider.set_deadline(deadline)
        validate()
        report = private_report(compare(sources, provider, validate, telemetry), sources)
        report["telemetry"] = telemetry
        validate()
        row = access.load(db, actor, target, write=True)
        validate()  # Recheck after waiting for the final write lock.
        for value in (materials, report):
            if len(json.dumps(value, ensure_ascii=False).encode()) > 240000:
                raise HTTPException(413, "核对材料过长，请拆为不超过8条要求的较小批次")
        check = DossierRevisionCheck(
            id=check_id,
            dossier_id=row.id,
            journal_id=row.journal_id,
            base_version_id=str(body.base_version_id),
            revised_version_id=str(body.revised_version_id),
            revision=body.expected_revision,
            materials_json=materials,
            report_json=report,
            digest=packet_digest(materials, report),
            created_by=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(check)
        db.flush()
        event(db, actor, row, "revision_checked", check.revised_version_id, evidence_id=check.id)
        validate()
        return {"dossier_id": row.id, "check_id": check.id}

    def replay():
        load_check(db, actor, target, check_id)

    try:
        return gateway(
            db, actor, body, "revision_check", target, execute, revalidate_resource=replay
        )
    except GatewayError as error:
        db.rollback()
        try:
            row = access.load(db, actor, target)
            access.current(row, body.expected_revision, str(body.revised_version_id))
            record(
                db,
                actor_id=actor.user.id,
                journal_id=actor.journal_id,
                action="publishing.dossier_revision_check_failed",
                entity_id=target,
                details={
                    "error_code": "revision_comparison_invalid"
                    if error.args == ("revision_comparison_invalid",)
                    else failure_code(error),
                    "version_id": str(body.revised_version_id),
                    "telemetry": telemetry,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(503, "本轮修回核对未完成，未保存结果或推进业务；请稍后重试。") from None


@router.get("/{dossier_id}/revision-checks")
def list_checks(
    dossier_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    cursor: str | None = Query(None, max_length=600),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row = access.load(db, actor, str(dossier_id))
    scope = scope_key("revision-checks", actor.user.id, actor.journal_id, row.id)
    position = cursor_position(cursor, scope)
    query = select(DossierRevisionCheck).where(
        DossierRevisionCheck.dossier_id == row.id,
        DossierRevisionCheck.journal_id == actor.journal_id,
    )
    if position:
        query = query.where(
            older_than(DossierRevisionCheck.created_at, DossierRevisionCheck.id, position)
        )
    checks = db.scalars(
        query.order_by(
            DossierRevisionCheck.created_at.desc(), DossierRevisionCheck.id.desc()
        ).limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "id": c.id,
                "base_version_id": c.base_version_id,
                "revised_version_id": c.revised_version_id,
                "revision": c.revision,
                "provider": c.report_json["provider"],
                "point_count": len(c.report_json["rows"]),
                "created_at": c.created_at.isoformat(),
                "is_current": c.revision == row.revision
                and c.revised_version_id == row.current_version_id,
            }
            for c in checks[:limit]
        ],
        "next_cursor": next_cursor(checks, limit, scope),
    }


@router.get("/{dossier_id}/revision-checks/{check_id}")
def get_check(
    dossier_id: UUID,
    check_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return projection(db, actor, load_check(db, actor, dossier_id, check_id))


@router.get("/{dossier_id}/revision-checks/{check_id}/export")
def export_check(
    dossier_id: UUID,
    check_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    check = load_check(db, actor, dossier_id, check_id)
    packet = projection(db, actor, check)
    _, sources = verified_packet(db, actor, str(dossier_id), check)
    packet["sources"] = {
        kind: {
            key: file[key] for key in ("version_id", "version_no", "sha256", "text", "download_url")
        }
        for kind, file in sources["files"].items()
    }
    access.load(db, actor, str(dossier_id))
    return Response(
        content=json.dumps(packet, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="pivot-revision-{check.id}.json"',
            "Cache-Control": "no-store",
        },
    )


def point_exists(check, point_id):
    if not any(row["point_id"] == point_id for row in check.report_json["rows"]):
        raise HTTPException(404, "本核对包中没有此要求")


class ReviewAction(DossierRevisionReviewInput):
    check_id: UUID
    point_id: str


@router.post("/{dossier_id}/revision-checks/{check_id}/points/{point_id}/reviews")
def review_point(
    dossier_id: UUID,
    check_id: UUID,
    body: DossierRevisionReviewInput,
    point_id: str = Path(pattern=r"^P0[1-8]$"),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    def validate(*, write=False):
        row = access.load(db, actor, str(dossier_id), write=write)
        check = load_check(db, actor, dossier_id, check_id)
        if body.check_digest != check.digest:
            raise HTTPException(409, "核对包摘要已变化，请重新载入")
        point_exists(check, point_id)
        return row, check

    def execute():
        # The dossier lock serializes all human heads, including different UUID retries.
        row, check = validate(write=True)
        previous = db.scalar(
            select(DossierRevisionReview)
            .where(
                DossierRevisionReview.check_id == check.id,
                DossierRevisionReview.point_id == point_id,
            )
            .order_by(DossierRevisionReview.review_no.desc())
            .limit(1)
        )
        if (previous.id if previous else None) != (
            str(body.expected_review_id) if body.expected_review_id else None
        ):
            raise HTTPException(409, "此项已有新的人工判断，请重新载入后核对")
        review = DossierRevisionReview(
            check_id=check.id,
            dossier_id=row.id,
            journal_id=row.journal_id,
            point_id=point_id,
            check_digest=check.digest,
            response_verdict=body.response_verdict,
            implementation_verdict=body.implementation_verdict,
            editor_verdict=body.editor_verdict,
            reason=body.reason,
            review_no=previous.review_no + 1 if previous else 1,
            reviewed_by=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(review)
        db.flush()
        event(db, actor, row, "revision_reviewed", check.revised_version_id, evidence_id=check.id)
        validate()
        return review_projection(review)

    action = ReviewAction(**body.model_dump(), check_id=check_id, point_id=point_id)
    return gateway(
        db,
        actor,
        action,
        "revision_review",
        str(dossier_id),
        execute,
        revalidate_resource=validate,
    )


@router.get("/{dossier_id}/revision-checks/{check_id}/points/{point_id}/reviews")
def review_history(
    dossier_id: UUID,
    check_id: UUID,
    point_id: str = Path(pattern=r"^P0[1-8]$"),
    limit: int = Query(10, ge=1, le=50),
    before: int | None = Query(None, ge=1),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    check = load_check(db, actor, dossier_id, check_id)
    point_exists(check, point_id)
    query = select(DossierRevisionReview).where(
        DossierRevisionReview.check_id == check.id, DossierRevisionReview.point_id == point_id
    )
    if before:
        query = query.where(DossierRevisionReview.review_no < before)
    reviews = db.scalars(
        query.order_by(DossierRevisionReview.review_no.desc()).limit(limit + 1)
    ).all()
    return {
        "items": [review_projection(r) for r in reviews[:limit]],
        "next_cursor": reviews[limit - 1].review_no if len(reviews) > limit else None,
    }
