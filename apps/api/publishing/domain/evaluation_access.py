"""Registered package access and frozen binding verification, independent of HTTP routes."""

from fastapi import HTTPException
from sqlalchemy import select

from .core import digest
from .evaluation_models import EvaluationPackage, EvaluationReturn
from .evaluation_sources import evaluation_material


def load_package(db, actor, dossier_id, package_id, *, write=False):
    package = db.get(EvaluationPackage, str(package_id))
    if (
        not package
        or package.dossier_id != str(dossier_id)
        or package.journal_id != actor.journal_id
    ):
        raise HTTPException(404, "评价包不存在或无权访问")
    row, item, answer, source, entries, targets = evaluation_material(
        db, actor, dossier_id, package.answer_id
    )
    if write:
        from .dossier_access import load

        row = load(db, actor, str(dossier_id), write=True)
    if (
        item.id != package.version_id
        or item.content_digest != package.content_digest
        or digest(package.packet_json) != package.packet_digest
        or package.packet_json["source"] != source
    ):
        raise HTTPException(409, "评价包与历史版本来源不一致")
    expected = {(t["bucket"], t["index"]): (e, t) for e, t in zip(entries, targets, strict=True)}
    if len(expected) != len(package.claim_map) or len(package.packet_json["claims"]) != len(
        expected
    ):
        raise HTTPException(409, "评价包的结论集合不一致")
    seen = set()
    for entry in package.packet_json["claims"]:
        target = package.claim_map.get(entry["id"], {})
        key = (target.get("bucket"), target.get("index"))
        match = expected.get(key)
        if (
            not match
            or key in seen
            or target != match[1]
            or {"text": entry["text"], "citations": entry["citations"]} != match[0]
        ):
            raise HTTPException(409, "评价包的原文引用不一致")
        seen.add(key)
    return row, item, package


def latest_returns(db, packages):
    ids = [p.id for p in packages]
    if not ids:
        return {}
    rows = db.scalars(
        select(EvaluationReturn)
        .where(EvaluationReturn.package_id.in_(ids))
        .distinct(EvaluationReturn.package_id)
        .order_by(EvaluationReturn.package_id, EvaluationReturn.return_no.desc())
    ).all()
    return {r.package_id: r for r in rows}


def receipt(row):
    return {
        "id": row.id,
        "package_id": row.package_id,
        "return_no": row.return_no,
        "digest": row.digest,
        "version_id": row.version_id,
        "created_at": row.created_at.isoformat(),
        "submitted_by": row.submitted_by,
    }
