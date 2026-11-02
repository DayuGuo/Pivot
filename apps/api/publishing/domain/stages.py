"""Sequential staff checks, evidence and assignment through the Action Gateway."""

import hashlib
from copy import deepcopy

from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import func, select

from ..models import Membership, User, now, uid
from . import core
from .checks import (
    CHECK_KINDS,
    CheckInput,
    CheckMaterial,
    CheckPreparationError,
    CheckRun,
    prepare_check,
)
from .files import FileValidationError, read_bytes, store_bytes, validate_upload
from .models import (
    Assignment,
    FileObject,
    FormDraft,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    VersionAuthor,
    VersionFile,
)
from .schemas import DeclarationsInput, StrictInput

NEXT = {
    "precheck_completeness": "similarity_review",
    "similarity_review": "technical_screening",
    "technical_screening": "chief_scope",
    "chief_scope": "assign_editor",
    "editor_quality": "reviewer_selection",
}


class EditorChoice(StrictInput):
    editor_id: str = Field(min_length=36, max_length=36)
    notes: str = Field(min_length=1, max_length=4000)


def eligible_editors(db, manuscript):
    users = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.journal_id == manuscript.journal_id, Membership.role == "editor")
        .order_by(User.email)
    ).all()
    return [
        {"id": u.id, "name": u.name, "email": u.email}
        for u in users
        if not core.is_conflicted(db, manuscript, u)
    ]


def report_binding(db, manuscript, version, user_id):
    return db.scalar(
        select(FormDraft).where(
            FormDraft.manuscript_id == manuscript.id,
            FormDraft.version_id == version.id,
            FormDraft.owner_id == user_id,
            FormDraft.schema_key == "similarity_report",
        )
    )


def checked_blob(blob):
    try:
        raw = read_bytes(blob.storage_key)
    except FileValidationError:
        raise HTTPException(409, "报告文件丢失或内容校验失败，请重新上传") from None
    if len(raw) != blob.byte_size or hashlib.sha256(raw).hexdigest() != blob.sha256:
        raise HTTPException(409, "报告文件内容校验失败")
    return raw


def report_projection(manuscript, blob, display_name):
    return {
        "id": blob.id,
        "name": display_name,
        "sha256": blob.sha256,
        "byte_size": blob.byte_size,
        "check_method": blob.check_method,
        "review_mode": "manual_review",
        "download_url": f"/api/publishing/manuscripts/{manuscript.id}/reports/{blob.id}",
    }


def upload_report(db, actor, manuscript_id, revision, upload):
    manuscript, flow = core.load_submission(db, actor, manuscript_id, write=True)
    core.require_revision(flow, revision)
    core.require_task(db, actor, manuscript, flow)
    if flow.stage != "similarity_review" or upload.purpose != "similarity_report":
        raise HTTPException(422, "仅在相似度人工复核关口上传报告")
    version = db.get(ManuscriptVersion, flow.current_version_id)
    try:
        file = validate_upload(upload.filename, upload.content_base64)
        key = store_bytes(file.raw, file.sha256)
    except FileValidationError:
        raise HTTPException(422, "报告必须为1MiB以内的UTF8 TXT或Markdown文本") from None
    blob = db.scalar(
        select(FileObject).where(
            FileObject.journal_id == actor.journal_id, FileObject.sha256 == file.sha256
        )
    )
    if not blob:
        blob = FileObject(
            id=uid(),
            journal_id=actor.journal_id,
            uploaded_by=actor.user.id,
            sha256=file.sha256,
            byte_size=file.byte_size,
            media_type=file.media_type,
            storage_key=key,
            original_filename=file.filename,
        )
        db.add(blob)
        db.flush()
    binding = report_binding(db, manuscript, version, actor.user.id)
    if not binding:
        binding = FormDraft(
            manuscript_id=manuscript.id,
            version_id=version.id,
            owner_id=actor.user.id,
            schema_key="similarity_report",
            base_revision=flow.revision,
            data_json={},
            sources_json={},
        )
        db.add(binding)
        db.flush()
    binding.data_json = {"file_object_id": blob.id, "display_name": file.filename}
    binding.revision += 1
    binding.updated_at = now()
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "manual_report_uploaded",
        {"file_object_id": blob.id, "sha256": blob.sha256},
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "revision": flow.revision,
        "report": report_projection(manuscript, blob, file.filename),
    }


