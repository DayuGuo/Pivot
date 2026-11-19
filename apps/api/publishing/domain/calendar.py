"""Read-only, role-scoped deadlines from existing authoritative work items."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import now
from ..security import Actor, ensure_current_actor, get_actor
from .deadlines import calendar_data

router = APIRouter(prefix="/api/calendar", tags=["personal deadlines"])


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
    result = calendar_data(
        db,
        actor,
        month=month,
        tz=tz,
        view=view,
        day=day,
        cursor=cursor,
        limit=limit,
        stamp=now(),
    )
    ensure_current_actor(db, actor)
    return result
