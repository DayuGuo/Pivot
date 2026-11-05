"""Owner-governed package issuance, untrusted preview and explicit confirmed return."""

import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field
from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .claim_evaluation_package import package_projection
from .core import digest
from .dossier_actions import event, gateway
from .dossier_schemas import ExplicitTrue, RequestID
from .evaluation_access import latest_returns, load_package, receipt
from .evaluation_models import EvaluationPackage, EvaluationReturn
from .evaluation_protocol import InvalidReturn, assessments, disagreement, return_digest
from .evaluation_sources import evaluation_material
from .schemas import StrictInput

router = APIRouter(prefix="/api/dossiers", tags=["independent evaluation returns"])


class IssueInput(StrictInput):
    request_id: RequestID
    evaluator_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class IssueAction(IssueInput):
    answer_id: UUID


class PreviewInput(StrictInput):
    packet: dict[str, Any]


class ConfirmInput(PreviewInput):
    request_id: RequestID
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_return_id: RequestID | None
    acknowledged: ExplicitTrue
    acknowledged_claims: list[RequestID] = Field(min_length=1, max_length=12)


class ConfirmAction(ConfirmInput):
    package_id: UUID


def size_check(db, value, limit):
    if db.scalar(select(func.octet_length(cast(literal(value, type_=JSONB), Text)))) > limit:
        raise HTTPException(413, "评价材料过大，未保存；请使用较短的问题重新生成结论")


def parse(package, packet):
    try:
        return assessments(package.packet_json, packet)
    except (InvalidReturn, ValueError, TypeError, OverflowError, RecursionError) as error:
        message = str(error) if isinstance(error, InvalidReturn) else "评价文件格式不合法"
        raise HTTPException(422, message) from None


