"""Draft/approval invariants. Prototype deliberately contains no sending transport."""

import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record
from .models import EmailApproval, EmailDraft
from .policy import require_editor
from .security import Actor


def digest_snapshot(snapshot: dict) -> str:
    # Includes every recipient, subject, full body, and immutable attachment content hashes.
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def validate_snapshot(snapshot: dict) -> None:
    if set(snapshot) != {"to", "cc", "bcc", "subject", "body", "attachments"}:
        raise HTTPException(422, "邮件快照必须包含所有收件人、主题、正文、附件内容哈希")
    for field in ("to", "cc", "bcc"):
        recipients = snapshot[field]
        if not isinstance(recipients, list) or any(
            not isinstance(address, str)
            or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", address)
            for address in recipients
        ):
            raise HTTPException(422, "邮件收件人列表无效")
    if not snapshot["to"] or any(
        not isinstance(snapshot[field], str) for field in ("subject", "body")
    ):
        raise HTTPException(422, "完整邮件正文、主题和主收件人必需")
    if "\r" in snapshot["subject"] or "\n" in snapshot["subject"]:
        raise HTTPException(422, "邮件主题禁止包含换行")
    attachments = snapshot["attachments"]
    if not isinstance(attachments, list) or any(
        not isinstance(item, dict)
        or set(item) != {"filename", "sha256"}
        or not isinstance(item["filename"], str)
        or not item["filename"]
        or not isinstance(item["sha256"], str)
        or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
        for item in attachments
    ):
        raise HTTPException(422, "附件必须包含文件名与不可变 SHA-256 内容哈希")


def create_draft(db: Session, actor: Actor, snapshot: dict) -> EmailDraft:
    require_editor(actor)
    validate_snapshot(snapshot)
    draft = EmailDraft(
        journal_id=actor.journal_id,
        snapshot=snapshot,
        digest=digest_snapshot(snapshot),
        status="draft",
    )
    db.add(draft)
    db.flush()
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="email.drafted",
        entity_id=draft.id,
        details={"digest": draft.digest},
    )
    return draft


def lock_draft(db: Session, actor: Actor, draft: EmailDraft) -> EmailDraft:
    require_editor(actor)
    locked = db.scalar(
        select(EmailDraft)
        .where(EmailDraft.id == draft.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not locked or locked.journal_id != actor.journal_id:
        raise HTTPException(404, "邮件草稿不存在")
    return locked


def approve_draft(db: Session, actor: Actor, draft: EmailDraft) -> EmailApproval:
    # Caller is an authenticated human. This function is never in the agent tool registry.
    draft = lock_draft(db, actor, draft)
    validate_snapshot(draft.snapshot)
    approval = EmailApproval(
        draft_id=draft.id,
        approver_id=actor.user.id,
        digest=draft.digest,
        snapshot=draft.snapshot,
        valid=True,
    )
    db.add(approval)
    draft.status = "approved"
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="email.approved",
        entity_id=draft.id,
        details={"digest": draft.digest},
    )
    return approval


def revise_draft(db: Session, actor: Actor, draft: EmailDraft, snapshot: dict) -> None:
    draft = lock_draft(db, actor, draft)
    validate_snapshot(snapshot)
    draft.snapshot = snapshot
    draft.digest = digest_snapshot(snapshot)
    draft.status = "draft"
    for approval in db.scalars(select(EmailApproval).where(EmailApproval.draft_id == draft.id)):
        approval.valid = False
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="email.approval_invalidated",
        entity_id=draft.id,
        details={"digest": draft.digest},
    )


def send_email(db: Session, actor: Actor, draft: EmailDraft, request_id: str) -> None:
    draft = lock_draft(db, actor, draft)
    # Fail closed even if an environment variable is accidentally enabled. A future transport
    # must enforce snapshot-bound approval + durable outbox + idempotency + unknown outcome.
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="email.send_blocked",
        entity_id=draft.id,
        details={"request_id": request_id},
    )
    db.commit()
    raise HTTPException(403, "真实邮件发送已禁用；原型不包含外发传输器")
