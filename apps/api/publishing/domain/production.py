"""Actual proof files, independent author checks and authenticated local previews.

Accepted versions remain frozen; proofs are separate immutable packages. No mail,
public publication, network access, model declarations or executable HTML rendering.
"""

import hashlib
from copy import deepcopy

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from ..models import now, uid
from . import core
from .decision_models import EditorialDecision
from .files import FileValidationError, read_bytes, store_bytes, validate_upload
from .models import ActionReceipt, FileObject, FormDraft, ManuscriptVersion, StepRun, WorkItem
from .production_models import ProofPackage, ProofResponse, PublicationPreview
from .production_schemas import ConfirmProof, PreparePreview, SendProof
from .reviews import _new_confirmation, finish_task


def source(db, manuscript, flow):
    version = (
        db.get(ManuscriptVersion, flow.accepted_version_id) if flow.accepted_version_id else None
    )
    decision = db.scalar(
        select(EditorialDecision).where(
            EditorialDecision.manuscript_id == manuscript.id,
            EditorialDecision.version_id == flow.accepted_version_id,
            EditorialDecision.decision_code == "accept",
        )
    )
    if not version or not version.frozen_at or not decision or manuscript.status != "accepted":
        raise HTTPException(409, "需要主编已确认录用的确切冻结版本")
    data = core.version_data(db, version).model_dump()
    metadata = {
        key: deepcopy(data[key])
        for key in (
            "title",
            "abstract",
            "language",
            "article_type",
            "keywords",
            "funding_statement",
        )
    }
    metadata["schema_version"] = 1
    metadata["authors"] = [
        {
            key: deepcopy(author[key])
            for key in (
                "name",
                "orcid",
                "affiliations",
                "corresponding",
                "contributions",
            )
        }
        for author in data["authors"]
    ]
    return version, decision, metadata


def can_produce(db, actor, manuscript):
    return "production" in core.capabilities(db, actor, manuscript) and not core.is_conflicted(
        db, manuscript, actor.user
    )


def can_read_package(db, actor, manuscript):
    return manuscript.author_id == actor.user.id or (
        bool(core.capabilities(db, actor, manuscript) & {"production", "handling_editor", "chief"})
        and not core.is_conflicted(db, manuscript, actor.user)
    )


def require_staff_task(db, actor, manuscript, flow, stage):
    if flow.stage != stage:
        raise HTTPException(409, "此操作不属于当前制作关口")
    task = core.require_task(db, actor, manuscript, flow)
    if not can_produce(db, actor, manuscript):
        raise HTTPException(403, "只有本稿实际制作负责人可以执行")
    return task


def active_package(db, manuscript, flow):
    step = db.get(StepRun, flow.current_step_id) if flow.current_step_id else None
    package_id = step.outcome_json.get("package_id") if step else None
    package = db.get(ProofPackage, package_id) if package_id else None
    if package and (
        package.manuscript_id != manuscript.id
        or package.accepted_version_id != flow.accepted_version_id
    ):
        raise HTTPException(409, "当前校样任务的包或版本绑定无效")
    return package


def response_for(db, package):
    return (
        db.scalar(select(ProofResponse).where(ProofResponse.package_id == package.id))
        if package
        else None
    )


def binding(db, actor, manuscript, version):
    return db.scalar(
        select(FormDraft).where(
            FormDraft.manuscript_id == manuscript.id,
            FormDraft.version_id == version.id,
            FormDraft.owner_id == actor.user.id,
            FormDraft.schema_key == "production_proof",
        )
    )


def material_file(blob, filename):
    return {
        "id": blob.id,
        "filename": filename,
        "sha256": blob.sha256,
        "byte_size": blob.byte_size,
        "media_type": blob.media_type,
    }


def file_dto(file, url):
    return {
        **file,
        "check_method": "utf8_text_safety",
        "scan_status": "validated_text",
        "download_url": url,
    }


