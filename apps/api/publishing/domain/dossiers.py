"""Private editorial preparation artifacts, separate from formal submissions.

Immutable, validated metadata snapshots reuse the publishing CAS and action gateway.
No synthetic author account, submission workflow, or model write capability is created.
"""

from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import now, uid
from ..security import Actor, get_actor
from .document_sources import inherit_source, source_projection
from .dossier_access import current, file_content, load, require_staff, snapshot_digest, version
from .dossier_actions import event, gateway
from .dossier_models import Dossier, DossierCheck, DossierTurn, DossierVersion
from .dossier_queries import list_summaries
from .dossier_schemas import AssistInput, ConfirmInput, CreateInput, DossierData, SaveInput, missing
from .dossier_schemas import DossierAuthor as DossierAuthor
from .dossier_schemas import ExplicitTrue as ExplicitTrue
from .dossier_schemas import RequestID as RequestID
from .dossier_schemas import TextUpload as TextUpload
from .dossier_views import message_page, projection, turn_projection, version_page
from .files import FileValidationError, store_bytes, validate_upload
from .models import FileObject

router = APIRouter(prefix="/api/dossiers", tags=["private editorial review dossiers"])


@router.get("")
def list_dossiers(
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=600),
    query: str = Query("", max_length=500),
):
    return list_summaries(db, actor, limit=limit, cursor=cursor, query=query)


@router.post("")
def create_dossier(
    body: CreateInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    require_staff(db, actor)

    def execute():
        require_staff(db, actor)
        version_id = uid()
        row = Dossier(
            id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"pivot:dossier:{actor.journal_id}:{actor.user.id}:{body.request_id}",
                )
            ),
            journal_id=actor.journal_id,
            created_by=actor.user.id,
            revision=1,
            current_version_id=version_id,
        )
        db.add(row)
        db.flush()
        data = DossierData(
            title=body.title, source_kind=body.source_kind, source_note=body.source_note
        ).model_dump()
        db.add(
            DossierVersion(
                id=version_id,
                dossier_id=row.id,
                journal_id=row.journal_id,
                version_no=1,
                data_json=data,
                content_digest=snapshot_digest(data, None, None, None),
                created_by=actor.user.id,
            )
        )
        db.flush()
        event(db, actor, row, "created", version_id)
        return {"dossier_id": row.id, "version_id": version_id}

    return gateway(db, actor, body, "create", None, execute)


@router.get("/{dossier_id}")
def get_dossier(dossier_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return projection(db, actor, str(dossier_id))


@router.get("/{dossier_id}/versions/{version_id}")
def get_version(
    dossier_id: UUID,
    version_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return projection(db, actor, str(dossier_id), str(version_id))


@router.get("/{dossier_id}/messages")
def get_messages(
    dossier_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=600),
):
    row = load(db, actor, str(dossier_id))
    return message_page(db, actor, row, limit=limit, cursor=cursor)


@router.get("/{dossier_id}/versions")
def get_versions(
    dossier_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=600),
):
    row = load(db, actor, str(dossier_id))
    return version_page(db, actor, row, limit=limit, cursor=cursor)


@router.post("/{dossier_id}/versions")
def save_version(
    dossier_id: UUID,
    body: SaveInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)

    def execute():
        row = load(db, actor, target, write=True)
        current(row, body.expected_revision)
        old = version(db, row)
        blob = None
        filename, media = old.file_name, old.file_media_type
        if body.file:
            try:
                upload = validate_upload(body.file.filename, body.file.content_base64)
                if not upload.raw.decode("utf-8").strip():
                    raise FileValidationError("empty_manuscript_text")
                storage_key = store_bytes(upload.raw, upload.sha256)
            except FileValidationError:
                raise HTTPException(422, "仅支持1 MiB以内有效UTF-8 TXT/Markdown文件") from None
            db.execute(
                insert(FileObject)
                .values(
                    id=uid(),
                    journal_id=row.journal_id,
                    uploaded_by=actor.user.id,
                    sha256=upload.sha256,
                    byte_size=upload.byte_size,
                    media_type=upload.media_type,
                    storage_key=storage_key,
                    original_filename=upload.filename,
                )
                .on_conflict_do_nothing(index_elements=[FileObject.journal_id, FileObject.sha256])
            )
            blob = db.scalar(
                select(FileObject).where(
                    FileObject.journal_id == row.journal_id, FileObject.sha256 == upload.sha256
                )
            )
            filename, media = upload.filename, upload.media_type
        elif old.file_object_id:
            blob, _ = file_content(db, old)
        data = body.data.model_dump()
        item = DossierVersion(
            id=uid(),
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_no=row.revision + 1,
            data_json=data,
            file_object_id=blob.id if blob else None,
            file_name=filename,
            file_media_type=media,
            content_digest=snapshot_digest(data, blob.sha256 if blob else None, filename, media),
            created_by=actor.user.id,
        )
        db.add(item)
        db.flush()
        row.revision += 1
        row.current_version_id = item.id
        row.updated_at = now()
        db.flush()
        if body.file is None:
            inherit_source(db, row, old, item)
        event(db, actor, row, "version_saved", item.id)
        return {"dossier_id": row.id, "version_id": item.id}

    return gateway(db, actor, body, "save", target, execute)


