"""Staged binary ingestion. A person, never a model, approves the exact new version."""

import base64
import binascii
import hashlib
import time
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from packages.document_ingest import DocumentError, extract_document
from packages.model_gateway.gateway import GatewayError

from ..audit import record
from ..db import get_db
from ..models import now, uid
from ..security import Actor, get_actor
from . import dossier_access as access
from . import dossier_actions as actions
from .document_candidates import identify
from .document_models import DocumentApproval, DocumentImport, DocumentSource
from .document_sources import (
    approval_digest,
    import_digest,
    source_projection,
    verify_import,
)
from .document_sources import (
    attach_document as attach_document,
)
from .document_sources import (
    inherit_source as inherit_source,
)
from .document_sources import (
    origin_digest as origin_digest,
)
from .document_store import MAX_BYTES, store_original
from .dossier_models import DossierCheck, DossierVersion
from .dossier_schemas import DossierData, ExplicitTrue, RequestID, missing
from .files import FileValidationError, store_bytes, validate_upload
from .models import FileObject
from .schemas import StrictInput

router = APIRouter(prefix="/api/dossiers", tags=["human-reviewed document imports"])


class DocumentUpload(StrictInput):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4, max_length=6990508)


class ImportInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    version_id: RequestID
    file: DocumentUpload
    authorized_material: ExplicitTrue


class ApproveInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    data: DossierData
    acknowledged: ExplicitTrue


def load_import(db, actor, dossier_id, import_id):
    row = access.load(db, actor, dossier_id)
    item = db.scalar(
        select(DocumentImport).where(
            DocumentImport.id == import_id,
            DocumentImport.dossier_id == row.id,
            DocumentImport.journal_id == row.journal_id,
        )
    )
    if not item:
        raise HTTPException(404, "导入记录不存在或无权访问")
    return row, item


def import_projection(db, actor, target, import_id):
    row, item = load_import(db, actor, target, import_id)
    verify_import(item)
    approved = db.scalar(select(DocumentApproval).where(DocumentApproval.import_id == item.id))
    e = item.extraction_json
    return {
        "id": item.id,
        "dossier_id": row.id,
        "base_revision": item.base_revision,
        "base_version_id": item.base_version_id,
        "digest": item.digest,
        "filename": item.filename,
        "media_type": item.media_type,
        "byte_size": item.byte_size,
        "sha256": item.sha256,
        "original_download_url": f"/api/dossiers/{row.id}/imports/{item.id}/file",
        "parser": e["parser"],
        "text": e["text"],
        "segments": e["segments"],
        "warnings": e["warnings"],
        "proposed_data": item.proposed_data,
        "field_sources": item.field_sources,
        "metadata_provider": item.metadata_provider,
        "metadata_model": item.metadata_model,
        "telemetry": item.telemetry_json,
        "confirmed_version_id": approved.version_id if approved else None,
        "editable": approved is None
        and row.revision == item.base_revision
        and row.current_version_id == item.base_version_id,
    }


