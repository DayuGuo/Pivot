"""Authenticated domain endpoints; model tools never receive final confirmation."""

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session

from packages.model_gateway.editorial import editorial_model_status

from ..db import get_db
from ..models import Journal
from ..security import Actor, get_actor
from . import core
from .chat import ChatContext, ChatInput, conversation, history
from .files import FileValidationError, read_bytes
from .models import FileObject, ManuscriptVersion, VersionFile
from .review_access import download_material, require_report
from .review_schemas import ReportData
from .reviews import save_report
from .schemas import FileUpload, IntakeData, StrictInput
from .stages import download_report, upload_report

router = APIRouter(prefix="/api/publishing", tags=["normalized publishing domain"])
RequestID = Annotated[UUID, Field(strict=False)]


class NewDraftInput(StrictInput):
    request_id: RequestID
    title: str = Field(default="", max_length=500)


class SaveIntakeInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    data: IntakeData


class UploadInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    file: FileUpload


class ProposalInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    action_type: str = Field(min_length=1, max_length=60)
    data: dict = Field(default_factory=dict, max_length=30)


class ConfirmationInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledged: Literal[True]
    reason: str = Field(default="", max_length=4000)


class ChatRequest(ChatInput):
    request_id: RequestID


class SaveReportInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=0)
    data: ReportData


@router.get("/chat")
def chat_history(
    manuscript_id: UUID | None = None,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return history(
        db, actor, ChatContext(manuscript_id=str(manuscript_id) if manuscript_id else None)
    )


@router.post("/chat")
def chat(body: ChatRequest, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return conversation(
        db,
        actor,
        str(body.request_id),
        ChatInput.model_validate(body.model_dump(exclude={"request_id"})),
    )


@router.get("/session")
def session(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    journal = db.get(Journal, actor.journal_id)
    return {
        "user": {
            "id": actor.user.id,
            "name": actor.user.name,
            "email": actor.user.email,
            "role": actor.role,
        },
        "journal": {"id": journal.id, "name": journal.name},
        "csrf_token": actor.session.csrf_token,
        "model": editorial_model_status(),
        "synthetic_only": True,
        "email_send_enabled": False,
    }


@router.get("/workspace")
def workspace(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return core.workspace(db, actor)


@router.post("/drafts")
def new_draft(
    body: NewDraftInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "new_draft",
        body.model_dump(mode="json", exclude={"request_id"}),
        lambda: core.new_draft(db, actor, body.title),
    )


@router.get("/manuscripts/{manuscript_id}")
def manuscript(
    manuscript_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    return core.submission_projection(db, actor, str(manuscript_id))


@router.patch("/manuscripts/{manuscript_id}/intake")
def intake(
    manuscript_id: UUID,
    body: SaveIntakeInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "save_intake",
        {
            "manuscript_id": str(manuscript_id),
            **body.model_dump(mode="json", exclude={"request_id"}),
        },
        lambda: core.save_intake(db, actor, str(manuscript_id), body.expected_revision, body.data),
    )


@router.post("/manuscripts/{manuscript_id}/files")
def upload(
    manuscript_id: UUID,
    body: UploadInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    # Store only a payload digest in receipts, never duplicate file bytes in audit.
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "upload_file",
        {
            "manuscript_id": str(manuscript_id),
            **body.model_dump(mode="json", exclude={"request_id"}),
        },
        lambda: core.upload_file(db, actor, str(manuscript_id), body.expected_revision, body.file),
    )


@router.post("/manuscripts/{manuscript_id}/proposals")
def proposal(
    manuscript_id: UUID,
    body: ProposalInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "prepare_proposal",
        {
            "manuscript_id": str(manuscript_id),
            **body.model_dump(mode="json", exclude={"request_id"}),
        },
        lambda: core.prepare_proposal(
            db, actor, str(manuscript_id), body.expected_revision, body.action_type, body.data
        ),
    )


@router.get("/proposals/{proposal_id}")
def review(proposal_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return core.proposal_projection(db, actor, str(proposal_id))


@router.post("/proposals/{proposal_id}/confirmations")
def confirm(
    proposal_id: UUID,
    body: ConfirmationInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "confirm_proposal",
        {"proposal_id": str(proposal_id), **body.model_dump(mode="json", exclude={"request_id"})},
        lambda: core.confirm_proposal(
            db,
            actor,
            str(proposal_id),
            body.expected_revision,
            body.digest,
            acknowledged=body.acknowledged,
            reason=body.reason,
        ),
    )


@router.get("/files/{file_id}")
def download(file_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    link = db.get(VersionFile, str(file_id))
    if not link or link.journal_id != actor.journal_id:
        raise HTTPException(404, "文件不存在或无权访问")
    core.load_submission(db, actor, link.manuscript_id)
    version = db.get(ManuscriptVersion, link.version_id)
    # Unsubmitted files remain private to their author; reviewer-specific file
    # access is added only with an accepted review assignment in the review slice.
    manuscript, _ = core.load_submission(db, actor, link.manuscript_id)
    if actor.role == "reviewer" and manuscript.author_id != actor.user.id:
        raise HTTPException(404, "请使用本轮明确授权的匿名评审材料入口")
    if not version.frozen_at and manuscript.author_id != actor.user.id:
        raise HTTPException(404, "文件不存在或无权访问")
    blob = db.get(FileObject, link.file_object_id)
    try:
        content = read_bytes(blob.storage_key)
    except FileValidationError:
        raise HTTPException(409, "文件内容校验失败，请联系本地管理员") from None
    if len(content) != blob.byte_size:
        raise HTTPException(409, "文件内容校验失败")
    return Response(
        content=content,
        media_type=blob.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(link.display_name, safe='')}",
            "X-Content-SHA256": blob.sha256,
        },
    )


@router.post("/manuscripts/{manuscript_id}/reports")
def report_upload(
    manuscript_id: UUID,
    body: UploadInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "upload_report",
        {
            "manuscript_id": str(manuscript_id),
            **body.model_dump(mode="json", exclude={"request_id"}),
        },
        lambda: upload_report(db, actor, str(manuscript_id), body.expected_revision, body.file),
    )


@router.get("/manuscripts/{manuscript_id}/reports/{file_id}")
def report_download(
    manuscript_id: UUID,
    file_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    blob, name, content = download_report(db, actor, str(manuscript_id), str(file_id))
    return Response(
        content=content,
        media_type=blob.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
            "X-Content-SHA256": blob.sha256,
        },
    )


@router.patch("/review-reports/{report_id}")
def report_save(
    report_id: UUID,
    body: SaveReportInput,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    require_report(db, actor, str(report_id))
    return core.run_action(
        db,
        actor,
        str(body.request_id),
        "save_review_report",
        {"report_id": str(report_id), **body.model_dump(mode="json", exclude={"request_id"})},
        lambda: save_report(db, actor, str(report_id), body.expected_revision, body.data),
    )


@router.get("/review-materials/{file_id}")
def review_material(
    file_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    blob, name, content = download_material(db, actor, str(file_id))
    return Response(
        content=content,
        media_type=blob.media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
            "X-Content-SHA256": blob.sha256,
        },
    )