def prepare_stage(db, actor, manuscript, flow, task, version, action_type, data):
    if action_type == "assign_editor" and flow.stage == "assign_editor":
        choice = EditorChoice.model_validate(data)
        selected = next(
            (user for user in eligible_editors(db, manuscript) if user["id"] == choice.editor_id),
            None,
        )
        if not selected:
            raise HTTPException(422, "请选择本刊无已知作者利益冲突的现有编辑")
        return {"input": choice.model_dump(), "editor": selected, "notes": choice.notes}
    if action_type != "record_check" or flow.stage not in CHECK_KINDS:
        raise HTTPException(422, "当前关口不支持此审核动作")
    payload = CheckInput.model_validate(data)
    report = None
    if payload.file_object_id:
        binding = report_binding(db, manuscript, version, actor.user.id)
        if not binding or binding.data_json.get("file_object_id") != payload.file_object_id:
            raise HTTPException(404, "报告不属于本人当前稿件的复核材料")
        report = db.get(FileObject, payload.file_object_id)
        if not report or report.journal_id != actor.journal_id:
            raise HTTPException(404, "报告不存在或无权访问")
        checked_blob(report)
    snapshot = core.version_snapshot(db, version)
    fields = (
        "id",
        "journal_id",
        "sha256",
        "byte_size",
        "media_type",
        "scan_status",
        "check_method",
        "original_filename",
    )
    material = CheckMaterial.model_validate(
        {
            "manuscript_id": manuscript.id,
            "journal_id": manuscript.journal_id,
            "version_id": version.id,
            "step_run_id": task.step_run_id,
            "step_key": flow.stage,
            "data": core.version_data(db, version).model_dump(),
            "files": [
                {key: f[key] for key in ("id", "purpose", "sha256", "visibility")}
                for f in snapshot["files"]
            ],
            "report": {
                key: (
                    binding.data_json["display_name"]
                    if key == "original_filename"
                    else getattr(report, key)
                )
                for key in fields
            }
            if report
            else None,
        }
    )
    prepared = prepare_check(flow.stage, payload, material)
    return {
        "input": payload.model_dump(),
        "check": prepared.model_dump(),
        "report": report_projection(manuscript, report, binding.data_json["display_name"])
        if report
        else None,
    }


def clone_for_return(db, actor, manuscript, flow, version, reason, return_to):
    number = (
        db.scalar(
            select(func.max(ManuscriptVersion.version_no)).where(
                ManuscriptVersion.manuscript_id == manuscript.id
            )
        )
        or 0
    ) + 1
    metadata = deepcopy(version.metadata_json)
    metadata["declarations"] = DeclarationsInput().model_dump()
    draft = ManuscriptVersion(
        id=uid(),
        manuscript_id=manuscript.id,
        version_no=number,
        title=version.title,
        abstract=version.abstract,
        language=version.language,
        article_type=version.article_type,
        metadata_json=metadata,
        created_by=actor.user.id,
        provenance="author_revision",
    )
    db.add(draft)
    db.flush()
    for author in db.scalars(select(VersionAuthor).where(VersionAuthor.version_id == version.id)):
        db.add(
            VersionAuthor(
                manuscript_id=manuscript.id,
                version_id=draft.id,
                ordinal=author.ordinal,
                name=author.name,
                email=author.email,
                orcid=author.orcid,
                affiliations=deepcopy(author.affiliations),
                contributions=deepcopy(author.contributions),
                corresponding=author.corresponding,
                linked_user_id=author.linked_user_id,
            )
        )
    for link in db.scalars(
        select(VersionFile).where(
            VersionFile.version_id == version.id,
            VersionFile.purpose.in_(["manuscript", "blinded_manuscript"]),
        )
    ):
        db.add(
            VersionFile(
                manuscript_id=manuscript.id,
                journal_id=manuscript.journal_id,
                version_id=draft.id,
                file_object_id=link.file_object_id,
                purpose=link.purpose,
                visibility=link.visibility,
                display_name=link.display_name,
                created_by=actor.user.id,
            )
        )
    db.flush()
    flow.draft_version_id = draft.id
    task = core.start_step(
        db,
        manuscript,
        flow,
        "author_revision",
        manuscript.author_id,
        version_id=draft.id,
        due_days=14,
    )
    step = db.get(StepRun, task.step_run_id)
    step.outcome_json = {
        "return_to": "precheck_completeness",
        "returned_from": return_to,
        "reason": reason,
        "revision_kind": "screening_return",
    }
    db.add(
        FormDraft(
            manuscript_id=manuscript.id,
            version_id=draft.id,
            owner_id=manuscript.author_id,
            base_revision=flow.revision,
            data_json=core.version_data(db, draft).model_dump(),
            sources_json={"previous_version": {"id": version.id, "verified": False}},
        )
    )
    return draft


