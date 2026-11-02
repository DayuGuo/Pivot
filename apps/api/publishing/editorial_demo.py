"""Deterministic action gateway for private synthetic editorial workspace drafts.

These tables never update manuscripts, tasks, email drafts, or workflow decisions.
The fixture is read-only; all mutable fields are typed, scoped, and audited here.
"""

import hashlib
import re
from copy import deepcopy
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from packages.editorial_demo import load_cases

from .audit import record
from .db import get_db
from .models import Base, now, uid
from .policy import EDITOR_ROLES
from .security import Actor, get_actor

router = APIRouter(prefix="/api/editorial-demo", tags=["synthetic editorial workspace"])


class DemoWorkspaceState(Base):
    __tablename__ = "editorial_demo_states"
    __table_args__ = (UniqueConstraint("user_id", "journal_id", "case_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    case_id: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DemoSavedViews(Base):
    __tablename__ = "editorial_demo_views"
    __table_args__ = (UniqueConstraint("user_id", "journal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    journal_id: Mapped[str] = mapped_column(ForeignKey("journals.id"))
    content: Mapped[list] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


Identifier = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
]
Note = Annotated[str, StringConstraints(strict=True, max_length=10000)]
IssueStatus = Literal["unanswered", "unverified", "resolved", "ignored"]


class TypedInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Invitation(TypedInput):
    to: str = Field(max_length=254)
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20000)
    due: str = Field(max_length=10)

    @model_validator(mode="after")
    def validate_draft(self):
        # Even private synthetic invitation drafts cannot contain a real recipient.
        if self.to and any(
            not re.fullmatch(
                r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.test", recipient.strip()
            )
            for recipient in self.to.split(",")
        ):
            raise ValueError("仅允许 .test 合成收件人")
        if self.due:
            date.fromisoformat(self.due)
        return self


class Decision(TypedInput):
    outcome: Literal["", "accept", "minor_revision", "major_revision", "reject"]
    body: str = Field(max_length=20000)


class Reading(TypedInput):
    version: Identifier
    section: Identifier
    paragraph: int = Field(default=0, ge=0, le=10000)


class AIResult(TypedInput):
    id: Identifier
    issue_id: Identifier
    status: Literal["pending", "adopted", "ignored"]
    text: str = Field(min_length=1, max_length=6000)
    version: Identifier


class CaseState(TypedInput):
    revision: int = Field(ge=0)
    selected_reviewers: list[Identifier] = Field(max_length=12)
    issue_statuses: dict[Identifier, IssueStatus] = Field(max_length=100)
    notes: str = Field(max_length=12000)
    version_notes: dict[Identifier, Note] = Field(default_factory=dict, max_length=10)
    invitation: Invitation
    decision: Decision
    reading: Reading
    ai_results: list[AIResult] = Field(max_length=30)


class StatePatch(TypedInput):
    selected_reviewers: list[Identifier] | None = Field(default=None, max_length=12)
    issue_statuses: dict[Identifier, IssueStatus] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=12000)
    version_notes: dict[Identifier, Note] | None = Field(default=None, max_length=10)
    invitation: Invitation | None = None
    decision: Decision | None = None
    reading: Reading | None = None
    ai_results: list[AIResult] | None = Field(default=None, max_length=30)

    @model_validator(mode="before")
    @classmethod
    def reject_empty_or_null(cls, value):
        if isinstance(value, dict) and (not value or any(v is None for v in value.values())):
            raise ValueError("更新必须包含合法的非空字段")
        return value


class PatchInput(TypedInput):
    expected_revision: int = Field(ge=0, le=2147483646)
    patch: StatePatch


class ViewState(TypedInput):
    query: str = Field(max_length=200)
    stage: Literal[
        "all", "screening", "assignment", "reviewers", "review", "decision", "production"
    ]
    sort: Literal["due", "priority", "updated", "title"]
    name: str | None = Field(default=None, min_length=1, max_length=60)
    today_only: bool | None = None


class ViewsInput(TypedInput):
    views: list[ViewState] = Field(max_length=12)


def editor(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role not in EDITOR_ROLES:
        raise HTTPException(403, "只有编辑或主编可以访问合成编辑工作台")
    return actor


def case_record(case_id: str) -> dict:
    item = next((c for c in load_cases() if c["id"] == case_id), None)
    if not item:
        raise HTTPException(404, "合成稿件不存在")
    return item


def default_state(case: dict) -> dict:
    version = case["versions"][-1]
    return CaseState(
        revision=0,
        selected_reviewers=[],
        issue_statuses={i["id"]: i["initial_status"] for i in case["issues"]},
        notes="",
        version_notes={},
        invitation=Invitation(to="", subject="", body="", due=""),
        decision=Decision(outcome="", body=""),
        reading=Reading(version=version["id"], section=version["sections"][0]["id"]),
        ai_results=[],
    ).model_dump()


def lock_workspace(db: Session, actor: Actor, scope: str) -> None:
    # Covers first insert as well as later writes, across API worker processes.
    key = f"editorial-demo:{actor.user.id}:{actor.journal_id}:{scope}"
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})


def state_query(actor: Actor, case_id: str):
    return select(DemoWorkspaceState).where(
        DemoWorkspaceState.user_id == actor.user.id,
        DemoWorkspaceState.journal_id == actor.journal_id,
        DemoWorkspaceState.case_id == case_id,
    )


