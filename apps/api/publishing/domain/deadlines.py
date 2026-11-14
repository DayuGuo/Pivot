"""Shared read-only calendar and conversation facts; no route-to-route calls."""

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, tuple_

from ..models import now
from . import core
from .calendar_queries import personal_task_statement

TIMEZONES = frozenset(available_timezones()) - {"localtime"}
PERIODS = {"today", "week", "overdue", "undated", "all"}
TIMEZONE_ERROR = "当前时区不可用，请选择使用UTC后重新发送。"


def timezone_name(value):
    if value not in TIMEZONES:
        raise ValueError("请选择有效的IANA时区；需要时请明确使用UTC")
    return value


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


def calendar_data(db, actor, *, month, tz, view, day, cursor, limit, stamp):
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


def requested_period(text):
    """Narrow shortcuts for factual requests; all other requests retain the model path."""
    if re.fullmatch(
        r"\s*(?:继续(?:查看|查询)?(?:我的)?待办|下一页待办|more tasks)[。？！.!?\s]*", text, re.I
    ):
        return "continue"
    if not re.search(
        r"待办|任务|截止|到期|处理|做什么|做些什么|干嘛|tasks?|deadlines?|due", text, re.I
    ):
        return None
    matched = [
        period
        for period, pattern in [
            (
                "undated",
                r"未设|没有.{0,6}(?:日期|期限|截止时间)|无截止|undated|no (?:due date|deadline)",
            ),
            ("overdue", r"逾期|过期|overdue"),
            ("week", r"本周|这周|this week"),
            ("today", r"今天|今日|today"),
        ]
        if re.search(pattern, text, re.I)
    ]
    if len(matched) > 1:
        raise HTTPException(422, "请一次查询一个范围：今天到期、本周到期、全部逾期或未设日期。")
    if matched:
        return matched[0]
    if re.search(r"明天|后天|下周|下个月|tomorrow|next week|\d{4}[-/]\d", text, re.I):
        raise HTTPException(
            422, "目前支持今天、本周、逾期、未设日期或全部待办，请选择其中一个范围。"
        )
    if re.search(
        r"待办|(?:哪些|什么|我的|所有|全部).{0,5}任务|all (?:my )?tasks|why.{0,30}(?:task|work)|截止|到期|期限|deadline|due",
        text,
        re.I,
    ):
        return "all"
    return None


def ungrounded_task_claim(text):
    """Reject obvious free-text task/date claims when a provider skips factual reads.

    This is a conservative guard, not a proof of arbitrary natural-language semantics.
    """
    task_words = r"待办|任务|task"
    return bool(
        re.search(rf"(?:{task_words}).{{0,40}}(?:截止|到期|逾期|deadline|due)", text, re.I)
        or re.search(
            rf"(?:\d+|[一二两三四五六七八九十百]+)\s*(?:项|个)?\s*(?:{task_words})", text, re.I
        )
        or re.search(rf"(?:{task_words}).{{0,8}}\d+\s*(?:项|个)", text, re.I)
        or re.search(rf"(?:没有|暂无|no pending).{{0,8}}(?:{task_words})", text, re.I)
        or re.search(
            r"(?:截止日期|截止时间|到期时间|deadline|due date).{0,30}(?:\d{4}|今天|明天|下周|today|tomorrow)",
            text,
            re.I,
        )
    )


def _work_position(cursor, scope):
    try:
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if set(value) != {"scope", "due", "id"} or value["scope"] != scope:
            raise ValueError
        identifier = str(UUID(value["id"]))
        due = datetime.fromisoformat(value["due"]) if value["due"] else None
        if due and (due.tzinfo is None or due.utcoffset() is None):
            raise ValueError
        return due, identifier
    except (ValueError, TypeError, KeyError, binascii.Error, OverflowError):
        raise HTTPException(422, "待办分页已失效，请重新查询") from None


