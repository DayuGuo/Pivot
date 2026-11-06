"""Real PostgreSQL calendar projections preserve task, role and title boundaries."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from apps.api.publishing.domain import calendar as module
from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import Assignment, ManuscriptVersion, VersionAuthor
from apps.api.publishing.models import AuditEvent, now
from tests.api.test_global_search import formal
from tests.api.test_publishing_decisions import closed_round, decide, recommend
from tests.api.test_publishing_decisions import production as production
from tests.api.test_publishing_peer_review import accept, open_round, reviewer_selection
from tests.api.test_publishing_production import accepted

URL = "/api/calendar"
MONTH = "2032-03"
STAMP = datetime(2032, 3, 10, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def task(
    db,
    world,
    *,
    due=STAMP,
    role="editor",
    kind="precheck_completeness",
    title="测试期限定稿",
    journal=None,
):
    m, flow, version, _ = formal(db, world, title, stage=kind, assignee=None, journal=journal)
    if role != "author":
        db.add(
            Assignment(
                manuscript_id=m.id,
                journal_id=m.journal_id,
                user_id=world.users[role].id,
                capability=core.CAPABILITIES[kind],
            )
        )
    result = core.start_step(db, m, flow, kind, world.users[role].id, version_id=version.id)
    result.due_at = due
    db.flush()
    return m, flow, result


def calendar(client, **params):
    r = client.get(URL, params={"month": MONTH, **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_login(client):
    assert client.get(URL, params={"month": MONTH}).status_code == 401


@pytest.mark.parametrize(
    "params",
    [
        {"month": "2032-13"},
        {"month": "9999-12"},
        {"month": "2032-3"},
        {"tz": "Mars/Unknown"},
        {"tz": "posix/Europe/London"},
        {"tz": "localtime"},
        {"day": "2032-02-29"},
        {"day": "2032-03-32"},
        {"view": "overdue", "day": "2032-03-01"},
        {"view": "all"},
        {"limit": 0},
        {"limit": 51},
        {"cursor": "invalid"},
    ],
)
def test_invalid_inputs_are_safe(client, login, params):
    login()
    assert client.get(URL, params={"month": MONTH, **params}).status_code == 422


def test_month_day_dst_and_exact_boundaries(client, login, db, world):
    login()
    # Los Angeles starts DST on March 14, 2032. March local midnight is 08:00 UTC.
    before = datetime(2032, 3, 1, 7, 59, tzinfo=UTC)
    first = datetime(2032, 3, 1, 8, tzinfo=UTC)
    last = datetime(2032, 4, 1, 6, 59, tzinfo=UTC)
    after = datetime(2032, 4, 1, 7, tzinfo=UTC)
    for due in [before, first, last, after]:
        task(db, world, due=due)
    db.commit()
    r = calendar(client, tz="America/Los_Angeles")
    assert [i["due_at"] for i in r["items"]] == [first.isoformat(), last.isoformat()]
    assert r["days"] == [{"date": "2032-03-01", "count": 1}, {"date": "2032-03-31", "count": 1}]
    assert len(calendar(client, tz="America/Los_Angeles", day="2032-03-01")["items"]) == 1
    assert calendar(client, tz="America/Los_Angeles", day="2032-03-02")["items"] == []


def test_only_current_role_own_active_assigned_tasks(client, login, db, world):
    login()
    own, _, own_task = task(db, world)
    task(db, world, role="chief_editor", kind="chief_scope")
    task(db, world, journal=world.other_journal)
    _, _, undated = task(db, world, due=None)
    revoked, _, _ = task(db, world)
    assignment = db.scalar(select(Assignment).where(Assignment.manuscript_id == revoked.id))
    assignment.ends_at = now()
    _, stale_flow, _ = task(db, world)
    stale_flow.current_step_id = None
    _, _, wrong_role = task(db, world, role="chief_editor", kind="chief_scope")
    wrong_role.assignee_id = world.users["editor"].id
    db.commit()
    r = calendar(client)
    assert [x["id"] for x in r["items"]] == [own_task.id]
    assert r["counts"]["month"] == 1 and r["counts"]["undated"] == 1
    assert r["items"][0]["href"] == f"/publishing?manuscript={own.id}"
    assert undated.id not in {x["id"] for x in r["items"]}


def test_overdue_crosses_months_and_no_invented_deadlines(client, login, db, world, monkeypatch):
    monkeypatch.setattr(module, "now", lambda: STAMP)
    login()
    _, _, old = task(db, world, due=STAMP - timedelta(days=50))
    _, _, current = task(db, world, due=STAMP - timedelta(minutes=1))
    task(db, world, due=STAMP)
    task(db, world, due=None)
    db.commit()
    r = calendar(client, view="overdue")
    assert [x["id"] for x in r["items"]] == [old.id, current.id]
    assert r["counts"] == {"month": 2, "overdue": 2, "undated": 1}
    assert all(x["overdue"] for x in r["items"])


def test_stable_pagination_and_scope_bound_cursor(client, login, db, world):
    login()
    tasks = [task(db, world)[2] for _ in range(5)]
    db.commit()
    r = calendar(client, limit=2)
    seen = r["items"][:]
    cursor = r["next_cursor"]
    assert r["days"] == [{"date": "2032-03-10", "count": 5}]
    while cursor:
        page = calendar(client, limit=2, cursor=cursor)
        seen.extend(page["items"])
        cursor = page["next_cursor"]
    assert [x["id"] for x in seen] == sorted(t.id for t in tasks)
    assert len({x["id"] for x in seen}) == 5
    for extra in [{"view": "overdue"}, {"tz": "Europe/London"}, {"day": "2032-03-10"}]:
        assert (
            client.get(
                URL, params={"month": MONTH, "cursor": r["next_cursor"], **extra}
            ).status_code
            == 422
        )
    payload = json.loads(base64.urlsafe_b64decode(r["next_cursor"]))
    payload["id"] = {"bad": 1}
    invalid = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    assert client.get(URL, params={"month": MONTH, "cursor": invalid}).status_code == 422


def test_author_work_is_not_granted_by_editor_or_chief_role(client, login, db, world):
    m, _, t = task(db, world, role="author", kind="author_draft")
    db.commit()
    login("author")
    assert [x["id"] for x in calendar(client)["items"]] == [t.id]
    for role in ["editor", "chief_editor", "reviewer"]:
        login(role)
        assert m.id not in {x["manuscript_id"] for x in calendar(client)["items"]}


def test_real_review_invitation_uses_response_deadline_and_snapshot(client, login, world):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    login("reviewer")
    detail = client.get(f"/api/publishing/manuscripts/{mid}").json()
    invitation = detail["review"]["invitation"]
    r = calendar(client, month=invitation["response_due_at"][:7])
    own = next(x for x in r["items"] if x["manuscript_id"] == mid)
    assert own["kind"] == "respond_review_invitation"
    assert own["due_at"] == invitation["response_due_at"]
    assert own["title"] == invitation["title"]


def test_calendar_is_read_only_and_revalidates_session(client, login, db, world, monkeypatch):
    login()
    task(db, world)
    db.commit()
    before = db.scalar(select(func.count()).select_from(AuditEvent))
    statements = []

    def record(conn, cur, statement, parameters, context, many):
        statements.append(statement.strip().split()[0].upper())

    event.listen(db.get_bind(), "before_cursor_execute", record)
    try:
        calendar(client)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", record)
    assert not {"INSERT", "UPDATE", "DELETE"} & set(statements)
    assert before == db.scalar(select(func.count()).select_from(AuditEvent))
    original = module.ensure_current_actor
    calls = 0

    def deny_on_return(db, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            from fastapi import HTTPException

            raise HTTPException(401, "登录已失效")
        return original(db, actor)

    monkeypatch.setattr(module, "ensure_current_actor", deny_on_return)
    assert client.get(URL, params={"month": MONTH}).status_code == 401


def test_real_accepted_review_uses_report_deadline_and_revocation(client, login, db, world):
    mid = reviewer_selection(client, login, world)
    open_round(client, mid, world)
    detail = accept(client, login, mid)
    invitation = detail["review"]["invitation"]
    month = invitation["report_due_at"][:7]
    items = calendar(client, month=month)["items"]
    assert len(items) == 1 and items[0]["kind"] == "submit_review"
    assert items[0]["due_at"] == invitation["report_due_at"]
    assignment = db.scalar(
        select(Assignment).where(Assignment.review_invitation_id == invitation["id"])
    )
    assignment.ends_at = now()
    db.commit()
    assert calendar(client, month=month)["items"] == []


def test_real_author_revision_uses_confirmed_revision_deadline(client, login, world):
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    decide(client, login, mid)
    login("author")
    detail = client.get(f"/api/publishing/manuscripts/{mid}").json()
    request = detail["editorial"]["revision_request"]
    items = calendar(client, month=request["due_at"][:7])["items"]
    assert len(items) == 1 and items[0]["kind"] == "author_revision"
    assert items[0]["due_at"] == request["due_at"]


@pytest.mark.usefixtures("production")
def test_production_deadline_requires_actual_assignment(client, login, db, world):
    mid = accepted(client, login, world)
    row = db.scalar(
        select(core.WorkItem).where(
            core.WorkItem.manuscript_id == mid, core.WorkItem.kind == "production"
        )
    )
    assert [x["id"] for x in calendar(client, month=row.due_at.strftime("%Y-%m"))["items"]] == [
        row.id
    ]
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.manuscript_id == mid, Assignment.capability == "production"
        )
    )
    assignment.ends_at = now()
    db.commit()
    assert calendar(client, month=row.due_at.strftime("%Y-%m"))["items"] == []


def test_historical_author_conflict_hides_editor_deadline(client, login, db, world):
    login()
    m, flow, _ = task(db, world)
    historical = ManuscriptVersion(
        manuscript_id=m.id,
        version_no=2,
        title="合成历史署名草稿",
        created_by=world.users["author"].id,
    )
    db.add(historical)
    db.flush()
    db.add(
        VersionAuthor(
            manuscript_id=m.id,
            version_id=historical.id,
            ordinal=0,
            name="合成历史署名",
            linked_user_id=world.users["editor"].id,
            email=world.users["editor"].email,
        )
    )
    db.commit()
    assert calendar(client)["items"] == []
