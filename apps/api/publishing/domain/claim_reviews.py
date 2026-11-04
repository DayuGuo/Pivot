"""Private, version-bound human feedback; no model tools or publication transitions."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import Field, field_validator
from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .claim_review_metrics import summarize
from .claim_review_models import ClaimReview
from .core import digest
from .document_sources import source_projection
from .dossier_actions import event, gateway
from .dossier_chat_models import DossierAnswer
from .dossier_schemas import ExplicitTrue, RequestID
from .schemas import StrictInput

Bucket = Literal["claims", "withheld_claims"]
router = APIRouter(prefix="/api/dossiers", tags=["human evidence feedback"])


class ReviewInput(StrictInput):
    request_id: RequestID
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_review_id: RequestID | None
    verdict: Literal["supported", "unsupported", "uncertain"]
    note: str = Field(min_length=5, max_length=2000)
    acknowledged: ExplicitTrue

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        if len(value.strip()) < 5:
            raise ValueError("请填写至少5字的实际核对理由")
        if "\x00" in value:
            raise ValueError("核对理由不能包含空字符，请删除后重试")
        return value.strip()


class ReviewAction(ReviewInput):
    answer_id: UUID
    claim_bucket: Bucket
    claim_index: int


def answer_source(db, actor, dossier_id, answer_id, *, write=False):
    row = access.load(db, actor, str(dossier_id), write=write)
    answer = db.get(DossierAnswer, str(answer_id))
    if not answer or answer.dossier_id != row.id or answer.journal_id != row.journal_id:
        raise HTTPException(404, "结论不存在或无权访问")
    item = access.version(db, row, answer.version_id)
    material = access.file_content(db, item)
    actual = access.snapshot_digest(
        item.data_json,
        material[0].sha256 if material else None,
        item.file_name,
        item.file_media_type,
    )
    if actual != item.content_digest:
        raise HTTPException(409, "版本来源已变化，请重新载入")
    source_projection(db, row, item)
    return row, item, answer


def target(db, actor, dossier_id, answer_id, bucket, index, *, write=False):
    row, item, answer = answer_source(db, actor, dossier_id, answer_id, write=write)
    claims = answer.result_json.get(bucket, [])
    if not isinstance(claims, list):
        raise HTTPException(409, "原结论格式异常，请联系负责人核对")
    if index >= len(claims):
        raise HTTPException(404, "结论不存在或无权访问")
    if not isinstance(claims[index], dict) or not claims[index].get("citations"):
        raise HTTPException(409, "原结论缺少可核对来源")
    return row, item, claims[index]


def query(answer_id, bucket, index):
    return select(ClaimReview).where(
        ClaimReview.answer_id == str(answer_id),
        ClaimReview.claim_bucket == bucket,
        ClaimReview.claim_index == index,
    )


def projection(review):
    return {
        k: getattr(review, k)
        for k in (
            "id",
            "verdict",
            "note",
            "review_no",
            "claim_digest",
            "content_digest",
            "reviewed_by",
        )
    } | {"created_at": review.created_at.isoformat()}


@router.get("/{dossier_id}/answers/{answer_id}/claims/{bucket}/{index}/reviews")
def history(
    dossier_id: UUID,
    answer_id: UUID,
    bucket: Bucket,
    index: int = Path(ge=0, le=5),
    limit: int = Query(10, ge=1, le=50),
    before: int | None = Query(None, ge=1),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    _, item, claim = target(db, actor, dossier_id, answer_id, bucket, index)
    stmt = query(answer_id, bucket, index).order_by(ClaimReview.review_no.desc())
    latest = db.scalar(stmt.limit(1))
    rows = db.scalars(
        (stmt.where(ClaimReview.review_no < before) if before else stmt).limit(limit + 1)
    ).all()
    for review in rows:
        if (
            review.claim_digest != digest(claim)
            or review.content_digest != item.content_digest
            or review.claim_json != claim
        ):
            raise HTTPException(409, "复核记录与来源不匹配，请联系负责人")
    return {
        "items": [projection(r) for r in rows[:limit]],
        "next_cursor": rows[limit - 1].review_no if len(rows) > limit else None,
        "latest_id": latest.id if latest else None,
        "claim_digest": digest(claim),
        "content_digest": item.content_digest,
    }


@router.post("/{dossier_id}/answers/{answer_id}/claims/{bucket}/{index}/reviews")
def review_claim(
    dossier_id: UUID,
    answer_id: UUID,
    bucket: Bucket,
    body: ReviewInput,
    index: int = Path(ge=0, le=5),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    def validate():
        row, item, claim = target(db, actor, dossier_id, answer_id, bucket, index, write=True)
        if body.content_digest != item.content_digest or body.claim_digest != digest(claim):
            raise HTTPException(409, "复核目标已变化，请重新载入原结论")
        return row, item, claim

    def execute():
        row, item, claim = validate()
        snapshot_size = db.scalar(
            select(func.octet_length(cast(literal(claim, type_=JSONB), Text)))
        )
        if snapshot_size > 32768:
            raise HTTPException(
                413,
                "本条结论附带的引用内容过长，暂不支持保存复核；请拆分问题生成较短的独立结论后再核对。未保存复核，原回答保持不变。",
            )
        latest = db.scalar(
            query(answer_id, bucket, index).order_by(ClaimReview.review_no.desc()).limit(1)
        )
        if (latest.id if latest else None) != (
            str(body.expected_review_id) if body.expected_review_id else None
        ):
            raise HTTPException(409, "此结论已有新的人工复核，请重新载入后核对")
        review = ClaimReview(
            answer_id=str(answer_id),
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_id=item.id,
            claim_bucket=bucket,
            claim_index=index,
            claim_json=claim,
            claim_digest=digest(claim),
            content_digest=item.content_digest,
            verdict=body.verdict,
            note=body.note,
            review_no=latest.review_no + 1 if latest else 1,
            reviewed_by=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(review)
        db.flush()
        event(db, actor, row, "claim_reviewed", item.id)
        return projection(review)

    def replay():
        validate()

    action = ReviewAction(
        **body.model_dump(), answer_id=answer_id, claim_bucket=bucket, claim_index=index
    )
    return gateway(
        db, actor, action, "claim_review", str(dossier_id), execute, revalidate_resource=replay
    )


@router.get("/{dossier_id}/answers/{answer_id}/review-summary")
def review_summary(
    dossier_id: UUID,
    answer_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row, item, answer = answer_source(db, actor, dossier_id, answer_id)
    reviews = db.scalars(
        select(ClaimReview)
        .where(
            ClaimReview.answer_id == str(answer_id),
            ClaimReview.dossier_id == row.id,
            ClaimReview.journal_id == row.journal_id,
        )
        .distinct(ClaimReview.claim_bucket, ClaimReview.claim_index)
        .order_by(ClaimReview.claim_bucket, ClaimReview.claim_index, ClaimReview.review_no.desc())
    ).all()
    for review in reviews:
        claim = answer.result_json.get(review.claim_bucket, [])[review.claim_index]
        if (
            review.claim_json != claim
            or review.claim_digest != digest(claim)
            or review.content_digest != item.content_digest
        ):
            raise HTTPException(409, "复核记录与原结论不匹配")
    return {
        "schema": "claim-review-summary.v1",
        "dossier_id": row.id,
        "answer_id": answer.id,
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "metrics": summarize(reviews),
        "reviews": [
            {**projection(r), "claim_bucket": r.claim_bucket, "claim_index": r.claim_index}
            for r in reviews
        ],
        "human_feedback_is_not_publication_approval": True,
    }