def read_work(db, actor, *, period, timezone, manuscript_id=None, read_at=None, cursor=None):
    """Read a bounded task snapshot; classification time never grants past authority."""
    if period not in PERIODS:
        raise HTTPException(422, "请选择支持的待办范围")
    if timezone not in TIMEZONES:
        raise HTTPException(422, TIMEZONE_ERROR)
    try:
        timezone_name(timezone)
        stamp = datetime.fromisoformat(read_at) if read_at else now()
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError
        zone = ZoneInfo(timezone)
        local = stamp.astimezone(zone).date()
        start = local - timedelta(days=local.weekday()) if period == "week" else local
        end = start + timedelta(days=7 if period == "week" else 1)
        lower = datetime.combine(start, time.min, zone).astimezone(UTC)
        upper = datetime.combine(end, time.min, zone).astimezone(UTC)
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError):
        raise HTTPException(422, "请选择有效日期和时区") from None
    # Always check *current* assignments, even when continuing a historical read time.
    source = personal_task_statement(actor, now()).subquery()
    condition = {
        "today": and_(source.c.due_at >= lower, source.c.due_at < upper),
        "week": and_(source.c.due_at >= lower, source.c.due_at < upper),
        "overdue": source.c.due_at < stamp,
        "undated": source.c.due_at.is_(None),
        "all": True,
    }[period]
    if manuscript_id:
        condition = and_(condition, source.c.manuscript_id == manuscript_id)
    query_scope = [
        actor.journal_id,
        actor.user.id,
        actor.role,
        period,
        timezone,
        manuscript_id,
        stamp.isoformat(),
    ]
    scope = hashlib.sha256(json.dumps(query_scope).encode()).hexdigest()
    total = db.scalar(select(func.count()).select_from(source).where(condition))
    query = select(source).where(condition)
    if cursor:
        due, identifier = _work_position(cursor, scope)
        query = query.where(
            and_(source.c.due_at.is_(None), source.c.id > identifier)
            if due is None
            else or_(
                source.c.due_at.is_(None), tuple_(source.c.due_at, source.c.id) > (due, identifier)
            )
        )
    rows = db.execute(
        query.order_by(source.c.due_at.asc().nulls_last(), source.c.id).limit(13)
    ).all()
    labels = {"respond_review_invitation": "回应审稿邀请", "submit_review": "提交审稿报告"}
    items = [
        {
            "id": row.id,
            "manuscript_id": row.manuscript_id,
            "number": row.number,
            "title": row.title,
            "kind": row.kind,
            "status": row.status,
            "label": labels.get(row.kind, core.STAGE_LABELS.get(row.kind, row.kind)),
            "stage": row.stage,
            "workflow_revision": row.workflow_revision,
            "due_at": row.due_at.isoformat() if row.due_at else None,
            "overdue": row.due_at is not None and row.due_at < stamp,
            "href": "/publishing?manuscript=" + quote(row.manuscript_id, safe=""),
        }
        for row in rows[:12]
    ]
    next_cursor = None
    if len(rows) > 12:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "due": last["due_at"], "id": last["id"]}).encode()
        ).decode()
    return {
        "schema": "personal-work.v1",
        "period": period,
        "timezone": timezone,
        "manuscript_id": manuscript_id,
        "read_at": stamp.isoformat(),
        "retrieved_at": now().isoformat(),
        "range_start": lower.isoformat() if period in {"today", "week"} else None,
        "range_end": upper.isoformat() if period in {"today", "week"} else None,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "total": total,
        "items": items,
        "role": actor.role,
        "source": "work_items",
    }


def require_snapshot_access(db, actor, snapshot):
    """History/replays cannot resurrect responsibility revoked since the original read."""
    if snapshot["role"] != actor.role:
        raise HTTPException(403, "待办身份已变化，请重新查询")
    ids = {item["id"] for item in snapshot["items"]}
    if ids:
        source = personal_task_statement(actor, now()).subquery()
        visible = set(db.scalars(select(source.c.id).where(source.c.id.in_(ids))))
        if visible != ids:
            raise HTTPException(403, "待办职责已变化，请重新查询")


def work_reply(snapshot, *, explain=False):
    """All dates, totals and task links come from code, never model assertions."""
    labels = {
        "today": "今天到期",
        "week": "本周到期",
        "overdue": "已逾期",
        "undated": "未设截止日期",
        "all": "全部本人待办",
    }
    zone = ZoneInfo(snapshot["timezone"])
    stamp = datetime.fromisoformat(snapshot["read_at"])
    paged = bool(snapshot["cursor"] or snapshot["next_cursor"])
    lines = [
        f"{labels[snapshot['period']]}：{snapshot['total']} 项。"
        + (f"本批 {len(snapshot['items'])} 项。" if paged else "")
    ]
    if snapshot["range_start"]:
        start = datetime.fromisoformat(snapshot["range_start"]).astimezone(zone).date()
        end = datetime.fromisoformat(snapshot["range_end"]).astimezone(zone).date()
        lines.append(f"日期范围：{start} 至 {end}（不含结束日）。")
    retrieved = datetime.fromisoformat(snapshot["retrieved_at"])
    timing = (
        f"日期基准 {stamp.astimezone(zone).isoformat(timespec='seconds')}；"
        if snapshot["cursor"]
        else ""
    ) + f"读取于 {retrieved.astimezone(zone).isoformat(timespec='seconds')}"
    lines.append(
        f"{snapshot['timezone']} · {timing}；仅限当前身份"
        + ("、当前稿件。" if snapshot["manuscript_id"] else "。")
    )
    for item in snapshot["items"]:
        due = (
            datetime.fromisoformat(item["due_at"]).astimezone(zone).isoformat(timespec="minutes")
            if item["due_at"]
            else "未设截止日期"
        )
        lines.append(
            f"• {item['number']} · {item['title']}：{item['label']}；{due}"
            + ("，已逾期" if item["overdue"] else "")
            + "。"
        )
    if snapshot["period"] in {"today", "week"}:
        lines.append("此列表仅含该日期范围内到期的任务；更早的逾期和未设期限任务可分别查询。")
    if snapshot["next_cursor"]:
        lines.append("还有下一批，可输入“继续查看待办”；继续时重新读取，列表可能变化。")
    if explain:
        lines.append("这些任务来自当前身份的有效分派或本人审稿邀请。")
    lines.append("处理前请打开稿件核对最新状态。")
    return {
        "content": "\n".join(lines),
        "references": [
            {"manuscript_id": x["manuscript_id"], "label": x["number"] + " · " + x["label"]}
            for x in snapshot["items"]
        ],
        "work_snapshot": snapshot,
    }
