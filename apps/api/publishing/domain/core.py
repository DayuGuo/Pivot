"""Object policy, normalized projections and deterministic draft action gateway."""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, delete, exists, func, or_, select, text
from sqlalchemy.orm import Session

from ..audit import record
from ..models import LoginSession, Manuscript, Membership, User, now, uid
from ..security import Actor
from .decision_schemas import EDITORIAL_ACTIONS
from .files import FileValidationError, read_bytes
from .models import (
    ActionProposal,
    ActionReceipt,
    Assignment,
    FileObject,
    FormDraft,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    SubmissionWorkflow,
    VersionAuthor,
    VersionFile,
    WorkItem,
)
from .review_schemas import REVIEW_ACTIONS
from .schemas import IntakeData, missing_requirements

STAGE_LABELS = {
    "author_draft": "作者准备投稿",
    "precheck_completeness": "材料完整性预审",
    "similarity_review": "相似度报告人工复核",
    "technical_screening": "匿名材料筛选",
    "chief_scope": "主编范围初筛",
    "assign_editor": "分派责任编辑",
    "editor_quality": "责任编辑质量评估",
    "reviewer_selection": "寻找审稿人",
    "peer_review": "同行评审",
    "respond_review_invitation": "回应审稿邀请",
    "submit_review": "提交审稿报告",
    "editor_recommendation": "编辑汇总建议",
    "chief_decision": "负责人决定",
    "author_revision": "作者修回",
    "revision_assessment": "修回复核",
    "production": "出版制作",
    "author_proof": "作者核对校样",
    "preview_confirmation": "本地预览审核",
    "preview_ready": "本地出版预览",
    "legacy_screening": "旧版初筛记录",
    "rejected": "已确认退稿",
}
CAPABILITIES = {
    "author_draft": "author",
    "author_revision": "author",
    "author_proof": "author",
    "precheck_completeness": "precheck",
    "similarity_review": "precheck",
    "technical_screening": "precheck",
    "chief_scope": "chief",
    "assign_editor": "chief",
    "chief_decision": "chief",
    "editor_quality": "handling_editor",
    "reviewer_selection": "handling_editor",
    "peer_review": "handling_editor",
    "editor_recommendation": "handling_editor",
    "revision_assessment": "handling_editor",
    "production": "production",
    "preview_confirmation": "production",
}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def lock_request(db: Session, actor: Actor, request_id: str):
    key = int.from_bytes(
        hashlib.sha256(
            f"publishing:{actor.user.id}:{actor.journal_id}:{request_id}".encode()
        ).digest()[:8],
        signed=True,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def ensure_actor(db: Session, actor: Actor):
    # ORM entities may be refreshed after provider/lock waits; retain the request's
    # original authority rather than silently adopting a changed membership.
    identity = actor.__dict__.get("_publishing_identity")
    if identity is None:
        identity = (
            actor.user.id,
            actor.journal_id,
            actor.role,
            actor.membership.id,
            actor.session.token_hash,
        )
        actor.__dict__["_publishing_identity"] = identity
    user_id, journal_id, role, membership_id, session_hash = identity
    membership = db.execute(
        select(Membership.user_id, Membership.journal_id, Membership.role).where(
            Membership.id == membership_id
        )
    ).one_or_none()
    session = db.execute(
        select(LoginSession.user_id, LoginSession.expires_at).where(
            LoginSession.token_hash == session_hash
        )
    ).one_or_none()
    if (
        not membership
        or tuple(membership) != (user_id, journal_id, role)
        or not session
        or session.user_id != user_id
        or session.expires_at <= now()
    ):
        raise HTTPException(403, "身份、期刊或会话已变化，请重新登录")


def run_action(
    db: Session,
    actor: Actor,
    request_id: str,
    action_type: str,
    payload: dict,
    execute: Callable[[], dict],
    *,
    revalidate_replay: Callable[[], None] | None = None,
) -> dict:
    ensure_actor(db, actor)
    lock_request(db, actor, request_id)
    ensure_actor(db, actor)
    fingerprint = digest({"action": action_type, "payload": payload})
    old = db.scalar(
        select(ActionReceipt).where(
            ActionReceipt.user_id == actor.user.id,
            ActionReceipt.journal_id == actor.journal_id,
            ActionReceipt.request_id == request_id,
        )
    )
    if old:
        if old.action_type != action_type or old.input_digest != fingerprint:
            raise HTTPException(409, "此请求编号已用于不同内容")
        if revalidate_replay:
            revalidate_replay()
        proposal_id = payload.get("proposal_id") or old.response.get("proposal_id")
        if proposal_id:
            previous = db.get(ActionProposal, proposal_id)
            if previous:
                authorize_proposal_content(db, actor, previous)
        elif payload.get("manuscript_id"):
            load_submission(db, actor, payload["manuscript_id"])
        return old.response
    try:
        result = execute()
        ensure_actor(db, actor)
        db.add(
            ActionReceipt(
                user_id=actor.user.id,
                journal_id=actor.journal_id,
                request_id=request_id,
                action_type=action_type,
                input_digest=fingerprint,
                response=result,
            )
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def capabilities(db: Session, actor: Actor, manuscript: Manuscript) -> set[str]:
    rows = db.scalars(
        select(Assignment).where(
            Assignment.manuscript_id == manuscript.id,
            Assignment.journal_id == actor.journal_id,
            Assignment.user_id == actor.user.id,
            Assignment.starts_at <= now(),
            (Assignment.ends_at.is_(None) | (Assignment.ends_at > now())),
        )
    ).all()
    allowed_for_role = {
        "author": {"author"},
        "editor": {"author", "precheck", "handling_editor"},
        "chief_editor": {"author", "chief"},
        "production_editor": {"author", "production"},
        "reviewer": {"author", "reviewer"},
    }.get(actor.role, set())
    found = {row.capability for row in rows if row.capability in allowed_for_role}
    if manuscript.author_id == actor.user.id:
        found.add("author")
    return found


def can_view(db: Session, actor: Actor, manuscript: Manuscript, flow: SubmissionWorkflow) -> bool:
    if manuscript.journal_id != actor.journal_id or flow.journal_id != actor.journal_id:
        return False
    if manuscript.author_id == actor.user.id:
        return True
    if flow.stage == "author_draft":
        return False
    if actor.role == "reviewer":
        from .review_access import own_invitation

        if own_invitation(db, actor, manuscript.id):
            return True
    if actor.role == "chief_editor":
        return True
    return bool(
        capabilities(db, actor, manuscript)
        & {"author", "precheck", "handling_editor", "chief", "production"}
    )


def load_submission(db: Session, actor: Actor, manuscript_id: str, *, write=False):
    query = select(Manuscript).where(
        Manuscript.id == manuscript_id, Manuscript.journal_id == actor.journal_id
    )
    if write:
        query = query.with_for_update()
    manuscript = db.scalar(query.execution_options(populate_existing=True))
    if write:
        ensure_actor(db, actor)
    flow = db.scalar(
        select(SubmissionWorkflow)
        .where(SubmissionWorkflow.manuscript_id == manuscript_id)
        .execution_options(populate_existing=True)
    )
    if not manuscript or not flow or not can_view(db, actor, manuscript, flow):
        raise HTTPException(404, "稿件不存在或无权访问")
    if write and flow.is_legacy:
        raise HTTPException(409, "此记录来自旧版原型，不能补造审核历史；请创建新投稿")
    return manuscript, flow


def require_revision(flow: SubmissionWorkflow, expected: int):
    if flow.revision != expected:
        raise HTTPException(409, "稿件已更新，请重新载入后审核或保存")


def require_task(
    db: Session,
    actor: Actor,
    manuscript: Manuscript,
    flow: SubmissionWorkflow,
    task_id: str | None = None,
):
    query = select(WorkItem).where(
        WorkItem.manuscript_id == manuscript.id,
        WorkItem.journal_id == actor.journal_id,
        WorkItem.assignee_id == actor.user.id,
        or_(
            WorkItem.status == "pending",
            and_(WorkItem.kind == "peer_review", WorkItem.status == "waiting"),
        ),
    )
    if task_id:
        query = query.where(WorkItem.id == task_id)
    else:
        query = query.where(WorkItem.step_run_id == flow.current_step_id)
    task = db.scalar(query)
    if task and task.kind in {"respond_review_invitation", "submit_review"}:
        from . import review_access

        if task.kind == "respond_review_invitation":
            from .review_models import ReviewRound

            invitation = review_access.require_invitation(
                db, actor, task.review_invitation_id, manuscript.id
            )
            if (
                invitation.status != "pending"
                or db.get(ReviewRound, invitation.round_id).status != "open"
            ):
                raise HTTPException(403, "此邀请已经处理或轮次已结束")
        else:
            review_access.require_report(db, actor, task.review_report_id, write=True)
        return task
    required = CAPABILITIES.get(task.kind if task else "")
    if not task or not required or required not in capabilities(db, actor, manuscript):
        raise HTTPException(403, "当前账号不是此关口的负责人")
    if required != "author" and is_conflicted(db, manuscript, actor.user):
        raise HTTPException(403, "作者不能审核自己的稿件，请由独立负责人处理")
    return task


def is_conflicted(db: Session, manuscript: Manuscript, user: User) -> bool:
    if manuscript.author_id == user.id:
        return True
    # A match is only a conflict signal, never an access grant. Preserve conflicts
    # against historical authorship, including authors without linked accounts.
    return bool(
        db.scalar(
            select(VersionAuthor.id)
            .where(
                VersionAuthor.manuscript_id == manuscript.id,
                or_(
                    VersionAuthor.linked_user_id == user.id,
                    func.lower(VersionAuthor.email) == user.email.casefold(),
                ),
            )
            .limit(1)
        )
    )


def version_data(db: Session, version: ManuscriptVersion) -> IntakeData:
    authors = db.scalars(
        select(VersionAuthor)
        .where(VersionAuthor.version_id == version.id)
        .order_by(VersionAuthor.ordinal)
    ).all()
    metadata = version.metadata_json or {}
    return IntakeData.model_validate(
        {
            "title": version.title,
            "abstract": version.abstract,
            "language": version.language,
            "article_type": version.article_type,
            "keywords": metadata.get("keywords", []),
            "funding_statement": metadata.get("funding_statement", ""),
            "declarations": metadata.get("declarations", {}),
            "authors": [
                {
                    "name": a.name,
                    "email": a.email,
                    "orcid": a.orcid,
                    "affiliations": a.affiliations,
                    "corresponding": a.corresponding,
                    "contributions": a.contributions,
                }
                for a in authors
            ],
        }
    )


def files_for_version(db: Session, version_id: str) -> list[dict]:
    pairs = db.execute(
        select(VersionFile, FileObject)
        .join(FileObject, VersionFile.file_object_id == FileObject.id)
        .where(VersionFile.version_id == version_id)
        .order_by(VersionFile.purpose)
    ).all()
    return [
        {
            "id": link.id,
            "purpose": link.purpose,
            "visibility": link.visibility,
            "name": link.display_name,
            "sha256": blob.sha256,
            "byte_size": blob.byte_size,
            "media_type": blob.media_type,
            "check_method": blob.check_method,
            "scan_status": blob.scan_status,
            "download_url": f"/api/publishing/files/{link.id}",
        }
        for link, blob in pairs
    ]


def version_snapshot(db: Session, version: ManuscriptVersion) -> dict:
    if version.provenance == "legacy":
        authors = db.scalars(
            select(VersionAuthor)
            .where(VersionAuthor.version_id == version.id)
            .order_by(VersionAuthor.ordinal)
        ).all()
        return {
            "id": version.id,
            "version_no": version.version_no,
            "data": {
                "title": version.title,
                "abstract": version.abstract,
                "language": version.language,
                "article_type": version.article_type,
                "authors": [
                    {"name": a.name, "email": a.email, "corresponding": a.corresponding}
                    for a in authors
                ],
                "legacy_metadata": version.metadata_json,
            },
            "files": files_for_version(db, version.id),
            "frozen_at": version.frozen_at.isoformat() if version.frozen_at else None,
            "provenance": "legacy",
        }
    return {
        "id": version.id,
        "version_no": version.version_no,
        "data": version_data(db, version).model_dump(),
        "files": files_for_version(db, version.id),
        "frozen_at": version.frozen_at.isoformat() if version.frozen_at else None,
        "provenance": version.provenance,
    }


def snapshot_evidence(snapshot: dict) -> dict:
    return {
        "version": snapshot["id"],
        "metadata": digest(snapshot["data"]),
        "files": {f["id"]: f["sha256"] for f in snapshot["files"]},
    }


def verify_version_files(db: Session, version: ManuscriptVersion):
    """Verify actual CAS bytes at both preparation and the confirmation gate."""
    pairs = db.execute(
        select(VersionFile, FileObject)
        .join(FileObject, VersionFile.file_object_id == FileObject.id)
        .where(VersionFile.version_id == version.id)
    ).all()
    for _, blob in pairs:
        try:
            content = read_bytes(blob.storage_key)
        except FileValidationError:
            raise HTTPException(409, "附件丢失或校验失败，请重新上传后审核") from None
        if len(content) != blob.byte_size or hashlib.sha256(content).hexdigest() != blob.sha256:
            raise HTTPException(409, "附件内容已变化，请重新上传后审核")


def form_draft(db: Session, manuscript: Manuscript, version: ManuscriptVersion):
    return db.scalar(
        select(FormDraft).where(
            FormDraft.manuscript_id == manuscript.id,
            FormDraft.version_id == version.id,
            FormDraft.owner_id == manuscript.author_id,
            FormDraft.schema_key == "intake",
        )
    )


def bump(db: Session, flow: SubmissionWorkflow):
    flow.revision += 1
    flow.updated_at = now()
    db.execute(
        text(
            "UPDATE publishing_action_proposals SET superseded_at=:at WHERE manuscript_id=:id AND superseded_at IS NULL AND NOT EXISTS (SELECT 1 FROM publishing_human_confirmations c WHERE c.proposal_id=publishing_action_proposals.id)"
        ),
        {"at": now(), "id": flow.manuscript_id},
    )


def event(db: Session, actor: Actor, manuscript_id: str, name: str, details: dict | None = None):
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action=f"publishing.{name}",
        entity_id=manuscript_id,
        details={"synthetic": True, **(details or {})},
    )


def assign(db: Session, actor: Actor, manuscript: Manuscript, user_id: str, capability: str):
    member = db.scalar(
        select(Membership).where(
            Membership.user_id == user_id, Membership.journal_id == manuscript.journal_id
        )
    )
    if not member:
        raise HTTPException(422, "负责人必须是本刊现有成员")
    expected = {
        "precheck": "editor",
        "handling_editor": "editor",
        "chief": "chief_editor",
        "production": "production_editor",
    }.get(capability)
    if expected and (
        member.role != expected or is_conflicted(db, manuscript, db.get(User, user_id))
    ):
        raise HTTPException(422, "负责人角色不符或存在已知作者利益冲突")
    row = db.scalar(
        select(Assignment).where(
            Assignment.manuscript_id == manuscript.id,
            Assignment.user_id == user_id,
            Assignment.capability == capability,
            Assignment.ends_at.is_(None),
        )
    )
    if row:
        return row
    row = Assignment(
        manuscript_id=manuscript.id,
        journal_id=manuscript.journal_id,
        user_id=user_id,
        capability=capability,
        assigned_by=actor.user.id,
        reason="本地合成样本工作流分派",
    )
    db.add(row)
    db.flush()
    return row


def staff(
    db: Session,
    journal_id: str,
    role: str,
    *,
    exclude: str | None = None,
    manuscript: Manuscript | None = None,
) -> User:
    query = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.journal_id == journal_id, Membership.role == role)
        .order_by(User.email)
    )
    if exclude:
        query = query.where(User.id != exclude)
    user = next(
        (u for u in db.scalars(query) if not manuscript or not is_conflicted(db, manuscript, u)),
        None,
    )
    if not user:
        raise HTTPException(409, "尚未配置独立的本刊负责人")
    return user