@router.post("/{dossier_id}/imports")
def prepare_import(
    dossier_id: UUID,
    body: ImportInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)
    deadline = time.monotonic() + 60
    telemetry = []
    diagnostics = []

    def validate():
        row = access.load(db, actor, target)
        access.current(row, body.expected_revision, str(body.version_id))
        if time.monotonic() >= deadline:
            raise GatewayError("editorial_provider_deadline")
        return row

    def execute():
        row = validate()
        base = access.version(db, row)
        try:
            raw = base64.b64decode(body.file.content_base64, validate=True)
            if (
                not 1 <= len(raw) <= MAX_BYTES
                or base64.b64encode(raw).decode() != body.file.content_base64
            ):
                raise ValueError
        except (binascii.Error, ValueError):
            raise HTTPException(422, "原文件编码或大小无效（上限5 MiB）") from None
        try:
            extraction = extract_document(body.file.filename, raw)
            derived = validate_upload(
                "extracted.txt", base64.b64encode(extraction["text"].encode()).decode()
            )
        except DocumentError as error:
            messages = {
                "document_format_unsupported": "请上传含文字层的PDF或Word .docx；旧版.doc请先另存为.docx。",
                "document_encrypted": "PDF已加密；请在本地解密并保存副本后重新上传。",
                "document_text_missing": "未找到可提取文字；扫描件请先完成OCR，再上传文字文档。",
                "document_text_incomplete": "部分页面没有可提取文字，未保存不完整全文；请先完成OCR或重新导出。",
                "document_tracked_changes": "Word含未处理修订；请在Word核对并接受或拒绝修订，保存副本后上传。",
                "document_annotations_unsupported": "文档含暂未支持的批注结构，请移除批注并保存副本后上传。",
                "document_layout_unsupported": "Word含暂未支持的动态域或文本框；请转换为静态正文并保存副本后上传。",
                "document_unsafe_relationship": "文档含外部模板、链接图片或对象；请移除这些依赖后重新上传。",
                "document_active_content": "文档包含宏、脚本或嵌入对象，无法处理；请另存为不含活动内容的副本。",
                "document_page_limit": "当前仅支持不超过60页的PDF，没有截断或保存部分全文。",
                "document_text_limit": "提取文本超过1 MiB上限，没有截断；请简化文档后重新上传。",
                "document_parse_timeout": "解析超时；请重新导出为标准PDF或.docx后再试。",
            }
            raise HTTPException(
                422,
                {
                    "message": messages.get(
                        error.code, "无法完整、安全地提取文本，请重新导出文件后再试。"
                    ),
                    "error_code": error.code,
                },
            ) from None
        except FileValidationError:
            raise HTTPException(422, "提取全文包含不受支持的文字或超过1 MiB，未创建版本") from None
        validate()
        data, sources, provider, model, metrics = identify(
            extraction,
            base.data_json,
            validate,
            deadline,
            telemetry=telemetry,
            diagnostics=diagnostics,
        )
        # No write lock spans parser/model work. Then revalidate original identity and bytes.
        row = access.load(db, actor, target, write=True)
        access.current(row, body.expected_revision, str(body.version_id))
        validate()
        storage = store_original(raw)
        extraction = {**extraction, "sha256": derived.sha256, "metadata_diagnostics": diagnostics}
        item = DocumentImport(
            id=uid(),
            dossier_id=row.id,
            journal_id=row.journal_id,
            base_version_id=base.id,
            base_revision=row.revision,
            filename=body.file.filename,
            media_type="application/pdf"
            if body.file.filename.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            storage_key=storage,
            extraction_json=extraction,
            proposed_data=data,
            field_sources=sources,
            metadata_provider=provider,
            metadata_model=model,
            telemetry_json=metrics,
            created_by=actor.user.id,
        )
        item.digest = import_digest(item)
        db.add(item)
        db.flush()
        actions.event(db, actor, row, "document_import_prepared", base.id)
        validate()
        return {"dossier_id": row.id, "import_id": item.id}

    try:
        return actions.gateway(db, actor, body, "document_import", target, execute)
    except FileValidationError:
        raise HTTPException(409, "原文件存储未完成，请重试") from None
    except GatewayError as error:
        db.rollback()
        try:
            access.load(db, actor, target)
            code = (
                error.args[0]
                if error.args
                and error.args[0]
                in {
                    "document_material_credentials",
                    "document_metadata_invalid",
                    "document_metadata_evidence_invalid",
                    "editorial_provider_deadline",
                }
                else "document_metadata_unavailable"
            )
            record(
                db,
                actor_id=actor.user.id,
                journal_id=actor.journal_id,
                action="publishing.document_import_failed",
                entity_id=target,
                details={"error_code": code, "telemetry": telemetry, "diagnostics": diagnostics},
            )
            db.commit()
        except Exception:
            db.rollback()
        if error.args == ("document_material_credentials",):
            raise HTTPException(422, "文稿包含疑似密钥，已阻止发送至模型；请移除后重试。") from None
        raise HTTPException(503, "候选识别未完成，没有创建版本；请重试。") from None