def next_assignee(db, manuscript, flow, stage):
    capability = core.CAPABILITIES[stage]
    row = db.scalar(
        select(Assignment)
        .where(
            Assignment.manuscript_id == manuscript.id,
            Assignment.capability == capability,
            Assignment.ends_at.is_(None),
        )
        .order_by(Assignment.starts_at.desc())
    )
    if not row:
        raise HTTPException(409, "尚未配置下一关口的独立负责人")
    user = db.get(User, row.user_id)
    expected = {"precheck": "editor", "chief": "chief_editor", "handling_editor": "editor"}[
        capability
    ]
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.journal_id == manuscript.journal_id,
            Membership.role == expected,
        )
    )
    if not membership or core.is_conflicted(db, manuscript, user):
        raise HTTPException(409, "下一关口负责人已变化或存在作者利益冲突，请重新分派")
    return user.id


def confirm_stage(db, actor, manuscript, flow, task, version, proposal, reason):
    try:
        extra = prepare_stage(
            db,
            actor,
            manuscript,
            flow,
            task,
            version,
            proposal.action_type,
            proposal.payload_snapshot["input"],
        )
    except (ValidationError, CheckPreparationError):
        raise HTTPException(422, "审核内容或人工复核声明不完整") from None
    if any(proposal.payload_snapshot.get(key) != value for key, value in extra.items()):
        raise HTTPException(409, "复核材料或负责人已变化，请重新准备审核")
    confirmation = HumanConfirmation(
        id=uid(),
        manuscript_id=manuscript.id,
        proposal_id=proposal.id,
        responsible_user_id=actor.user.id,
        session_hash=actor.session.token_hash,
        digest=proposal.digest,
        outcome="confirm",
        reason=reason,
    )
    db.add(confirmation)
    db.flush()
    stage = flow.stage
    step = db.get(StepRun, task.step_run_id)
    step.status, step.completed_at, step.confirmation_id = "completed", now(), confirmation.id
    step.outcome_json = {"action": proposal.action_type, **extra}
    task.status, task.completed_at, task.confirmation_id = "completed", now(), confirmation.id
    if proposal.action_type == "record_check":
        values = {k: v for k, v in extra["check"].items() if k != "requires_human_confirmation"}
        db.add(
            CheckRun(
                id=uid(),
                manuscript_id=manuscript.id,
                journal_id=manuscript.journal_id,
                version_id=version.id,
                step_run_id=task.step_run_id,
                prepared_by=proposal.prepared_by,
                human_confirmation_id=confirmation.id,
                finalized_at=now(),
                **values,
            )
        )
        # Persist the completed prior step/check before creating the next responsibility.
        db.flush()
        if extra["check"]["outcome"] == "return":
            clone_for_return(db, actor, manuscript, flow, version, extra["check"]["reason"], stage)
        else:
            next_stage = NEXT[stage]
            who = next_assignee(db, manuscript, flow, next_stage)
            core.start_step(db, manuscript, flow, next_stage, who, version_id=version.id)
    else:
        editor_id = extra["editor"]["id"]
        for old in db.scalars(
            select(Assignment).where(
                Assignment.manuscript_id == manuscript.id,
                Assignment.capability == "handling_editor",
                Assignment.ends_at.is_(None),
            )
        ):
            old.ends_at = now()
        db.flush()
        core.assign(db, actor, manuscript, editor_id, "handling_editor")
        manuscript.editor_id = flow.assigned_editor_id = editor_id
        db.flush()
        core.start_step(db, manuscript, flow, "editor_quality", editor_id, version_id=version.id)
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "stage_confirmed",
        {
            "proposal_id": proposal.id,
            "confirmation_id": confirmation.id,
            "from": stage,
            "to": flow.stage,
            "version_id": version.id,
        },
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "number": flow.number,
        "stage": flow.stage,
        "revision": flow.revision,
        "confirmation_id": confirmation.id,
    }