def start_step(
    db: Session,
    manuscript: Manuscript,
    flow: SubmissionWorkflow,
    step_key: str,
    assignee_id: str,
    *,
    version_id: str | None = None,
    due_days=3,
) -> WorkItem:
    cycle = (
        db.scalar(
            select(func.max(StepRun.cycle_no)).where(
                StepRun.manuscript_id == manuscript.id, StepRun.step_key == step_key
            )
        )
        or 0
    ) + 1
    step = StepRun(
        id=uid(),
        manuscript_id=manuscript.id,
        version_id=version_id,
        step_key=step_key,
        cycle_no=cycle,
        status="pending",
        policy_version=flow.policy_version,
    )
    db.add(step)
    db.flush()
    task = WorkItem(
        id=uid(),
        manuscript_id=manuscript.id,
        journal_id=manuscript.journal_id,
        step_run_id=step.id,
        version_id=version_id,
        kind=step_key,
        assignee_id=assignee_id,
        due_at=now() + timedelta(days=due_days),
    )
    db.add(task)
    db.flush()
    flow.current_step_id = step.id
    flow.stage = step_key
    return task


def new_draft(db: Session, actor: Actor, title: str = "") -> dict:
    # Any registered member can act as an author of their own submission;
    # that ownership never grants editorial confirmation of that submission.
    manuscript = Manuscript(
        id=uid(),
        journal_id=actor.journal_id,
        author_id=actor.user.id,
        editor_id=None,
        title=title or "未命名投稿",
        status="draft",
        workflow_kind="publishing",
    )
    db.add(manuscript)
    db.flush()
    version = ManuscriptVersion(
        id=uid(), manuscript_id=manuscript.id, version_no=1, title=title, created_by=actor.user.id
    )
    db.add(version)
    db.flush()
    flow = SubmissionWorkflow(
        manuscript_id=manuscript.id,
        journal_id=actor.journal_id,
        number=f"POS-{now().year}-{db.scalar(text("SELECT nextval('publishing_submission_number_seq')")):06d}",
        stage="author_draft",
        draft_version_id=version.id,
    )
    db.add(flow)
    db.flush()
    db.add(
        VersionAuthor(
            manuscript_id=manuscript.id,
            version_id=version.id,
            ordinal=0,
            name=actor.user.name,
            email=actor.user.email,
            corresponding=True,
            linked_user_id=actor.user.id,
        )
    )
    assign(db, actor, manuscript, actor.user.id, "author")
    start_step(
        db, manuscript, flow, "author_draft", actor.user.id, version_id=version.id, due_days=7
    )
    db.flush()
    data = version_data(db, version)
    db.add(
        FormDraft(
            manuscript_id=manuscript.id,
            version_id=version.id,
            owner_id=actor.user.id,
            base_revision=0,
            data_json=data.model_dump(),
            sources_json={"authors.0": {"source": "account_profile", "verified": False}},
        )
    )
    event(db, actor, manuscript.id, "draft_created", {"version_id": version.id})
    return {"manuscript_id": manuscript.id, "number": flow.number, "revision": flow.revision}