def views_query(actor: Actor):
    return select(DemoSavedViews).where(
        DemoSavedViews.user_id == actor.user.id,
        DemoSavedViews.journal_id == actor.journal_id,
    )


@router.get("")
def dataset(actor: Actor = Depends(editor), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DemoWorkspaceState).where(
            DemoWorkspaceState.user_id == actor.user.id,
            DemoWorkspaceState.journal_id == actor.journal_id,
        )
    ).all()
    saved = {r.case_id: {**r.content, "revision": r.revision} for r in rows}
    views = db.scalar(views_query(actor))
    return {
        "demo": True,
        "cases": load_cases(),
        "states": {c["id"]: saved.get(c["id"], default_state(c)) for c in load_cases()},
        "saved_views": views.content if views else [],
    }


def validated_state(case: dict, current: dict, patch: StatePatch) -> dict:
    merged = {**deepcopy(current), **patch.model_dump(exclude_unset=True)}
    versions = {v["id"]: v for v in case["versions"]}
    reading = merged["reading"]
    if reading["version"] not in versions or reading["section"] not in {
        s["id"] for s in versions.get(reading["version"], {}).get("sections", [])
    }:
        raise HTTPException(422, "阅读版本或章节不存在")
    section = next(
        item
        for item in versions[reading["version"]]["sections"]
        if item["id"] == reading["section"]
    )
    if reading.get("paragraph", 0) >= len(section["paragraphs"]):
        raise HTTPException(422, "阅读段落不存在")
    if not set(merged["version_notes"]).issubset(versions):
        raise HTTPException(422, "批注版本不存在")
    selected = merged["selected_reviewers"]
    if len(selected) != len(set(selected)) or not set(selected).issubset(
        {c["id"] for c in case["candidates"]}
    ):
        raise HTTPException(422, "候选审稿人不存在或重复")
    issues = {i["id"] for i in case["issues"]}
    if not set(merged["issue_statuses"]).issubset(issues):
        raise HTTPException(422, "问题不存在")
    # Reading another immutable version is navigation, not a content mutation.
    # Keep judgments/results bound to their original issue/version; UI filters context.
    existing_results = {item["id"]: item for item in current["ai_results"]}
    result_ids = set()
    for result in merged["ai_results"]:
        issue = next((item for item in case["issues"] if item["id"] == result["issue_id"]), None)
        if not issue or result["version"] not in {
            issue["before"]["version"],
            issue["after"]["version"],
        }:
            raise HTTPException(422, "模型结果必须绑定当前阅读版本及有效问题")
        if result["version"] != reading["version"] and result != existing_results.get(result["id"]):
            raise HTTPException(422, "新模型结果只能写入当前阅读版本")
        if result["id"] in result_ids:
            raise HTTPException(422, "模型结果标识重复")
        result_ids.add(result["id"])
    return CaseState.model_validate(merged).model_dump()


@router.patch("/cases/{case_id}/state")
def save_state(
    case_id: str,
    body: PatchInput,
    actor: Actor = Depends(editor),
    db: Session = Depends(get_db),
):
    case = case_record(case_id)
    lock_workspace(db, actor, case_id)
    row = db.scalar(state_query(actor, case_id).with_for_update())
    current = {**row.content, "revision": row.revision} if row else default_state(case)
    if body.expected_revision != current["revision"]:
        raise HTTPException(409, "此工作区已更新，请重新载入后保存")
    content = validated_state(case, current, body.patch)
    content["revision"] += 1
    if not row:
        row = DemoWorkspaceState(
            user_id=actor.user.id, journal_id=actor.journal_id, case_id=case_id, content={}
        )
        db.add(row)
    row.revision = content["revision"]
    row.content = {k: v for k, v in content.items() if k != "revision"}
    row.updated_at = now()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="editorial_demo.workspace_saved",
        entity_id=case_id,
        details={
            "demo": True,
            "revision": row.revision,
            "fields": sorted(body.patch.model_fields_set),
        },
    )
    db.commit()
    return content


@router.put("/views")
def save_views(body: ViewsInput, actor: Actor = Depends(editor), db: Session = Depends(get_db)):
    views = [v.model_dump(exclude_none=True) for v in body.views]
    names = [v["name"].strip() for v in views if "name" in v]
    if any(not n for n in names) or len(names) != len(set(names)):
        raise HTTPException(422, "视图名称不能为空或重复")
    lock_workspace(db, actor, "views")
    row = db.scalar(views_query(actor).with_for_update())
    if not row:
        row = DemoSavedViews(user_id=actor.user.id, journal_id=actor.journal_id, content=views)
        db.add(row)
    row.content = views
    row.updated_at = now()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="editorial_demo.views_saved",
        details={"demo": True, "count": len(views)},
    )
    db.commit()
    return {"saved_views": views}


@router.get("/cases/{case_id}/files/{attachment_id}")
def original_file(case_id: str, attachment_id: str, actor: Actor = Depends(editor)):
    case = case_record(case_id)
    attachment = next((a for a in case["attachments"] if a["id"] == attachment_id), None)
    if not attachment:
        raise HTTPException(404, "合成附件不存在")
    return Response(
        content=attachment["content"],
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{attachment["name"]}"'},
    )