def checked_blob(blob):
    try:
        raw = read_bytes(blob.storage_key)
    except FileValidationError:
        raise HTTPException(409, "校样文件缺失或内容校验失败，请重新核对") from None
    if len(raw) != blob.byte_size or hashlib.sha256(raw).hexdigest() != blob.sha256:
        raise HTTPException(409, "校样实际内容与冻结摘要不一致")
    return raw


def upload(db, actor, manuscript_id, expected_revision, file):
    manuscript, flow = core.load_submission(db, actor, manuscript_id, write=True)
    core.require_revision(flow, expected_revision)
    require_staff_task(db, actor, manuscript, flow, "production")
    version, _, _ = source(db, manuscript, flow)
    if file.purpose != "proof":
        raise HTTPException(422, "制作文件用途必须为校样")
    try:
        validated = validate_upload(file.filename, file.content_base64)
        storage_key = store_bytes(validated.raw, validated.sha256)
    except FileValidationError:
        raise HTTPException(422, "校样必须是有效的小型UTF8 TXT或Markdown文本") from None
    blob = db.scalar(
        select(FileObject).where(
            FileObject.journal_id == manuscript.journal_id,
            FileObject.sha256 == validated.sha256,
        )
    )
    if not blob:
        blob = FileObject(
            id=uid(),
            journal_id=manuscript.journal_id,
            uploaded_by=actor.user.id,
            sha256=validated.sha256,
            byte_size=validated.byte_size,
            media_type=validated.media_type,
            storage_key=storage_key,
            original_filename=validated.filename,
        )
        db.add(blob)
        db.flush()
    draft = binding(db, actor, manuscript, version)
    if not draft:
        draft = FormDraft(
            manuscript_id=manuscript.id,
            version_id=version.id,
            owner_id=actor.user.id,
            schema_key="production_proof",
            base_revision=flow.revision,
            data_json={},
            sources_json={},
        )
        db.add(draft)
    draft.data_json = {"file": material_file(blob, validated.filename)}
    draft.revision = (draft.revision or 0) + 1
    draft.updated_at = now()
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "proof_draft_uploaded",
        {"file_id": blob.id, "sha256": blob.sha256},
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "revision": flow.revision,
        "draft_file": file_dto(
            draft.data_json["file"],
            f"/api/publishing/manuscripts/{manuscript.id}/proof-files/{blob.id}",
        ),
    }


def draft_download(db, actor, manuscript_id, file_id):
    manuscript, flow = core.load_submission(db, actor, manuscript_id)
    if not can_produce(db, actor, manuscript):
        raise HTTPException(404, "私人制作文件不存在或无权读取")
    version, _, _ = source(db, manuscript, flow)
    draft = binding(db, actor, manuscript, version)
    file = draft.data_json.get("file") if draft else None
    if not file or file["id"] != file_id:
        raise HTTPException(404, "私人制作文件不存在或无权读取")
    blob = db.get(FileObject, file_id)
    if (
        not blob
        or blob.journal_id != actor.journal_id
        or material_file(blob, file["filename"]) != file
    ):
        raise HTTPException(404, "私人制作文件不存在或无权读取")
    return blob, file["filename"], checked_blob(blob)


def revalidate_upload_receipt(db, actor, manuscript_id, request_id):
    """Case summary access cannot restore a revoked private draft response."""
    manuscript, flow = core.load_submission(db, actor, manuscript_id)
    if not can_produce(db, actor, manuscript):
        raise HTTPException(404, "私人制作回执不存在或当前权限已撤销")
    version, _, _ = source(db, manuscript, flow)
    draft = binding(db, actor, manuscript, version)
    receipt = db.scalar(
        select(ActionReceipt).where(
            ActionReceipt.user_id == actor.user.id,
            ActionReceipt.journal_id == actor.journal_id,
            ActionReceipt.request_id == request_id,
            ActionReceipt.action_type == "upload_proof",
        )
    )
    file = draft.data_json.get("file") if draft else None
    if not file or not receipt or receipt.response.get("draft_file", {}).get("id") != file["id"]:
        raise HTTPException(404, "私人校样草稿已变化或无权读取原回执")