def save_intake(
    db: Session,
    actor: Actor,
    manuscript_id: str,
    expected_revision: int,
    data: IntakeData,
    *,
    sources: dict | None = None,
):
    manuscript, flow = load_submission(db, actor, manuscript_id, write=True)
    require_revision(flow, expected_revision)
    if (
        manuscript.author_id != actor.user.id
        or flow.stage not in {"author_draft", "author_revision"}
        or not flow.draft_version_id
    ):
        raise HTTPException(403, "当前稿件不处于本人可编辑的准备阶段")
    version = db.get(ManuscriptVersion, flow.draft_version_id)
    if version.frozen_at:
        raise HTTPException(409, "已提交版本不能覆盖，请创建修回版本")
    values = data.model_dump()
    previous = version_data(db, version).model_dump()
    old_links = {
        (a.name, a.email.casefold()): a.linked_user_id
        for a in db.scalars(select(VersionAuthor).where(VersionAuthor.version_id == version.id))
    }
    version.title, version.abstract, version.language, version.article_type = (
        data.title,
        data.abstract,
        data.language,
        data.article_type,
    )
    version.metadata_json = {
        k: values[k] for k in ("keywords", "funding_statement", "declarations")
    }
    version.updated_at = now()
    if flow.stage == "author_draft":
        manuscript.title = data.title or "未命名投稿"
    db.execute(delete(VersionAuthor).where(VersionAuthor.version_id == version.id))
    db.flush()
    for ordinal, author in enumerate(data.authors):
        db.add(
            VersionAuthor(
                manuscript_id=manuscript.id,
                version_id=version.id,
                ordinal=ordinal,
                linked_user_id=old_links.get((author.name, author.email.casefold())),
                **author.model_dump(),
            )
        )
    draft = form_draft(db, manuscript, version)
    draft.data_json = values
    changed = {
        key: {"source": "human_edit", "verified": False}
        for key, value in values.items()
        if (key in data.model_fields_set if sources is None else previous.get(key) != value)
    }
    draft.sources_json = {**draft.sources_json, **changed, **(sources or {})}
    draft.revision += 1
    draft.updated_at = now()
    bump(db, flow)
    event(
        db,
        actor,
        manuscript.id,
        "intake_saved",
        {"version_id": version.id, "revision": flow.revision},
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "revision": flow.revision,
        "missing": missing_requirements(
            data, {f["purpose"] for f in files_for_version(db, version.id)}
        ),
    }