@router.get("/{dossier_id}/versions/{version_id}/file")
def download(
    dossier_id: UUID,
    version_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row = load(db, actor, str(dossier_id))
    item = version(db, row, str(version_id))
    material = file_content(db, item)
    if material is None:
        raise HTTPException(404, "该版本未上传正文")
    return Response(
        material[1],
        media_type=item.file_media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.file_name, safe='')}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Content-SHA256": material[0].sha256,
        },
    )


@router.post("/{dossier_id}/confirm")
def confirm(
    dossier_id: UUID,
    body: ConfirmInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)

    def execute():
        row = load(db, actor, target, write=True)
        current(row, body.expected_revision, str(body.version_id))
        item = version(db, row)

        source_projection(db, row, item)
        material = file_content(db, item)
        actual_digest = snapshot_digest(
            item.data_json,
            material[0].sha256 if material else None,
            item.file_name,
            item.file_media_type,
        )
        if body.digest != item.content_digest or body.digest != actual_digest:
            raise HTTPException(409, "核对快照已变化，请重新载入")
        incomplete = missing(DossierData.model_validate(item.data_json), bool(material))
        if incomplete:
            raise HTTPException(409, {"message": "资料仍需补齐", "missing": incomplete})
        if not db.scalar(select(DossierCheck).where(DossierCheck.version_id == item.id)):
            db.add(
                DossierCheck(
                    dossier_id=row.id,
                    journal_id=row.journal_id,
                    version_id=item.id,
                    content_digest=item.content_digest,
                    checked_by=actor.user.id,
                    session_hash=actor.session.token_hash,
                )
            )
            event(db, actor, row, "checked", item.id)
        return {"dossier_id": row.id, "version_id": item.id}

    return gateway(db, actor, body, "confirm", target, execute)


@router.post("/{dossier_id}/assist")
def assist(
    dossier_id: UUID,
    body: AssistInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    target = str(dossier_id)

    def execute():
        row = load(db, actor, target, write=True)
        current(row, body.expected_revision, str(body.version_id))
        item = version(db, row)
        issues = missing(DossierData.model_validate(item.data_json), bool(item.file_object_id))
        if any(
            word in body.message
            for word in ("发邮件", "发送", "录用", "拒稿", "发表", "确认", "批准")
        ):
            answer = "规则引导：对话不能代替负责人核对，也不能发送邮件或作编辑决定。请在独立核对页阅读当前完整资料后自行确认。"
        elif issues:
            answer = f"当前资料包 V{item.version_no} 尚有{len(issues)}处必填缺项：\n" + "\n".join(
                i["message"] for i in issues
            )
        else:
            answer = f"当前资料包 V{item.version_no} 的必填资料已补齐。请打开独立核对页检查全文、署名和来源。ORCID仍仅为录入者提供，未认证身份。"
        answer += "\n本轮仅规则引导，未调用模型，不进行全文科学审阅；内部资料不构成正式投稿。"
        turn = DossierTurn(
            id=uid(),
            dossier_id=row.id,
            journal_id=row.journal_id,
            version_id=item.id,
            user_id=actor.user.id,
            question=body.message,
            answer=answer,
        )
        db.add(turn)
        db.flush()
        event(db, actor, row, "assisted", item.id)
        return turn_projection(db, turn)

    return gateway(db, actor, body, "assist", target, execute)
