"""Bounded feedback projections; head and page always use one database snapshot."""

from sqlalchemy import select, true
from sqlalchemy.orm import aliased

from .claim_review_models import ClaimReview


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


def history_page(db, answer_id, bucket, index, limit, before):
    stmt = query(answer_id, bucket, index).order_by(ClaimReview.review_no.desc())
    head = stmt.with_only_columns(ClaimReview.id.label("latest_id")).limit(1).cte("review_head")
    page = (
        (stmt.where(ClaimReview.review_no < before) if before else stmt)
        .limit(limit + 1)
        .cte("review_page")
    )
    entity = aliased(ClaimReview, page)
    pairs = db.execute(
        select(head.c.latest_id, entity)
        .select_from(head)
        .outerjoin(page, true())
        .order_by(page.c.review_no.desc())
    ).all()
    return (pairs[0][0] if pairs else None), [review for _, review in pairs if review is not None]