def upload_file(db: Session, actor: Actor, manuscript_id: str, expected_revision: int, upload):
    from .files import FileValidationError, store_bytes, validate_upload

    manuscript, flow = load_submission(db, actor, manuscript_id, write=True)
    require_revision(flow, expected_revision)
    if manuscript.author_id != actor.user.id or flow.stage not in {
        "author_draft",
        "author_revision",
    }:
        raise HTTPException(403, "当前仅投稿负责人可添加准备稿文件")
    if upload.purpose not in {"manuscript", "blinded_manuscript", "response"}:
        raise HTTPException(422, "此准备阶段不接受该文件用途")
    version = db.get(ManuscriptVersion, flow.draft_version_id)
    if not version or version.frozen_at:
        raise HTTPException(409, "没有可编辑的准备版本")
    try:
        validated = validate_upload(upload.filename, upload.content_base64)
        storage_key = store_bytes(validated.raw, validated.sha256)
    except FileValidationError:
        raise HTTPException(422, "文件必须为有效的小型UTF8纯文本，且名称不能包含路径") from None
    blob = db.scalar(
        select(FileObject).where(
            FileObject.journal_id == actor.journal_id, FileObject.sha256 == validated.sha256
        )
    )
    if not blob:
        blob = FileObject(
            id=uid(),
            journal_id=actor.journal_id,
            uploaded_by=actor.user.id,
            sha256=validated.sha256,
            byte_size=validated.byte_size,
            media_type=validated.media_type,
            storage_key=storage_key,
            original_filename=validated.filename,
        )
        db.add(blob)
        db.flush()
    old = db.scalar(
        select(VersionFile).where(
            VersionFile.version_id == version.id, VersionFile.purpose == upload.purpose
        )
    )
    if old:
        db.delete(old)
        db.flush()
    link = VersionFile(
        id=uid(),
        manuscript_id=manuscript.id,
        journal_id=actor.journal_id,
        version_id=version.id,
        file_object_id=blob.id,
        purpose=upload.purpose,
        visibility="reviewer" if upload.purpose == "blinded_manuscript" else "author_editor",
        display_name=validated.filename,
        created_by=actor.user.id,
    )
    db.add(link)
    bump(db, flow)
    event(
        db,
        actor,
        manuscript.id,
        "file_added",
        {
            "version_id": version.id,
            "file_id": link.id,
            "sha256": blob.sha256,
            "purpose": upload.purpose,
        },
    )
    db.flush()
    return {
        "manuscript_id": manuscript.id,
        "revision": flow.revision,
        "file_id": link.id,
        "sha256": blob.sha256,
    }


