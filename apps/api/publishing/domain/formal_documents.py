"""Formal PDF/DOCX file preparation and explicit owner confirmation, through Action Gateway."""

import base64
import binascii
import hashlib
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.document_ingest import DocumentError, extract_document

from ..db import get_db
from ..security import Actor, get_actor
from . import core
from .document_store import MAX_BYTES, store_original
from .dossier_evidence import credential_like
from .dossier_schemas import ExplicitTrue, RequestID
from .files import FileValidationError
from .formal_document_models import FormalDocumentBinding, FormalDocumentImport
from .formal_document_sources import (
    binding_digest,
    import_digest,
    readable_original,
    selected_text,
    verify_binding,
    verify_import,
)
from .models import ActionReceipt, ManuscriptVersion, VersionFile
from .pagination import cursor_position, next_cursor, older_than, scope_key
from .schemas import FileUpload, StrictInput

router = APIRouter(prefix="/api/publishing", tags=["reviewed formal document imports"])


@router.get("/manuscripts/{manuscript_id}/document-imports")
def pending_imports(
    manuscript_id: UUID,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=20),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    mid = str(manuscript_id)
    manuscript, flow = core.load_submission(db, actor, mid)
    if manuscript.author_id != actor.user.id:
        raise HTTPException(404, "待核对导入不存在或无权访问")
    scope = scope_key(
        "formal-pending", actor.journal_id, actor.user.id, actor.role, mid, flow.draft_version_id
    )
    position = cursor_position(cursor, scope)
    query = select(FormalDocumentImport).where(
        FormalDocumentImport.manuscript_id == mid,
        FormalDocumentImport.journal_id == actor.journal_id,
        FormalDocumentImport.version_id == flow.draft_version_id,
        ~select(FormalDocumentBinding.id)
        .where(
            FormalDocumentBinding.import_id == FormalDocumentImport.id,
            FormalDocumentBinding.kind == "confirmed",
        )
        .exists(),
    )
    if position:
        query = query.where(
            older_than(FormalDocumentImport.created_at, FormalDocumentImport.id, position)
        )
    rows = db.scalars(
        query.order_by(
            FormalDocumentImport.created_at.desc(), FormalDocumentImport.id.desc()
        ).limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "filename": r.filename,
                "purpose": r.purpose,
                "editable": r.base_revision == flow.revision,
            }
            for r in rows[:limit]
        ],
        "next_cursor": next_cursor(rows, limit, scope),
    }


class PrepareInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    version_id: RequestID
    purpose: Literal["manuscript", "blinded_manuscript", "response"]
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4, max_length=6990508)
    authorized_material: ExplicitTrue
    material_scope: Literal["complete", "excerpt"] = "complete"
    source_kind: Literal["synthetic", "public_authorized"]
    source_note: str = Field(min_length=5, max_length=2000)


class ConfirmInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_segment: int = Field(ge=1, le=5000)
    last_segment: int = Field(ge=1, le=5000)
    acknowledged_original: ExplicitTrue
    acknowledged_text: ExplicitTrue
    acknowledged_scope: ExplicitTrue


def editable(db, actor, mid, revision=None, version_id=None, write=False):
    manuscript, flow = core.load_submission(db, actor, mid, write=write)
    if (
        manuscript.author_id != actor.user.id
        or flow.stage not in {"author_draft", "author_revision"}
        or not flow.draft_version_id
    ):
        raise HTTPException(403, "仅稿件负责人可在本人准备或修回草稿中确认导入")
    if revision is not None:
        core.require_revision(flow, revision)
    if version_id is not None and flow.draft_version_id != version_id:
        raise HTTPException(409, "导入绑定的草稿版本已变化")
    version = db.get(ManuscriptVersion, flow.draft_version_id)
    if version.frozen_at:
        raise HTTPException(409, "正式提交版本不可覆盖")
    return manuscript, flow, version


def owned_import(db, actor, mid, iid):
    manuscript, flow = core.load_submission(db, actor, mid)
    if manuscript.author_id != actor.user.id:
        raise HTTPException(404, "导入记录不存在或无权访问")
    item = db.scalar(
        select(FormalDocumentImport).where(
            FormalDocumentImport.id == iid,
            FormalDocumentImport.manuscript_id == mid,
            FormalDocumentImport.journal_id == actor.journal_id,
        )
    )
    if not item:
        raise HTTPException(404, "导入记录不存在或无权访问")
    verify_import(item)
    return item, flow


