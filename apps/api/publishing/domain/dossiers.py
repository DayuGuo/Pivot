"""Private editorial preparation artifacts, separate from formal submissions.

Immutable, validated metadata snapshots reuse the publishing CAS and action gateway.
No synthetic author account, submission workflow, or model write capability is created.
"""

import hashlib
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BeforeValidator, Field
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..audit import record
from ..db import get_db
from ..models import Base, now, uid
from ..security import Actor, get_actor
from .core import digest, ensure_actor, run_action
from .files import FileValidationError, read_bytes, store_bytes, validate_upload
from .models import FileObject
from .schemas import AuthorInput, Keyword, StrictInput, _email_format_valid


class Dossier(Base):
    __tablename__ = "publishing_dossiers"
    __table_args__ = (
        UniqueConstraint("id", "journal_id", name="uq_dossier_tenant"),
        CheckConstraint("revision >= 1", name="ck_dossier_revision"),
        ForeignKeyConstraint(
            ["current_version_id", "id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_current",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer)
    current_version_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierVersion(Base):
    __tablename__ = "publishing_dossier_versions"
    __table_args__ = (
        UniqueConstraint("id", "dossier_id", "journal_id", name="uq_dossier_version_tenant"),
        UniqueConstraint("dossier_id", "version_no", name="uq_dossier_version_number"),
        ForeignKeyConstraint(
            ["dossier_id", "journal_id"],
            ["publishing_dossiers.id", "publishing_dossiers.journal_id"],
            name="fk_dossier_version_parent",
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_dossier_version_file",
        ),
        CheckConstraint("version_no >= 1", name="ck_dossier_version_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_no: Mapped[int] = mapped_column(Integer)
    data_json: Mapped[dict] = mapped_column(JSONB)
    file_object_id: Mapped[str | None] = mapped_column(String(36))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_media_type: Mapped[str | None] = mapped_column(String(100))
    content_digest: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierCheck(Base):
    __tablename__ = "publishing_dossier_checks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_check_version",
        ),
        UniqueConstraint("version_id", name="uq_dossier_checked_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    content_digest: Mapped[str] = mapped_column(String(64))
    checked_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierTurn(Base):
    __tablename__ = "publishing_dossier_turns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_turn_version",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(String(2000))
    answer: Mapped[str] = mapped_column(String(6000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DossierAuthor(AuthorInput):
    source_note: str = Field(default="", max_length=1000)


class DossierData(StrictInput):
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=12000)
    language: Literal["zh", "en"] = "zh"
    keywords: list[Keyword] = Field(default_factory=list, max_length=12)
    authors: list[DossierAuthor] = Field(default_factory=list, max_length=20)
    source_kind: Literal["synthetic", "public_authorized"]
    source_note: str = Field(min_length=5, max_length=2000)


def require_explicit_true(value):
    if value is not True:
        raise ValueError("需要负责人显式确认，必须为布尔true")
    return value


ExplicitTrue = Annotated[Literal[True], BeforeValidator(require_explicit_true)]
RequestID = Annotated[UUID, Field(strict=False)]


class CreateInput(StrictInput):
    request_id: RequestID
    title: str = Field(default="", max_length=500)
    source_kind: Literal["synthetic", "public_authorized"]
    source_note: str = Field(min_length=5, max_length=2000)
    authorized_material: ExplicitTrue


class TextUpload(StrictInput):
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=4, max_length=1398104)


class SaveInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    data: DossierData
    file: TextUpload | None = None


class ConfirmInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    version_id: RequestID
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledged: ExplicitTrue


class AssistInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=1)
    version_id: RequestID
    message: str = Field(min_length=1, max_length=2000)


router = APIRouter(prefix="/api/dossiers", tags=["private editorial review dossiers"])


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


def missing(data: DossierData, has_file: bool) -> list[dict]:
    found = []

    def need(ok, field, message):
        if not ok:
            found.append({"field": field, "message": message})

    need(len(data.title) >= 3, "title", "题名至少3个字符")
    need(len(data.abstract) >= 40, "abstract", "摘要至少40个字符")
    need(any(word.strip() for word in data.keywords), "keywords", "至少填写1个关键词")
    need(has_file, "file", "请上传完整TXT或Markdown正文")
    need(bool(data.authors), "authors", "至少填写1位作者")
    need(
        sum(a.corresponding for a in data.authors) == 1,
        "authors.corresponding",
        "请选择且仅选择1位通讯作者",
    )
    for index, author in enumerate(data.authors):
        need(bool(author.name), f"authors.{index}.name", "请填写作者姓名")
        need(
            bool(author.affiliations) and all(a.strip() for a in author.affiliations),
            f"authors.{index}.affiliations",
            "请填写作者机构",
        )
        need(bool(author.source_note), f"authors.{index}.source_note", "请说明作者资料的提供来源")
        if author.corresponding:
            need(
                _email_format_valid(author.email),
                f"authors.{index}.email",
                "请填写有效的通讯邮箱；格式检查不是身份认证",
            )
    return found


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


def turn_projection(db: Session, turn: DossierTurn):
    item = db.get(DossierVersion, turn.version_id)
    return {
        "id": turn.id,
        "question": turn.question,
        "answer": turn.answer,
        "provider": "rules",
        "version_id": turn.version_id,
        "version_no": item.version_no,
    }


def projection(db: Session, actor: Actor, dossier_id: str, version_id: str | None = None):
    row = load(db, actor, dossier_id)
    item = version(db, row, version_id)
    data = DossierData.model_validate(item.data_json)
    material = file_content(db, item)
    check = db.scalar(select(DossierCheck).where(DossierCheck.version_id == item.id))
    versions = db.scalars(
        select(DossierVersion)
        .where(DossierVersion.dossier_id == row.id)
        .order_by(DossierVersion.version_no.desc())
    ).all()
    checked = set(
        db.scalars(select(DossierCheck.version_id).where(DossierCheck.dossier_id == row.id)).all()
    )
    turns = db.scalars(
        select(DossierTurn)
        .where(DossierTurn.dossier_id == row.id, DossierTurn.user_id == actor.user.id)
        .order_by(DossierTurn.created_at.desc(), DossierTurn.id.desc())
        .limit(50)
    ).all()
    return {
        "id": row.id,
        "revision": row.revision,
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "is_current": item.id == row.current_version_id,
        "verified": check is not None,
        "verification": {"id": check.id, "by": check.checked_by, "at": check.checked_at.isoformat()}
        if check
        else None,
        "data": data.model_dump(),
        "file": {
            "filename": item.file_name,
            "sha256": material[0].sha256,
            "byte_size": material[0].byte_size,
            "media_type": item.file_media_type,
            "text": material[1].decode("utf-8"),
            "download_url": f"/api/dossiers/{row.id}/versions/{item.id}/file",
        }
        if material
        else None,
        "missing": missing(data, bool(material)),
        "versions": [
            {
                "id": v.id,
                "number": v.version_no,
                "title": v.data_json["title"],
                "created_at": v.created_at.isoformat(),
                "verified": v.id in checked,
            }
            for v in versions
        ],
        "messages": [turn_projection(db, t) for t in reversed(turns)],
    }


def gateway(db: Session, actor: Actor, body, action: str, dossier_id: str | None, execute):
    payload = body.model_dump(mode="json", exclude={"request_id"})
    if dossier_id:
        payload["dossier_id"] = dossier_id
    # Deterministic create ID also lets a replay re-check the exact private object.
    target = dossier_id or str(
        uuid5(NAMESPACE_URL, f"pivot:dossier:{actor.journal_id}:{actor.user.id}:{body.request_id}")
    )
    result = run_action(
        db,
        actor,
        str(body.request_id),
        f"dossier.{action}",
        payload,
        execute,
        revalidate_replay=lambda: load(db, actor, target),
    )
    return result


def event(db: Session, actor: Actor, row: Dossier, action: str, version_id: str):
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action=f"publishing.dossier_{action}",
        entity_id=row.id,
        details={"version_id": version_id, "revision": row.revision},
    )


@router.get("")
def list_dossiers(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    require_staff(db, actor)
    rows = db.scalars(
        select(Dossier)
        .where(Dossier.journal_id == actor.journal_id, Dossier.created_by == actor.user.id)
        .order_by(Dossier.updated_at.desc(), Dossier.id)
    ).all()
    checks = set(
        db.scalars(
            select(DossierCheck.version_id).where(DossierCheck.journal_id == actor.journal_id)
        ).all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "title": version(db, r).data_json["title"],
                "revision": r.revision,
                "version_id": r.current_version_id,
                "version_no": version(db, r).version_no,
                "verified": r.current_version_id in checks,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
    }


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