def prepare_proposal(
    db: Session,
    actor: Actor,
    manuscript_id: str,
    expected_revision: int,
    action_type: str,
    action_data: dict | None = None,
):
    manuscript, flow = load_submission(db, actor, manuscript_id, write=True)
    require_revision(flow, expected_revision)
    if action_type in EDITORIAL_ACTIONS:
        from .decisions import prepare

        return prepare(db, actor, manuscript, flow, action_type, action_data or {})
    if action_type in REVIEW_ACTIONS:
        from .reviews import prepare

        return prepare(db, actor, manuscript, flow, action_type, action_data or {})
    if flow.stage == "author_revision" and flow.draft_version_id:
        from .decisions import latest_request

        if latest_request(db, manuscript.id, draft_id=flow.draft_version_id):
            raise HTTPException(422, "正式修回必须准备修回审核，不能按预审退回投稿提交")
    task = require_task(db, actor, manuscript, flow)
    if flow.stage in {"author_draft", "author_revision"} and action_type != "submit":
        raise HTTPException(422, "当前准备阶段只能准备投稿审核")
    author_submit = flow.stage in {"author_draft", "author_revision"} and action_type == "submit"
    version = db.get(
        ManuscriptVersion, flow.draft_version_id if author_submit else flow.current_version_id
    )
    snapshot = version_snapshot(db, version)
    verify_version_files(db, version)
    missing = missing_requirements(
        version_data(db, version), {f["purpose"] for f in snapshot["files"]}
    )
    if missing and author_submit:
        raise HTTPException(422, {"message": "请先补齐投稿必需信息", "missing": missing})
    if action_data and author_submit:
        raise HTTPException(422, "投稿审核不接受额外状态或身份字段")
    extra = {}
    if not author_submit:
        from pydantic import ValidationError

        from .checks import CheckPreparationError
        from .stages import prepare_stage

        try:
            extra = prepare_stage(
                db, actor, manuscript, flow, task, version, action_type, action_data or {}
            )
        except (ValidationError, CheckPreparationError):
            raise HTTPException(422, "请补齐当前关口的检查结论、材料和人工复核声明") from None
    payload = {
        "action": action_type,
        "stage": flow.stage,
        "version": snapshot,
        "schema_version": 1,
        "synthetic_only": True,
        **extra,
    }
    evidence = snapshot_evidence(snapshot)
    return store_proposal(
        db, actor, manuscript, flow, task, version, action_type, payload, evidence
    )


def store_proposal(db, actor, manuscript, flow, task, version, action_type, payload, evidence):
    """Only the gateway stores immutable proposal envelopes; never confirms them."""
    proposal = ActionProposal(
        id=uid(),
        manuscript_id=manuscript.id,
        journal_id=actor.journal_id,
        work_item_id=task.id,
        version_id=version.id,
        action_type=action_type,
        prepared_by=actor.user.id,
        responsible_user_id=task.assignee_id,
        base_revision=flow.revision,
        policy_version=flow.policy_version,
        payload_snapshot=payload,
        evidence_digests=evidence,
        digest=digest(
            {
                "payload": payload,
                "evidence": evidence,
                "revision": flow.revision,
                "policy": flow.policy_version,
            }
        ),
        expires_at=now() + timedelta(hours=2),
    )
    db.add(proposal)
    db.flush()
    event(
        db,
        actor,
        manuscript.id,
        "proposal_prepared",
        {"proposal_id": proposal.id, "action": action_type, "digest": proposal.digest},
    )
    return {
        "proposal_id": proposal.id,
        "manuscript_id": manuscript.id,
        "digest": proposal.digest,
        "review_url": f"/publishing/review/{proposal.id}",
        "requires_human_confirmation": True,
    }


