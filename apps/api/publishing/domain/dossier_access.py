"""Object/role authorization and content-addressed version reads; no HTTP routes."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..security import Actor
from .core import digest, ensure_actor
from .dossier_models import Dossier, DossierVersion
from .files import FileValidationError, read_bytes
from .models import FileObject


def require_staff(db: Session, actor: Actor):
    ensure_actor(db, actor)
    if actor.role not in {"editor", "chief_editor"}:
        raise HTTPException(403, "仅编辑或主编可录入内部审阅资料")


def load(db: Session, actor: Actor, dossier_id: str, *, write=False) -> Dossier:
    ensure_actor(db, actor)
    query = select(Dossier).where(
        Dossier.id == dossier_id,
        Dossier.journal_id == actor.journal_id,
        Dossier.created_by == actor.user.id,
    )
    if write:
        query = query.with_for_update()
    row = db.scalar(query.execution_options(populate_existing=True))
    ensure_actor(db, actor)
    if row is None or actor.role not in {"editor", "chief_editor"}:
        raise HTTPException(404, "资料包不存在或无权访问")
    return row


def version(db: Session, row: Dossier, version_id: str | None = None) -> DossierVersion:
    result = db.scalar(
        select(DossierVersion).where(
            DossierVersion.id == (version_id or row.current_version_id),
            DossierVersion.dossier_id == row.id,
            DossierVersion.journal_id == row.journal_id,
        )
    )
    if result is None:
        raise HTTPException(404, "资料版本不存在或无权访问")
    return result


def current(row: Dossier, expected: int, version_id: str | None = None):
    if row.revision != expected or (version_id and row.current_version_id != version_id):
        raise HTTPException(409, "资料已更新，请重新载入并核对当前版本")


def file_content(db: Session, item: DossierVersion):
    if not item.file_object_id:
        return None
    blob = db.scalar(
        select(FileObject).where(
            FileObject.id == item.file_object_id, FileObject.journal_id == item.journal_id
        )
    )
    if not blob:
        raise HTTPException(409, "当前文件不可读取，请重新上传")
    try:
        raw = read_bytes(blob.storage_key)
    except FileValidationError:
        raise HTTPException(409, "文件完整性检查失败，请重新上传后核对") from None
    if len(raw) != blob.byte_size or hashlib.sha256(raw).hexdigest() != blob.sha256:
        raise HTTPException(409, "文件完整性检查失败，请重新上传后核对")
    return blob, raw


def snapshot_digest(data: dict, blob_hash: str | None, filename: str | None, media: str | None):
    return digest(
        {
            "schema": "internal_dossier.v1",
            "data": data,
            "file_sha256": blob_hash,
            "filename": filename,
            "media_type": media,
        }
    )