def require_package(db, actor, package_id):
    package = db.get(ProofPackage, package_id)
    if not package or package.journal_id != actor.journal_id:
        raise HTTPException(404, "校样包不存在或无权访问")
    manuscript, flow = core.load_submission(db, actor, package.manuscript_id)
    if not can_read_package(db, actor, manuscript):
        raise HTTPException(404, "校样包不存在或无权访问")
    return package, manuscript, flow


def package_download(db, actor, package_id):
    package, _, _ = require_package(db, actor, package_id)
    blob = db.get(FileObject, package.file_object_id)
    return blob, package.display_name, checked_blob(blob)


def package_snapshot(db, package):
    blob = db.get(FileObject, package.file_object_id)
    return {
        "id": package.id,
        "accepted_version_id": package.accepted_version_id,
        "acceptance_decision_id": package.acceptance_decision_id,
        "package_no": package.package_no,
        "file": material_file(blob, package.display_name),
        "metadata_snapshot": package.metadata_snapshot,
        "material_digest": package.material_digest,
        "production_user_id": package.production_user_id,
    }


def package_digest(version_id, decision_id, metadata, file):
    return core.digest(
        {
            "accepted_version_id": version_id,
            "acceptance_decision_id": decision_id,
            "metadata_snapshot": metadata,
            "file": file,
        }
    )


def response_projection(response, package):
    if not response:
        return None
    return {
        "id": response.id,
        "package_id": package.id,
        "outcome": response.outcome,
        "notes": response.notes,
        "package_digest": package.material_digest,
        "responded_at": response.responded_at.isoformat(),
    }


def _send(db, actor, manuscript, flow, data, planned=None):
    require_staff_task(db, actor, manuscript, flow, "production")
    SendProof.model_validate(data)
    version, decision, metadata = source(db, manuscript, flow)
    core.verify_version_files(db, version)
    draft = binding(db, actor, manuscript, version)
    file = draft.data_json.get("file") if draft else None
    if not file:
        raise HTTPException(422, "请先上传实际校样文件")
    blob = db.get(FileObject, file["id"])
    if (
        not blob
        or blob.journal_id != manuscript.journal_id
        or material_file(blob, file["filename"]) != file
    ):
        raise HTTPException(409, "校样草稿文件绑定无效")
    checked_blob(blob)
    previous = active_package(db, manuscript, flow)
    if previous:
        response = response_for(db, previous)
        if not response or response.outcome != "request_corrections":
            raise HTTPException(409, "当前校样尚未要求更正，不能覆盖或重复交付")
        if db.get(FileObject, previous.file_object_id).sha256 == blob.sha256:
            raise HTTPException(422, "请根据作者更正意见上传不同内容的新校样")
    number = (
        db.scalar(
            select(func.max(ProofPackage.package_no)).where(
                ProofPackage.manuscript_id == manuscript.id
            )
        )
        or 0
    ) + 1
    package = {
        "id": planned["id"] if planned else uid(),
        "accepted_version_id": version.id,
        "acceptance_decision_id": decision.id,
        "package_no": number,
        "file": file,
        "metadata_snapshot": metadata,
        "material_digest": package_digest(version.id, decision.id, metadata, file),
        "production_user_id": actor.user.id,
    }
    return {
        "proof_package": package,
        "previous_package_id": previous.id if previous else None,
        "proof_download_url": f"/api/publishing/manuscripts/{manuscript.id}/proof-files/{blob.id}",
    }


