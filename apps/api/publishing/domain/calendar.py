"""Read-only, role-scoped deadlines from existing authoritative work items."""

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import now
from ..security import Actor, ensure_current_actor, get_actor
from . import core
from .calendar_queries import personal_task_statement

router = APIRouter(prefix="/api/calendar", tags=["personal deadlines"])
TIMEZONES = frozenset(available_timezones()) - {"localtime"}


def _cursor(value, scope):
    if not value:
        return None
    try:
        payload = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"scope", "at", "id"}
            or not all(isinstance(v, str) for v in payload.values())
            or payload["scope"] != scope
        ):
            raise ValueError
        stamp = datetime.fromisoformat(payload["at"])
        identifier = str(UUID(payload["id"]))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        return stamp, identifier
    except (ValueError, TypeError, KeyError, binascii.Error, OverflowError):
        raise HTTPException(422, "分页位置无效，请重新载入日历") from None


@router.get("")
def calendar(
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
    tz: str = Query("UTC", min_length=1, max_length=100),
    view: Literal["month", "overdue"] = "month",
    day: str | None = Query(None, max_length=10),
    cursor: str | None = Query(None, max_length=1000),
    limit: int = Query(12, ge=1, le=50),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    ensure_current_actor(db, actor)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError
        start = date.fromisoformat(month + "-01")
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        if tz not in TIMEZONES:
            raise ValueError
        zone = ZoneInfo(tz)
        chosen = date.fromisoformat(day) if day else None
        if day and (
            view != "month" or not day.startswith(month + "-") or chosen.isoformat() != day
        ):
            raise ValueError
    except (ValueError, OverflowError, ZoneInfoNotFoundError):
        raise HTTPException(422, "请选择有效月份、日期和时区") from None
    stamp = now()
    lower = datetime.combine(start, time.min, zone).astimezone(UTC)
    upper = datetime.combine(end, time.min, zone).astimezone(UTC)
    source = personal_task_statement(actor, stamp).subquery()
    in_month = and_(source.c.due_at >= lower, source.c.due_at < upper)
    counts = db.execute(
        select(
            func.count().filter(in_month).label("month"),
            func.count().filter(source.c.due_at < stamp).label("overdue"),
            func.count().filter(source.c.due_at.is_(None)).label("undated"),
        ).select_from(source)
    ).one()
    local_day = func.date(func.timezone(tz, source.c.due_at))
    days = db.execute(
        select(local_day.label("date"), func.count().label("count"))
        .where(in_month)
        .group_by(local_day)
        .order_by(local_day)
    ).all()
    condition = source.c.due_at < stamp if view == "overdue" else in_month
    if chosen:
        a = datetime.combine(chosen, time.min, zone).astimezone(UTC)
        b = datetime.combine(chosen + timedelta(days=1), time.min, zone).astimezone(UTC)
        condition = and_(source.c.due_at >= a, source.c.due_at < b)
    scope = hashlib.sha256(
        json.dumps([actor.journal_id, actor.user.id, actor.role, month, tz, view, day]).encode()
    ).hexdigest()
    position = _cursor(cursor, scope)
    query = select(source).where(condition)
    if position:
        query = query.where(tuple_(source.c.due_at, source.c.id) > position)
    rows = db.execute(query.order_by(source.c.due_at, source.c.id).limit(limit + 1)).all()
    ensure_current_actor(db, actor)
    labels = {"respond_review_invitation": "回应审稿邀请", "submit_review": "提交审稿报告"}
    items = [
        {
            "id": row.id,
            "manuscript_id": row.manuscript_id,
            "number": row.number,
            "title": row.title,
            "kind": row.kind,
            "label": labels.get(row.kind, core.STAGE_LABELS.get(row.kind, row.kind)),
            "status": row.status,
            "due_at": row.due_at.isoformat(),
            "overdue": row.due_at < stamp,
            "href": "/publishing?manuscript=" + quote(row.manuscript_id, safe=""),
        }
        for row in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "at": last.due_at.isoformat(), "id": last.id}).encode()
        ).decode()
    return {
        "month": month,
        "timezone": tz,
        "view": view,
        "day": day,
        "server_now": stamp.isoformat(),
        "days": [{"date": r.date.isoformat(), "count": r._mapping["count"]} for r in days],
        "counts": dict(counts._mapping),
        "items": items,
        "next_cursor": next_cursor,
    }