def authorize_proposal_content(db, actor, proposal):
    manuscript, _ = load_submission(db, actor, proposal.manuscript_id)
    action = proposal.action_type
    caps = capabilities(db, actor, manuscript)
    if action in {"submit", "submit_revision"}:
        allowed = manuscript.author_id == actor.user.id
    elif action == "record_decision":
        allowed = "chief" in caps and not is_conflicted(db, manuscript, actor.user)
    elif action in {"recommend_decision", "assess_revision"}:
        allowed = "handling_editor" in caps and not is_conflicted(db, manuscript, actor.user)
    elif action in {"record_check", "assign_editor"}:
        required = CAPABILITIES.get(proposal.payload_snapshot["stage"])
        allowed = required in caps and not is_conflicted(db, manuscript, actor.user)
    elif action in {"open_review", "invite_reviewers", "finish_review", "cancel_review_invitation"}:
        allowed = bool(caps & {"handling_editor", "chief"}) and not is_conflicted(
            db, manuscript, actor.user
        )
    elif action in {"respond_review_invitation", "submit_review"}:
        from .review_access import require_invitation, require_report

        if action == "respond_review_invitation":
            require_invitation(
                db, actor, proposal.payload_snapshot["response"]["invitation_id"], manuscript.id
            )
        else:
            require_report(db, actor, proposal.payload_snapshot["review_report"]["id"])
        allowed = True
    else:
        allowed = False
    if not allowed:
        raise HTTPException(404, "当前权限已不允许读取该审核快照")


def proposal_projection(db: Session, actor: Actor, proposal_id: str) -> dict:
    proposal = db.get(ActionProposal, proposal_id)
    if (
        not proposal
        or proposal.journal_id != actor.journal_id
        or proposal.responsible_user_id != actor.user.id
    ):
        raise HTTPException(404, "审核材料不存在或不属于当前负责人")
    manuscript, flow = load_submission(db, actor, proposal.manuscript_id)
    authorize_proposal_content(db, actor, proposal)
    confirmation = db.scalar(
        select(HumanConfirmation).where(HumanConfirmation.proposal_id == proposal.id)
    )
    invalid = bool(
        proposal.superseded_at
        or proposal.expires_at <= now()
        or proposal.base_revision != flow.revision
        or proposal.policy_version != flow.policy_version
    )
    if not confirmation:
        try:
            require_task(db, actor, manuscript, flow, proposal.work_item_id)
        except HTTPException:
            invalid = True
    return {
        "id": proposal.id,
        "manuscript_id": proposal.manuscript_id,
        "number": flow.number,
        "action_type": proposal.action_type,
        "digest": proposal.digest,
        "base_revision": proposal.base_revision,
        "payload": proposal.payload_snapshot,
        "evidence": proposal.evidence_digests,
        "created_at": proposal.created_at.isoformat(),
        "expires_at": proposal.expires_at.isoformat(),
        "status": "confirmed" if confirmation else "expired" if invalid else "pending",
        "confirmation": {
            "id": confirmation.id,
            "outcome": confirmation.outcome,
            "confirmed_at": confirmation.confirmed_at.isoformat(),
        }
        if confirmation
        else None,
    }