def _respond(db, actor, manuscript, flow, data, planned=None):
    if flow.stage != "author_proof" or manuscript.author_id != actor.user.id:
        raise HTTPException(403, "只有当前稿件作者本人可以确认本包校样")
    core.require_task(db, actor, manuscript, flow)
    value = ConfirmProof.model_validate(data)
    package = active_package(db, manuscript, flow)
    if not package or value.package_id != package.id or response_for(db, package):
        raise HTTPException(409, "此校样包不是当前待确认包，或已经回应")
    checked_blob(db.get(FileObject, package.file_object_id))
    return {
        "proof_package": package_snapshot(db, package),
        "proof_response": {
            "id": planned["id"] if planned else uid(),
            "package_id": package.id,
            "accepted_version_id": package.accepted_version_id,
            "outcome": value.outcome,
            "notes": value.notes,
            "declarations": value.declarations.model_dump(),
            "package_digest": package.material_digest,
        },
        "proof_download_url": f"/api/publishing/proof-packages/{package.id}/file",
    }


def _preview(db, actor, manuscript, flow, data, planned=None):
    require_staff_task(db, actor, manuscript, flow, "preview_confirmation")
    PreparePreview.model_validate(data)
    version, decision, metadata = source(db, manuscript, flow)
    package = active_package(db, manuscript, flow)
    response = response_for(db, package)
    if not package or not response or response.outcome != "approve":
        raise HTTPException(409, "需要作者已明确通过的确切校样包")
    blob = db.get(FileObject, package.file_object_id)
    checked_blob(blob)
    file = material_file(blob, package.display_name)
    if package.metadata_snapshot != metadata or package.material_digest != package_digest(
        version.id, decision.id, metadata, file
    ):
        raise HTTPException(409, "已确认的校样包与冻结录用材料不一致")
    content = {
        "accepted_version_id": version.id,
        "package_id": package.id,
        "proof_response_id": response.id,
        "metadata_snapshot": metadata,
        "file": file,
        "local_only": True,
    }
    return {
        "preview": {
            "id": planned["id"] if planned else uid(),
            **content,
            "content_digest": core.digest(content),
            "production_user_id": actor.user.id,
        },
        "proof_package": package_snapshot(db, package),
        "proof_response": response_projection(response, package),
        "proof_download_url": f"/api/publishing/proof-packages/{package.id}/file",
    }


def prepare(db, actor, manuscript, flow, action, data):
    try:
        extra = {"send_proof": _send, "confirm_proof": _respond, "prepare_local_preview": _preview}[
            action
        ](db, actor, manuscript, flow, data)
    except ValidationError:
        raise HTTPException(422, "请明确选择校样结果并由本人核对全部必要声明") from None
    version, _, _ = source(db, manuscript, flow)
    payload = {
        "action": action,
        "stage": flow.stage,
        "version": None,
        "schema_version": 1,
        "synthetic_only": True,
        "input": deepcopy(data),
        **extra,
    }
    evidence = {
        "accepted_version_id": version.id,
        "package_digest": extra["proof_package"]["material_digest"],
        "proof_sha256": extra["proof_package"]["file"]["sha256"],
    }
    return core.store_proposal(
        db,
        actor,
        manuscript,
        flow,
        core.require_task(db, actor, manuscript, flow),
        version,
        action,
        payload,
        evidence,
    )


def _start(db, manuscript, flow, stage, user_id, version_id, package_id):
    task = core.start_step(db, manuscript, flow, stage, user_id, version_id=version_id, due_days=7)
    step = db.get(StepRun, task.step_run_id)
    step.outcome_json = {"package_id": package_id}
    db.flush()
    return task