def projection(db, actor, mid, iid):
    item, flow = owned_import(db, actor, mid, iid)
    binding = db.scalar(
        select(FormalDocumentBinding).where(
            FormalDocumentBinding.import_id == item.id, FormalDocumentBinding.kind == "confirmed"
        )
    )
    e = item.extraction_json
    if binding:
        verify_binding(db, binding)
    return {
        "id": item.id,
        "manuscript_id": mid,
        "version_id": item.version_id,
        "base_revision": item.base_revision,
        "digest": item.digest,
        "purpose": item.purpose,
        "filename": item.filename,
        "sha256": item.sha256,
        "source_kind": item.source_kind,
        "source_note": item.source_note,
        "text": e["text"],
        "segments": e["segments"],
        "warnings": e["warnings"],
        "parser": e["parser"],
        "material_scope": e.get("material_scope", "complete"),
        "original_url": f"/api/publishing/manuscripts/{mid}/document-imports/{iid}/original",
        "editable": binding is None
        and flow.draft_version_id == item.version_id
        and flow.revision == item.base_revision
        and flow.stage in {"author_draft", "author_revision"},
        "confirmed_file_id": binding.file_id if binding else None,
        "confirmed_range": {
            "first_segment": next(
                s["number"] for s in e["segments"] if s["start"] == binding.selection_start
            ),
            "last_segment": next(
                s["number"] for s in e["segments"] if s["end"] == binding.selection_end
            ),
        }
        if binding
        else None,
    }


@router.post("/manuscripts/{manuscript_id}/document-imports")
def prepare(
    manuscript_id: UUID,
    body: PrepareInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    mid = str(manuscript_id)

    def execute():
        editable(db, actor, mid, body.expected_revision, str(body.version_id))
        try:
            raw = base64.b64decode(body.content_base64, validate=True)
            if (
                not 1 <= len(raw) <= MAX_BYTES
                or base64.b64encode(raw).decode() != body.content_base64
            ):
                raise ValueError
        except (ValueError, binascii.Error):
            raise HTTPException(422, "原文件编码或大小无效，上限5 MiB") from None
        try:
            extraction = extract_document(body.filename, raw)
        except DocumentError as error:
            raise HTTPException(
                422,
                {
                    "message": "无法完整安全地提取，请使用文字层PDF或已处理修订/批注的DOCX。扫描件须先OCR；没有保存部分全文。",
                    "error_code": error.code,
                },
            ) from None
        if credential_like(extraction["text"] + "\n" + body.source_note):
            raise HTTPException(422, "资料含疑似凭据，已阻止导入；请移除后重新准备")
        editable(db, actor, mid, body.expected_revision, str(body.version_id), write=True)
        extraction = {
            **extraction,
            "material_scope": body.material_scope,
            "sha256": hashlib.sha256(extraction["text"].encode()).hexdigest(),
        }
        try:
            storage_key = store_original(raw)
        except FileValidationError:
            raise HTTPException(409, "原文件无法安全保存，请重新准备导入") from None
        item = FormalDocumentImport(
            id=core.uid(),
            manuscript_id=mid,
            journal_id=actor.journal_id,
            version_id=str(body.version_id),
            base_revision=body.expected_revision,
            purpose=body.purpose,
            filename=body.filename,
            media_type="application/pdf"
            if body.filename.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            storage_key=storage_key,
            extraction_json=extraction,
            source_kind=body.source_kind,
            source_note=body.source_note,
            created_by=actor.user.id,
        )
        item.digest = import_digest(item)
        db.add(item)
        db.flush()
        core.event(
            db,
            actor,
            mid,
            "formal_document_prepared",
            {"version_id": item.version_id, "import_id": item.id, "purpose": item.purpose},
        )
        return {"manuscript_id": mid, "import_id": item.id}

    def replay():
        previous = db.scalar(
            select(ActionReceipt).where(
                ActionReceipt.user_id == actor.user.id,
                ActionReceipt.journal_id == actor.journal_id,
                ActionReceipt.request_id == str(body.request_id),
            )
        )
        if not previous or not previous.response.get("import_id"):
            raise HTTPException(409, "导入回执来源不完整")
        owned_import(db, actor, mid, previous.response["import_id"])

    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "prepare_formal_document",
        {"manuscript_id": mid, **body.model_dump(mode="json", exclude={"request_id"})},
        execute,
        revalidate_replay=replay,
    )