@router.get("/{dossier_id}/imports")
def list_imports(
    dossier_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    row = access.load(db, actor, str(dossier_id))
    items = db.scalars(
        select(DocumentImport)
        .where(DocumentImport.dossier_id == row.id, DocumentImport.journal_id == row.journal_id)
        .order_by(DocumentImport.created_at.desc())
        .limit(100)
    ).all()
    approvals = {
        a.import_id: a.version_id
        for a in db.scalars(
            select(DocumentApproval).where(DocumentApproval.dossier_id == row.id)
        ).all()
    }
    return {
        "items": [
            {
                "id": i.id,
                "filename": i.filename,
                "created_at": i.created_at.isoformat(),
                "confirmed_version_id": approvals.get(i.id),
                "base_revision": i.base_revision,
            }
            for i in items
        ]
    }


@router.get("/{dossier_id}/imports/{import_id}")
def get_import(
    dossier_id: UUID,
    import_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return import_projection(db, actor, str(dossier_id), str(import_id))


@router.get("/{dossier_id}/imports/{import_id}/file")
def download_import(
    dossier_id: UUID,
    import_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    _, item = load_import(db, actor, str(dossier_id), str(import_id))
    raw = verify_import(item)
    return Response(
        raw,
        media_type=item.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.filename, safe='')}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": item.sha256,
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/{dossier_id}/imports/{import_id}/confirm")
def approve_import(
    dossier_id: UUID,
    import_id: UUID,
    body: ApproveInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)
    iid = str(import_id)

    def execute():
        row = access.load(db, actor, target, write=True)
        _, item = load_import(db, actor, target, iid)
        access.current(row, body.expected_revision, item.base_version_id)
        if row.revision != item.base_revision or body.digest != item.digest:
            raise HTTPException(409, "导入所依据的版本或核对快照已变化，请重新导入")
        if db.scalar(select(DocumentApproval).where(DocumentApproval.import_id == item.id)):
            raise HTTPException(409, "该导入已确认，请查看已保存版本")
        verify_import(item)
        incomplete = missing(body.data, True)
        if incomplete:
            raise HTTPException(409, {"message": "请补齐必填资料后再确认", "missing": incomplete})
        raw = item.extraction_json["text"].encode()
        sha = hashlib.sha256(raw).hexdigest()
        key = store_bytes(raw, sha)
        filename = item.filename[:230] + ".extracted.txt"
        db.execute(
            insert(FileObject)
            .values(
                id=uid(),
                journal_id=row.journal_id,
                uploaded_by=actor.user.id,
                sha256=sha,
                byte_size=len(raw),
                media_type="text/plain",
                storage_key=key,
                original_filename=filename,
            )
            .on_conflict_do_nothing(index_elements=[FileObject.journal_id, FileObject.sha256])
        )
        blob = db.scalar(
            select(FileObject).where(
                FileObject.journal_id == row.journal_id, FileObject.sha256 == sha
            )
        )
        data = body.data.model_dump()
        version = DossierVersion(
            id=uid(),
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_no=row.revision + 1,
            data_json=data,
            file_object_id=blob.id,
            file_name=filename,
            file_media_type="text/plain",
            content_digest=access.snapshot_digest(data, sha, filename, "text/plain"),
            created_by=actor.user.id,
        )
        db.add(version)
        db.flush()
        row.revision += 1
        row.current_version_id = version.id
        row.updated_at = now()
        db.flush()
        approval = DocumentApproval(
            id=uid(),
            import_id=item.id,
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_id=version.id,
            reviewed_data=data,
            digest=approval_digest(item, data, version.content_digest),
            reviewer_id=actor.user.id,
            session_hash=actor.session.token_hash,
        )
        db.add(approval)
        db.flush()
        db.add(
            DocumentSource(
                version_id=version.id,
                dossier_id=row.id,
                journal_id=row.journal_id,
                import_id=item.id,
                approval_id=approval.id,
                origin_digest=origin_digest(item, approval, version),
            )
        )
        db.flush()
        db.add(
            DossierCheck(
                dossier_id=row.id,
                journal_id=row.journal_id,
                version_id=version.id,
                content_digest=version.content_digest,
                checked_by=actor.user.id,
                session_hash=actor.session.token_hash,
            )
        )
        db.flush()
        actions.event(db, actor, row, "document_import_approved", version.id)
        return {"dossier_id": row.id, "version_id": version.id}

    def revalidate_confirmation():
        row, item = load_import(db, actor, target, iid)
        approved = db.scalar(
            select(DocumentApproval).where(
                DocumentApproval.import_id == item.id,
                DocumentApproval.dossier_id == row.id,
                DocumentApproval.journal_id == row.journal_id,
            )
        )
        if approved is None:
            raise HTTPException(409, "此确认回执不属于当前导入记录")
        approved_version = access.version(db, row, approved.version_id)
        if source_projection(db, row, approved_version) is None:
            raise HTTPException(409, "确认记录缺少完整原件来源，请重新核对")
        access.require_staff(db, actor)

    # Keep the v1 request fingerprint so existing VPS receipts remain replayable.
    # The immutable approval binds both legacy and new replays to the actual path.
    return actions.gateway(
        db,
        actor,
        body,
        "document_approve",
        target,
        execute,
        revalidate_resource=revalidate_confirmation,
    )