def confirm(db, actor, manuscript, flow, proposal, reason):
    core.authorize_proposal_content(db, actor, proposal)
    task = core.require_task(db, actor, manuscript, flow, proposal.work_item_id)
    version, _, _ = source(db, manuscript, flow)
    if proposal.version_id != version.id:
        raise HTTPException(409, "录用版本已变化，请重新核对校样")
    action, payload = proposal.action_type, proposal.payload_snapshot
    key = {
        "send_proof": "proof_package",
        "confirm_proof": "proof_response",
        "prepare_local_preview": "preview",
    }[action]
    try:
        extra = {"send_proof": _send, "confirm_proof": _respond, "prepare_local_preview": _preview}[
            action
        ](db, actor, manuscript, flow, payload["input"], planned=payload[key])
    except ValidationError:
        raise HTTPException(409, "校样审核字段与当前政策不一致") from None
    evidence = {
        "accepted_version_id": version.id,
        "package_digest": extra["proof_package"]["material_digest"],
        "proof_sha256": extra["proof_package"]["file"]["sha256"],
    }
    if (
        any(payload.get(key) != value for key, value in extra.items())
        or evidence != proposal.evidence_digests
    ):
        raise HTTPException(409, "文件、校样包、作者回应或当前任务已经变化")
    confirmation = _new_confirmation(db, actor, manuscript, proposal, reason)
    package_id = extra["proof_package"]["id"]
    finish_task(db, task, confirmation.id, {"action": action, "package_id": package_id, **extra})
    if action == "send_proof":
        p = extra["proof_package"]
        package = ProofPackage(
            id=p["id"],
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            accepted_version_id=version.id,
            acceptance_decision_id=p["acceptance_decision_id"],
            package_no=p["package_no"],
            file_object_id=p["file"]["id"],
            display_name=p["file"]["filename"],
            metadata_snapshot=p["metadata_snapshot"],
            material_digest=p["material_digest"],
            production_user_id=actor.user.id,
            human_confirmation_id=confirmation.id,
        )
        db.add(package)
        db.flush()
        flow.production_editor_id = actor.user.id
        _start(db, manuscript, flow, "author_proof", manuscript.author_id, version.id, package.id)
    elif action == "confirm_proof":
        p = extra["proof_response"]
        response = ProofResponse(
            id=p["id"],
            manuscript_id=manuscript.id,
            package_id=package_id,
            author_id=actor.user.id,
            outcome=p["outcome"],
            notes=p["notes"],
            human_confirmation_id=confirmation.id,
        )
        db.add(response)
        db.flush()
        from .stages import next_assignee

        target = "preview_confirmation" if response.outcome == "approve" else "production"
        who = next_assignee(db, manuscript, flow, target)
        _start(db, manuscript, flow, target, who, version.id, package_id)
    else:
        p = extra["preview"]
        preview = PublicationPreview(
            id=p["id"],
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            accepted_version_id=version.id,
            package_id=package_id,
            proof_response_id=p["proof_response_id"],
            metadata_snapshot=p["metadata_snapshot"],
            file_object_id=p["file"]["id"],
            display_name=p["file"]["filename"],
            content_digest=p["content_digest"],
            production_user_id=actor.user.id,
            human_confirmation_id=confirmation.id,
        )
        db.add(preview)
        db.flush()
        flow.stage = "preview_ready"
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "production_confirmed",
        {
            "action": action,
            "confirmation_id": confirmation.id,
            "package_id": package_id,
            "accepted_version_id": version.id,
            "stage": flow.stage,
        },
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "stage": flow.stage,
        "revision": flow.revision,
        "confirmation_id": confirmation.id,
    }


