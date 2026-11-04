"""Shared exact-version authorization and CAS checks; no routes or model calls."""

from fastapi import HTTPException

from . import dossier_access as access
from .document_sources import source_projection
from .dossier_chat_models import DossierAnswer


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