def confirm_proposal(
    db: Session,
    actor: Actor,
    proposal_id: str,
    expected_revision: int,
    expected_digest: str,
    *,
    acknowledged: bool,
    reason: str = "",
):
    # This method is only called by the interactive confirmation endpoint.
    # It is intentionally absent from every model tool registry.
    initial = db.get(ActionProposal, proposal_id)
    if (
        not initial
        or initial.journal_id != actor.journal_id
        or initial.responsible_user_id != actor.user.id
    ):
        raise HTTPException(404, "审核材料不存在或不属于当前负责人")
    manuscript, flow = load_submission(db, actor, initial.manuscript_id, write=True)
    proposal = db.scalar(
        select(ActionProposal).where(ActionProposal.id == proposal_id).with_for_update()
    )
    if not acknowledged:
        raise HTTPException(422, "请在独立审核页明确核对完整内容")
    require_revision(flow, expected_revision)
    if (
        proposal.base_revision != flow.revision
        or proposal.payload_snapshot["stage"] != flow.stage
        or proposal.policy_version != flow.policy_version
        or proposal.digest != expected_digest
        or proposal.superseded_at
        or proposal.expires_at <= now()
    ):
        raise HTTPException(409, "审核内容已过期或发生变化，请重新准备")
    if db.scalar(select(HumanConfirmation).where(HumanConfirmation.proposal_id == proposal.id)):
        raise HTTPException(409, "本审核已经处理，请使用原请求编号恢复结果")
    if proposal.action_type in EDITORIAL_ACTIONS:
        from .decisions import confirm

        return confirm(db, actor, manuscript, flow, proposal, reason)
    if proposal.action_type in REVIEW_ACTIONS:
        from .reviews import confirm

        return confirm(db, actor, manuscript, flow, proposal, reason)
    task = require_task(db, actor, manuscript, flow, proposal.work_item_id)
    version = db.get(ManuscriptVersion, proposal.version_id)
    snapshot = version_snapshot(db, version)
    verify_version_files(db, version)
    if (
        snapshot != proposal.payload_snapshot["version"]
        or snapshot_evidence(snapshot) != proposal.evidence_digests
    ):
        raise HTTPException(409, "版本或附件已变化，请重新核对")
    if flow.stage not in {"author_draft", "author_revision"} or proposal.action_type != "submit":
        from .stages import confirm_stage

        return confirm_stage(db, actor, manuscript, flow, task, version, proposal, reason)
    missing = missing_requirements(
        version_data(db, version), {f["purpose"] for f in snapshot["files"]}
    )
    if missing:
        raise HTTPException(422, "投稿资料不完整，不能确认提交")
    previous_stage = flow.stage
    return_to = (
        db.get(StepRun, task.step_run_id).outcome_json.get("return_to")
        if previous_stage == "author_revision"
        else None
    )
    if previous_stage == "author_revision" and return_to not in {
        "precheck_completeness",
        "similarity_review",
        "technical_screening",
        "chief_scope",
        "editor_quality",
    }:
        raise HTTPException(409, "修回目标关口无效，请联系负责人")
    checker = staff(
        db, manuscript.journal_id, "editor", exclude=manuscript.author_id, manuscript=manuscript
    )
    chief = staff(
        db,
        manuscript.journal_id,
        "chief_editor",
        exclude=manuscript.author_id,
        manuscript=manuscript,
    )
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
    step = db.get(StepRun, task.step_run_id)
    step.status, step.completed_at, step.confirmation_id, step.outcome_json = (
        "completed",
        now(),
        confirmation.id,
        {"action": "submit", "version_id": version.id},
    )
    task.status, task.completed_at, task.confirmation_id = "completed", now(), confirmation.id
    version.content_digest = digest(snapshot_evidence(snapshot))
    version.frozen_at = now()
    manuscript.status = "submitted"
    manuscript.title = version.title
    flow.current_version_id, flow.draft_version_id, flow.submitted_at, flow.chief_id = (
        version.id,
        None,
        now(),
        chief.id,
    )
    assign(db, actor, manuscript, checker.id, "precheck")
    assign(db, actor, manuscript, chief.id, "chief")
    # Flush frozen data before the next step references it; no future edits allowed.
    db.flush()
    target = return_to or "precheck_completeness"
    if return_to:
        from .stages import next_assignee

        assignee = next_assignee(db, manuscript, flow, target)
    else:
        assignee = checker.id
    start_step(db, manuscript, flow, target, assignee, version_id=version.id)
    bump(db, flow)
    event(
        db,
        actor,
        manuscript.id,
        "submission_confirmed",
        {
            "proposal_id": proposal.id,
            "confirmation_id": confirmation.id,
            "version_id": version.id,
            "digest": version.content_digest,
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


def task_projection(task: WorkItem, flow: SubmissionWorkflow, manuscript: Manuscript) -> dict:
    return {
        "id": task.id,
        "manuscript_id": manuscript.id,
        "number": flow.number,
        "title": manuscript.title,
        "kind": task.kind,
        "label": STAGE_LABELS.get(task.kind, task.kind),
        "status": task.status,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "priority": task.priority,
        "blocking": task.blocking,
        "version_id": task.version_id,
    }


def submission_projection(db: Session, actor: Actor, manuscript_id: str, *, detail=True) -> dict:
    manuscript, flow = load_submission(db, actor, manuscript_id)
    if actor.role == "reviewer" and manuscript.author_id != actor.user.id and not flow.is_legacy:
        from .review_access import reviewer_projection

        return reviewer_projection(db, actor, manuscript, flow, detail=detail)
    caps = capabilities(db, actor, manuscript)
    active = db.scalars(
        select(WorkItem)
        .where(WorkItem.manuscript_id == manuscript.id, WorkItem.status.in_(["pending", "waiting"]))
        .order_by(WorkItem.created_at)
    ).all()
    own_tasks = [
        task_projection(t, flow, manuscript) for t in active if t.assignee_id == actor.user.id
    ]
    version_id = (
        flow.draft_version_id
        if manuscript.author_id == actor.user.id and flow.draft_version_id
        else flow.current_version_id
    )
    version = db.get(ManuscriptVersion, version_id) if version_id else None
    result = {
        "id": manuscript.id,
        "number": flow.number,
        "title": version.title if version else manuscript.title,
        "stage": flow.stage,
        "stage_label": STAGE_LABELS[flow.stage],
        "revision": flow.revision,
        "is_legacy": flow.is_legacy,
        "is_owner": manuscript.author_id == actor.user.id,
        "capabilities": sorted(caps),
        "current_version_id": flow.current_version_id,
        "draft_version_id": flow.draft_version_id if "author" in caps else None,
        "accepted_version_id": flow.accepted_version_id,
        "own_tasks": own_tasks,
        "created_at": flow.created_at.isoformat(),
        "submitted_at": flow.submitted_at.isoformat() if flow.submitted_at else None,
    }
    no_conflict = not is_conflicted(db, manuscript, actor.user)
    visibility_scope = {
        "role": actor.role,
        "manuscript_files": True,
        "staff_reports": bool(caps & {"precheck", "handling_editor", "chief"}) and no_conflict,
        "peer_reports": bool(caps & {"handling_editor", "chief"}) and no_conflict,
        "editorial_private": bool(caps & {"handling_editor", "chief"}) and no_conflict,
    }
    result["visibility_scope"] = visibility_scope
    result["visibility_fingerprint"] = digest(visibility_scope)
    result["allowed_actions"] = []
    if not flow.is_legacy and own_tasks:
        try:
            require_task(db, actor, manuscript, flow)
        except HTTPException:
            pass
        else:
            if flow.stage in {"author_draft", "author_revision"}:
                result["allowed_actions"] = [
                    {"action": "submit", "label": "准备投稿审核", "requires_human": True}
                ]
                if flow.stage == "author_revision":
                    from .decisions import latest_request

                    formal = latest_request(db, manuscript.id, draft_id=flow.draft_version_id)
                    if formal and formal.status == "requested":
                        result["allowed_actions"] = [
                            {
                                "action": "submit_revision",
                                "label": "准备修回审核",
                                "requires_human": True,
                            }
                        ]
            elif flow.stage in {"editor_recommendation", "chief_decision", "revision_assessment"}:
                action, label = {
                    "editor_recommendation": ("recommend_decision", "准备编辑建议审核"),
                    "chief_decision": ("record_decision", "准备主编决定审核"),
                    "revision_assessment": ("assess_revision", "准备修回复核审核"),
                }[flow.stage]
                result["allowed_actions"] = [
                    {"action": action, "label": label, "requires_human": True}
                ]
            elif flow.stage in {
                "precheck_completeness",
                "similarity_review",
                "technical_screening",
                "chief_scope",
                "editor_quality",
            }:
                result["allowed_actions"] = [
                    {"action": "record_check", "label": "准备检查审核", "requires_human": True}
                ]
            elif flow.stage == "assign_editor":
                result["allowed_actions"] = [
                    {"action": "assign_editor", "label": "准备编辑分派审核", "requires_human": True}
                ]
            elif flow.stage in {"reviewer_selection", "peer_review"}:
                from .reviews import staff_allowed_actions

                result["allowed_actions"] = staff_allowed_actions(db, actor, manuscript, flow)
    if not detail:
        return result
    result["versions"] = [
        {
            "id": v.id,
            "version_no": v.version_no,
            "title": v.title,
            "frozen_at": v.frozen_at.isoformat() if v.frozen_at else None,
            "provenance": v.provenance,
        }
        for v in db.scalars(
            select(ManuscriptVersion)
            .where(ManuscriptVersion.manuscript_id == manuscript.id)
            .order_by(ManuscriptVersion.version_no)
        )
        if v.frozen_at or "author" in caps
    ]
    result["version"] = version_snapshot(db, version) if version else None
    result["missing"] = (
        missing_requirements(
            version_data(db, version), {f["purpose"] for f in files_for_version(db, version.id)}
        )
        if version and not flow.is_legacy and not version.frozen_at
        else []
    )
    result["can_edit_intake"] = bool(
        not flow.is_legacy
        and manuscript.author_id == actor.user.id
        and flow.draft_version_id
        and flow.stage in {"author_draft", "author_revision"}
    )
    draft = (
        form_draft(db, manuscript, version)
        if version and manuscript.author_id == actor.user.id
        else None
    )
    result["field_sources"] = draft.sources_json if draft else {}
    from .stages import staff_projection

    result["staff_review"] = staff_projection(db, actor, manuscript, flow, version)
    from .review_access import staff_projection as peer_projection

    result["review"] = peer_projection(db, actor, manuscript, flow)
    from .decisions import projection as editorial_projection

    result["editorial"] = editorial_projection(db, actor, manuscript, flow)
    if (
        result["can_edit_intake"]
        and result["editorial"]
        and result["editorial"].get("revision_request")
        and not any(f["purpose"] == "response" for f in result["version"]["files"])
    ):
        result["missing"].append(
            {"field": "files.response", "message": "请上传逐项回应修回要求的实际回复文件"}
        )
    current_step = db.get(StepRun, flow.current_step_id) if flow.current_step_id else None
    result["return_request"] = (
        {
            "reason": current_step.outcome_json.get("reason", ""),
            "return_to": current_step.outcome_json.get("return_to"),
        }
        if current_step and flow.stage == "author_revision"
        else None
    )
    result["timeline"] = [
        {
            "id": s.id,
            "step": s.step_key,
            "label": STAGE_LABELS.get(s.step_key, s.step_key),
            "status": s.status,
            "cycle": s.cycle_no,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in db.scalars(
            select(StepRun)
            .where(StepRun.manuscript_id == manuscript.id)
            .order_by(StepRun.entered_at)
        )
    ]
    return result


def workspace(db: Session, actor: Actor):
    from .review_access import visible_condition

    role_caps = {
        "editor": {"precheck", "handling_editor"},
        "chief_editor": {"chief"},
        "production_editor": {"production"},
        "reviewer": {"reviewer"},
    }.get(actor.role, set())
    explicit_access = exists(
        select(Assignment.id).where(
            Assignment.manuscript_id == Manuscript.id,
            Assignment.journal_id == actor.journal_id,
            Assignment.user_id == actor.user.id,
            Assignment.capability.in_(role_caps | {"author"}),
            Assignment.starts_at <= now(),
            or_(Assignment.ends_at.is_(None), Assignment.ends_at > now()),
        )
    )
    visible_clause = or_(
        Manuscript.author_id == actor.user.id,
        and_(
            SubmissionWorkflow.stage != "author_draft",
            or_(actor.role == "chief_editor", explicit_access, visible_condition(actor)),
        ),
    )
    rows = db.execute(
        select(Manuscript, SubmissionWorkflow)
        .join(SubmissionWorkflow, SubmissionWorkflow.manuscript_id == Manuscript.id)
        .where(Manuscript.journal_id == actor.journal_id, visible_clause)
        .order_by(SubmissionWorkflow.updated_at.desc(), Manuscript.id)
        .limit(200)
    ).all()
    visible = [(m, w) for m, w in rows if can_view(db, actor, m, w)]
    submissions = [submission_projection(db, actor, m.id, detail=False) for m, _ in visible]
    projection_titles = {s["id"]: s["title"] for s in submissions}
    allowed = {m.id: (m, w) for m, w in visible}
    tasks = []
    for task in db.scalars(
        select(WorkItem)
        .where(
            WorkItem.journal_id == actor.journal_id,
            WorkItem.assignee_id == actor.user.id,
            WorkItem.status.in_(["pending", "waiting"]),
        )
        .order_by(
            WorkItem.priority.desc(),
            WorkItem.due_at.asc().nullslast(),
            WorkItem.created_at,
            WorkItem.id,
        )
    ):
        if task.manuscript_id in allowed and not allowed[task.manuscript_id][1].is_legacy:
            m, flow = allowed[task.manuscript_id]
            tasks.append({**task_projection(task, flow, m), "title": projection_titles[m.id]})
    return {
        "submissions": submissions,
        "tasks": tasks,
        "counts": {
            "actionable": sum(t["status"] == "pending" for t in tasks),
            "waiting": sum(t["status"] == "waiting" for t in tasks),
        },
        "synthetic_only": True,
    }