def staff_projection(db, actor, manuscript, flow, version):
    if not version or flow.is_legacy:
        return None
    try:
        core.require_task(db, actor, manuscript, flow)
    except HTTPException:
        return None
    if flow.stage not in set(CHECK_KINDS) | {"assign_editor"}:
        return None
    binding = report_binding(db, manuscript, version, actor.user.id)
    blob = db.get(FileObject, binding.data_json.get("file_object_id")) if binding else None
    suggestions = notes_binding(db, manuscript, version, actor.user.id, flow.stage)
    return {
        "note_candidates": {**suggestions.data_json, **suggestions.sources_json}
        if suggestions
        else None,
        "kind": flow.stage,
        "report": report_projection(manuscript, blob, binding.data_json["display_name"])
        if blob
        else None,
        "eligible_editors": eligible_editors(db, manuscript)
        if flow.stage == "assign_editor"
        else [],
    }


def download_report(db, actor, manuscript_id, blob_id):
    manuscript, flow = core.load_submission(db, actor, manuscript_id)
    caps = core.capabilities(db, actor, manuscript)
    if not caps & {"precheck", "handling_editor", "chief"} or core.is_conflicted(
        db, manuscript, actor.user
    ):
        raise HTTPException(404, "报告不存在或无权访问")
    binding = db.scalar(
        select(FormDraft).where(
            FormDraft.manuscript_id == manuscript.id,
            FormDraft.schema_key == "similarity_report",
            FormDraft.data_json["file_object_id"].as_string() == blob_id,
        )
    )
    checked = db.scalar(
        select(CheckRun).where(
            CheckRun.manuscript_id == manuscript.id,
            CheckRun.file_object_id == blob_id,
            CheckRun.finalized_at.is_not(None),
        )
    )
    if not binding and not checked:
        raise HTTPException(404, "报告不存在或无权访问")
    blob = db.get(FileObject, blob_id)
    if not blob or blob.journal_id != actor.journal_id:
        raise HTTPException(404, "报告不存在或无权访问")
    name = (
        binding.data_json["display_name"]
        if binding
        else checked.evidence_json["report"]["original_filename"]
    )
    return blob, name, checked_blob(blob)


class CheckNotes(StrictInput):
    notes: str = Field(min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=4000)


def notes_binding(db, manuscript, version, actor_id, stage):
    return db.scalar(
        select(FormDraft).where(
            FormDraft.manuscript_id == manuscript.id,
            FormDraft.version_id == version.id,
            FormDraft.owner_id == actor_id,
            FormDraft.schema_key == "staff_notes_" + stage,
        )
    )


def save_check_notes(db, actor, manuscript_id, revision, candidates, message_id):
    """Unverified prose candidates, never a manual declaration, conclusion or approval."""
    manuscript, flow = core.load_submission(db, actor, manuscript_id, write=True)
    core.require_revision(flow, revision)
    core.require_task(db, actor, manuscript, flow)
    if flow.stage not in set(CHECK_KINDS) | {"assign_editor"}:
        raise HTTPException(422, "当前关口没有可整理的检查或分派意见")
    version = db.get(ManuscriptVersion, flow.current_version_id)
    binding = notes_binding(db, manuscript, version, actor.user.id, flow.stage)
    if not binding:
        binding = FormDraft(
            manuscript_id=manuscript.id,
            version_id=version.id,
            owner_id=actor.user.id,
            schema_key="staff_notes_" + flow.stage,
            base_revision=flow.revision,
            data_json={},
            sources_json={},
        )
        db.add(binding)
        db.flush()
    binding.data_json = candidates.model_dump()
    binding.sources_json = {"source": "ai_candidate", "verified": False, "message_id": message_id}
    binding.revision += 1
    binding.updated_at = now()
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "check_notes_suggested",
        {
            "stage": flow.stage,
            "version_id": version.id,
            "candidate_digest": core.digest(binding.data_json),
        },
    )
    db.flush()