def projection(db, actor, manuscript, flow):
    owner = manuscript.author_id == actor.user.id
    producer = can_produce(db, actor, manuscript)
    if not flow.accepted_version_id or not (owner or producer):
        return None
    version, decision, metadata = source(db, manuscript, flow)
    packages = []
    for package in db.scalars(
        select(ProofPackage)
        .where(
            ProofPackage.manuscript_id == manuscript.id,
            ProofPackage.accepted_version_id == version.id,
        )
        .order_by(ProofPackage.package_no)
    ):
        package_data = package_snapshot(db, package)
        package_data.pop("production_user_id")
        package_data["file"] = file_dto(
            package_data["file"], f"/api/publishing/proof-packages/{package.id}/file"
        )
        packages.append(
            {
                **package_data,
                "created_at": package.created_at.isoformat(),
                "response": response_projection(response_for(db, package), package),
            }
        )
    preview = db.scalar(
        select(PublicationPreview).where(
            PublicationPreview.manuscript_id == manuscript.id,
            PublicationPreview.accepted_version_id == version.id,
        )
    )
    active = active_package(db, manuscript, flow)
    result = {
        "mode": "author" if owner else "production",
        "accepted_version_id": version.id,
        "acceptance_decision_id": decision.id,
        "metadata_snapshot": metadata,
        "metadata_digest": core.digest(metadata),
        "active_package_id": active.id if active else None,
        "packages": packages,
        "preview": {
            "id": preview.id,
            "url": f"/publishing/preview/{preview.id}",
            "content_digest": preview.content_digest,
            "created_at": preview.created_at.isoformat(),
            "local_only": True,
        }
        if preview
        else None,
    }
    if not owner:
        draft = binding(db, actor, manuscript, version)
        file = draft.data_json.get("file") if draft else None
        result.update(
            {
                "can_upload_proof": flow.stage == "production"
                and bool(
                    db.scalar(
                        select(WorkItem.id).where(
                            WorkItem.step_run_id == flow.current_step_id,
                            WorkItem.kind == "production",
                            WorkItem.assignee_id == actor.user.id,
                            WorkItem.status == "pending",
                        )
                    )
                ),
                "draft_file": file_dto(
                    file, f"/api/publishing/manuscripts/{manuscript.id}/proof-files/{file['id']}"
                )
                if file
                else None,
                "accepted_materials": [
                    f
                    for f in core.files_for_version(db, version.id)
                    if f["purpose"] == "manuscript"
                ],
            }
        )
    return result


def visibility_scope(db, actor, manuscript, flow):
    authorized = can_read_package(db, actor, manuscript)
    producer = can_produce(db, actor, manuscript)
    package_ids = (
        list(
            db.scalars(
                select(ProofPackage.id)
                .where(
                    ProofPackage.manuscript_id == manuscript.id,
                )
                .order_by(ProofPackage.id)
            )
        )
        if authorized
        else []
    )
    draft_ids = []
    if producer and flow.accepted_version_id:
        version = db.get(ManuscriptVersion, flow.accepted_version_id)
        draft = binding(db, actor, manuscript, version)
        if draft and draft.data_json.get("file"):
            draft_ids = [draft.data_json["file"]["id"]]
    return {
        "production_private": producer,
        "private_proof_file_ids": draft_ids,
        "proof_package_ids": package_ids,
        "author_feedback": manuscript.author_id == actor.user.id,
    }


def preview_projection(db, actor, preview_id):
    preview = db.get(PublicationPreview, preview_id)
    if not preview or preview.journal_id != actor.journal_id:
        raise HTTPException(404, "本地预览不存在或无权访问")
    package, manuscript, flow = require_package(db, actor, preview.package_id)
    response = db.get(ProofResponse, preview.proof_response_id)
    blob = db.get(FileObject, preview.file_object_id)
    file = material_file(blob, preview.display_name)
    content = {
        "accepted_version_id": preview.accepted_version_id,
        "package_id": package.id,
        "proof_response_id": response.id,
        "metadata_snapshot": preview.metadata_snapshot,
        "file": file,
        "local_only": True,
    }
    if (
        response.package_id != package.id
        or response.outcome != "approve"
        or package.accepted_version_id != preview.accepted_version_id
        or core.digest(content) != preview.content_digest
    ):
        raise HTTPException(409, "本地预览的固定包、作者确认或内容摘要不一致")
    return {
        "id": preview.id,
        "manuscript_id": manuscript.id,
        "number": flow.number,
        **content,
        "file": file_dto(file, f"/api/publishing/proof-packages/{package.id}/file"),
        "text": checked_blob(blob).decode("utf-8"),
        "content_digest": preview.content_digest,
        "created_at": preview.created_at.isoformat(),
        "proof_approved_at": response.responded_at.isoformat(),
        "formally_published": False,
        "manuscript_status": manuscript.status,
    }