@router.post("/{dossier_id}/answers/{answer_id}/evaluations")
def issue(
    dossier_id: UUID,
    answer_id: UUID,
    body: IssueInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    def execute():
        row, item, _, source, entries, targets = evaluation_material(
            db, actor, dossier_id, answer_id
        )
        row = access.load(db, actor, str(dossier_id), write=True)
        if item.content_digest != body.content_digest:
            raise HTTPException(409, "评价目标版本摘要不匹配，请重新载入")
        existing = db.scalar(
            select(EvaluationPackage).where(
                EvaluationPackage.answer_id == str(answer_id),
                EvaluationPackage.evaluator_code == body.evaluator_code,
            )
        )
        if existing:
            raise HTTPException(409, "本回答已有该评价代号，请打开原评价包；不得重复登记增加票数")
        if (
            db.scalar(
                select(func.count())
                .select_from(EvaluationPackage)
                .where(EvaluationPackage.answer_id == str(answer_id))
            )
            >= 10
        ):
            raise HTTPException(409, "每个回答最多登记10个评价代号")
        ids = [str(uuid4()) for _ in entries]
        packet = package_projection(source, entries, claim_ids=ids)
        package_id = str(uuid4())
        packet.update(
            schema="claim-evaluation-package.v2",
            package_id=package_id,
            evaluator_code=body.evaluator_code,
        )
        packet["instructions"] = [x for x in packet["instructions"] if "暂不支持回传" not in x] + [
            "此包已登记；仅修改每条assessment。由资料负责人在独立页核对后回传，评价代号不是身份认证。"
        ]
        mapping = dict(zip(ids, targets, strict=True))
        size_check(db, packet, 2097152)
        size_check(db, mapping, 262144)
        package = EvaluationPackage(
            id=package_id,
            answer_id=str(answer_id),
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_id=item.id,
            content_digest=item.content_digest,
            evaluator_code=body.evaluator_code,
            packet_json=packet,
            claim_map=mapping,
            packet_digest=digest(packet),
            created_by=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(package)
        db.flush()
        event(db, actor, row, "evaluation_issued", item.id, evidence_id=package.id)
        return {"id": package.id, "version_id": item.id, "packet_digest": package.packet_digest}

    action = IssueAction(**body.model_dump(), answer_id=answer_id)
    return gateway(
        db,
        actor,
        action,
        "evaluation_issue",
        str(dossier_id),
        execute,
        revalidate_resource=lambda: evaluation_material(db, actor, dossier_id, answer_id),
    )


@router.get("/{dossier_id}/answers/{answer_id}/evaluations")
def overview(
    dossier_id: UUID,
    answer_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    _, item, _, _, _, _ = evaluation_material(db, actor, dossier_id, answer_id)
    packages = db.scalars(
        select(EvaluationPackage)
        .where(EvaluationPackage.answer_id == str(answer_id))
        .order_by(EvaluationPackage.evaluator_code)
        .limit(10)
    ).all()
    latest = latest_returns(db, packages)
    return {
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "packages": [
            {
                "id": p.id,
                "evaluator_code": p.evaluator_code,
                "latest": receipt(latest[p.id]) if p.id in latest else None,
            }
            for p in packages
        ],
        "summary": disagreement(packages, latest),
    }


@router.get("/{dossier_id}/evaluations/{package_id}")
def detail(
    dossier_id: UUID,
    package_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row, item, p = load_package(db, actor, dossier_id, package_id)
    latest = latest_returns(db, [p]).get(p.id)
    return {
        "id": p.id,
        "answer_id": p.answer_id,
        "evaluator_code": p.evaluator_code,
        "version_id": p.version_id,
        "version_no": item.version_no,
        "is_current": row.current_version_id == item.id,
        "packet_digest": p.packet_digest,
        "packet": p.packet_json,
        "latest": receipt(latest) if latest else None,
    }


@router.get("/{dossier_id}/evaluations/{package_id}/file")
def download(
    dossier_id: UUID,
    package_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row, _, p = load_package(db, actor, dossier_id, package_id)
    access.load(db, actor, row.id)
    return Response(
        json.dumps(p.packet_json, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="pivot-evaluation-{p.id}.json"',
        },
    )


@router.post("/{dossier_id}/evaluations/{package_id}/preview")
def preview(
    dossier_id: UUID,
    package_id: UUID,
    body: PreviewInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    _, _, p = load_package(db, actor, dossier_id, package_id)
    values = parse(p, body.packet)
    return {
        "digest": return_digest(p, values),
        "assessments": values,
        "answered": sum(v["verdict"] is not None for v in values.values()),
        "unanswered": sum(v["verdict"] is None for v in values.values()),
    }


@router.post("/{dossier_id}/evaluations/{package_id}/confirm")
def confirm(
    dossier_id: UUID,
    package_id: UUID,
    body: ConfirmInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    def validate(write=False):
        row, item, p = load_package(db, actor, dossier_id, package_id, write=write)
        values = parse(p, body.packet)
        ids = [str(value) for value in body.acknowledged_claims]
        if len(ids) != len(set(ids)) or set(ids) != set(p.claim_map):
            raise HTTPException(422, "请逐条核对全部结论及未评价状态")
        if return_digest(p, values) != body.preview_digest:
            raise HTTPException(409, "评价内容与预览摘要不一致，请重新核对")
        return row, item, p, values

    def execute():
        row, item, p, values = validate(write=True)
        latest = latest_returns(db, [p]).get(p.id)
        if (latest.id if latest else None) != (
            str(body.expected_return_id) if body.expected_return_id else None
        ):
            raise HTTPException(409, "已有新的确认回传，请重新载入并逐条核对")
        size_check(db, values, 131072)
        result = EvaluationReturn(
            package_id=p.id,
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_id=item.id,
            content_digest=item.content_digest,
            packet_digest=p.packet_digest,
            assessments_json=values,
            digest=body.preview_digest,
            return_no=latest.return_no + 1 if latest else 1,
            submitted_by=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(result)
        db.flush()
        event(db, actor, row, "evaluation_returned", item.id, evidence_id=result.id)
        return receipt(result)

    action = ConfirmAction(**body.model_dump(), package_id=package_id)
    return gateway(
        db,
        actor,
        action,
        "evaluation_return",
        str(dossier_id),
        execute,
        revalidate_resource=validate,
    )


@router.get("/{dossier_id}/evaluations/{package_id}/returns")
def history(
    dossier_id: UUID,
    package_id: UUID,
    before: int | None = Query(None, ge=1),
    limit: int = Query(10, ge=1, le=50),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    _, _, p = load_package(db, actor, dossier_id, package_id)
    stmt = (
        select(EvaluationReturn)
        .where(EvaluationReturn.package_id == p.id)
        .order_by(EvaluationReturn.return_no.desc())
    )
    rows = db.scalars(
        (stmt.where(EvaluationReturn.return_no < before) if before else stmt).limit(limit + 1)
    ).all()
    return {
        "items": [receipt(r) | {"assessments": r.assessments_json} for r in rows[:limit]],
        "next_cursor": rows[limit - 1].return_no if len(rows) > limit else None,
    }