@router.get("/manuscripts/{manuscript_id}/document-imports/{import_id}")
def detail(
    manuscript_id: UUID,
    import_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return projection(db, actor, str(manuscript_id), str(import_id))


@router.get("/manuscripts/{manuscript_id}/document-imports/{import_id}/original")
def prepared_original(
    manuscript_id: UUID,
    import_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    item, _ = owned_import(db, actor, str(manuscript_id), str(import_id))
    return original_response(item, verify_import(item))


def original_response(item, raw):
    mode = "inline" if item.media_type == "application/pdf" else "attachment"
    return Response(
        raw,
        media_type=item.media_type,
        headers={
            "Content-Disposition": f"{mode}; filename*=UTF-8''{quote(item.filename, safe='')}",
            "X-Content-SHA256": item.sha256,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/files/{file_id}/original")
def original(file_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    link = db.get(VersionFile, str(file_id))
    if not link or link.journal_id != actor.journal_id:
        raise HTTPException(404, "原文件不存在或无权访问")
    item, raw = readable_original(db, actor, link)
    return original_response(item, raw)


@router.post("/manuscripts/{manuscript_id}/document-imports/{import_id}/confirmations")
def confirm(
    manuscript_id: UUID,
    import_id: UUID,
    body: ConfirmInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    mid, iid = str(manuscript_id), str(import_id)

    def execute():
        item, _ = owned_import(db, actor, mid, iid)
        if item.base_revision != body.expected_revision:
            raise HTTPException(409, "稿件内容已变化，请重新准备导入并核对")
        _, _, version = editable(
            db, actor, mid, body.expected_revision, item.version_id, write=True
        )
        if item.digest != body.digest:
            raise HTTPException(409, "导入快照已变化，请重新核对")
        if db.scalar(
            select(FormalDocumentBinding.id).where(
                FormalDocumentBinding.import_id == iid, FormalDocumentBinding.kind == "confirmed"
            )
        ):
            raise HTTPException(409, "该导入已确认，请查看当前版本文件")
        start, end, text = selected_text(item, body.first_segment, body.last_segment)
        upload = FileUpload(
            filename=item.filename[:225] + ".extracted.txt",
            content_base64=base64.b64encode(text.encode()).decode(),
            purpose=item.purpose,
        )
        out = core.upload_file(db, actor, mid, body.expected_revision, upload)
        link = db.get(VersionFile, out["file_id"])
        binding = FormalDocumentBinding(
            id=core.uid(),
            file_id=link.id,
            manuscript_id=mid,
            journal_id=actor.journal_id,
            version_id=version.id,
            file_object_id=link.file_object_id,
            import_id=iid,
            kind="confirmed",
            parent_id=None,
            confirmed_by=actor.user.id,
            session_hash=actor.session.token_hash,
            selection_start=start,
            selection_end=end,
        )
        binding.digest = binding_digest(binding, item)
        db.add(binding)
        db.flush()
        core.event(
            db,
            actor,
            mid,
            "formal_document_confirmed",
            {
                "version_id": version.id,
                "file_id": link.id,
                "import_id": iid,
                "binding_id": binding.id,
            },
        )
        return {**out, "import_id": iid, "binding_id": binding.id}

    def replay():
        item, _ = owned_import(db, actor, mid, iid)
        binding = db.scalar(
            select(FormalDocumentBinding).where(
                FormalDocumentBinding.import_id == item.id,
                FormalDocumentBinding.kind == "confirmed",
            )
        )
        if not binding:
            raise HTTPException(409, "确认回执的原文绑定不存在")
        verify_binding(db, binding)

    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "confirm_formal_document",
        {
            "manuscript_id": mid,
            "import_id": iid,
            **body.model_dump(mode="json", exclude={"request_id"}),
        },
        execute,
        revalidate_replay=replay,
    )
