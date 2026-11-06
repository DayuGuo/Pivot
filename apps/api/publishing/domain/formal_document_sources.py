"""Verified original/selected-text provenance. No routes or model calls."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import select

from . import core
from .document_store import read_original
from .files import FileValidationError, read_bytes
from .formal_document_models import FormalDocumentBinding, FormalDocumentImport
from .models import FileObject, ManuscriptVersion


def import_digest(item):
    return core.digest(
        {
            k: getattr(item, k)
            for k in [
                "manuscript_id",
                "journal_id",
                "version_id",
                "base_revision",
                "purpose",
                "filename",
                "media_type",
                "byte_size",
                "sha256",
                "storage_key",
                "extraction_json",
                "source_kind",
                "source_note",
                "created_by",
            ]
        }
    )


def binding_digest(binding, item):
    return core.digest(
        {
            "import_digest": item.digest,
            **{
                k: getattr(binding, k)
                for k in [
                    "file_id",
                    "manuscript_id",
                    "journal_id",
                    "version_id",
                    "file_object_id",
                    "kind",
                    "parent_id",
                    "confirmed_by",
                    "session_hash",
                    "selection_start",
                    "selection_end",
                ]
            },
        }
    )


def verify_import(item):
    try:
        raw = read_original(item.storage_key)
    except FileValidationError:
        raise HTTPException(409, "原文件完整性检查失败") from None
    extraction = item.extraction_json
    if (
        len(raw) != item.byte_size
        or hashlib.sha256(raw).hexdigest() != item.sha256
        or import_digest(item) != item.digest
        or hashlib.sha256(extraction["text"].encode()).hexdigest() != extraction["sha256"]
    ):
        raise HTTPException(409, "导入原件或提取快照已变化")
    cursor = 0
    for i, s in enumerate(extraction["segments"]):
        if (
            s["start"] != cursor
            or s["end"] <= cursor
            or extraction["text"][cursor : s["end"]] != s["text"]
            or s["number"] != i + 1
            or (
                i + 1 < len(extraction["segments"])
                and extraction["text"][s["end"] : s["end"] + 2] != "\n\n"
            )
        ):
            raise HTTPException(409, "原文位置映射不完整")
        cursor = s["end"] + (2 if i + 1 < len(extraction["segments"]) else 0)
    if cursor != len(extraction["text"]):
        raise HTTPException(409, "提取全文未完整覆盖")
    return raw


def selected_text(item, first, last):
    segments = item.extraction_json["segments"]
    if not 1 <= first <= last <= len(segments):
        raise HTTPException(422, "请指定有效的正文起止页码或段落")
    start, end = segments[first - 1]["start"], segments[last - 1]["end"]
    return start, end, item.extraction_json["text"][start:end]


def verify_binding(db, binding):
    item = db.get(FormalDocumentImport, binding.import_id)
    if (
        not item
        or item.manuscript_id != binding.manuscript_id
        or item.journal_id != binding.journal_id
    ):
        raise HTTPException(409, "正式文件来源归属不一致")
    verify_import(item)
    if binding_digest(binding, item) != binding.digest:
        raise HTTPException(409, "原文绑定摘要不一致")
    ancestor = binding
    seen = set()
    for _ in range(64):
        if ancestor.id in seen or binding_digest(ancestor, item) != ancestor.digest:
            raise HTTPException(409, "原件继承链摘要不一致")
        seen.add(ancestor.id)
        if ancestor.kind == "confirmed":
            break
        parent = db.get(FormalDocumentBinding, ancestor.parent_id)
        if (
            not parent
            or parent.import_id != item.id
            or parent.file_object_id != binding.file_object_id
            or (parent.selection_start, parent.selection_end)
            != (binding.selection_start, binding.selection_end)
        ):
            raise HTTPException(409, "继承的原文件范围不一致")
        ancestor = parent
    else:
        raise HTTPException(409, "原件继承链超出本次可校验范围")
    blob = db.get(FileObject, binding.file_object_id)
    text = item.extraction_json["text"][binding.selection_start : binding.selection_end]
    try:
        raw = read_bytes(blob.storage_key)
    except (FileValidationError, AttributeError):
        raise HTTPException(409, "提取文件完整性检查失败") from None
    if (
        blob.journal_id != binding.journal_id
        or raw != text.encode()
        or blob.sha256 != hashlib.sha256(raw).hexdigest()
        or blob.byte_size != len(raw)
    ):
        raise HTTPException(409, "已确认原文与正式文件不一致")
    return item


def binding_for(db, link):
    binding = db.scalar(
        select(FormalDocumentBinding).where(FormalDocumentBinding.file_id == link.id)
    )
    if binding and (
        binding.version_id != link.version_id
        or binding.manuscript_id != link.manuscript_id
        or binding.journal_id != link.journal_id
        or binding.file_object_id != link.file_object_id
    ):
        raise HTTPException(409, "正式版本文件与原件关联不一致")
    return binding


def origin_for(db, link):
    binding = binding_for(db, link)
    if not binding:
        return None
    item = verify_binding(db, binding)
    return {
        "binding_id": binding.id,
        "digest": binding.digest,
        "filename": item.filename,
        "sha256": item.sha256,
        "media_type": item.media_type,
        "selection_start": binding.selection_start,
        "selection_end": binding.selection_end,
        "segments": item.extraction_json["segments"],
        "source_kind": item.source_kind,
        "source_note": item.source_note,
        "download_url": f"/api/publishing/files/{link.id}/original",
        "inherited": binding.kind == "inherited",
        "source_complete": item.extraction_json.get("material_scope", "complete") == "complete",
    }


def inherit(db, old, new):
    source = binding_for(db, old)
    if not source:
        return
    item = verify_binding(db, source)
    inherited = FormalDocumentBinding(
        id=core.uid(),
        file_id=new.id,
        manuscript_id=new.manuscript_id,
        journal_id=new.journal_id,
        version_id=new.version_id,
        file_object_id=new.file_object_id,
        import_id=item.id,
        kind="inherited",
        parent_id=source.id,
        confirmed_by=None,
        session_hash=None,
        selection_start=source.selection_start,
        selection_end=source.selection_end,
    )
    inherited.digest = binding_digest(inherited, item)
    db.add(inherited)
    db.flush()


def readable_original(db, actor, link):
    manuscript, flow = core.load_submission(db, actor, link.manuscript_id)
    version = db.get(ManuscriptVersion, link.version_id)
    if manuscript.author_id != actor.user.id and (
        not version.frozen_at
        or actor.role not in {"editor", "chief_editor"}
        or not core.capabilities(db, actor, manuscript) & {"handling_editor", "chief"}
        or core.is_conflicted(db, manuscript, actor.user)
    ):
        raise HTTPException(404, "原文件不存在或无权访问")
    origin = origin_for(db, link)
    if not origin:
        raise HTTPException(404, "该正式文件没有已确认的PDF/Word原件")
    binding = binding_for(db, link)
    item = db.get(FormalDocumentImport, binding.import_id)
    return item, verify_import(item)
