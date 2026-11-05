"""Only author-released requirements and authorized actual revision files enter comparison."""

import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import select

from . import core
from .decision_models import DecisionReportRelease, EditorialDecision, RevisionRequest
from .dossier_evidence import credential_like
from .files import FileValidationError, read_bytes
from .models import FileObject, ManuscriptVersion, VersionFile


def comparison_requested(message):
    return bool(
        re.search(r"修回|修订|revis", message, re.I)
        and re.search(r"逐条|对照|比对|比较|审稿意见|回复|compare|response", message, re.I)
    )


def point_spans(text):
    starts = [0] + [m.end() for m in re.finditer(r"\n\s*\n|\n(?=\s*(?:\d+[.)、]|[-*•]\s))", text)]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        value = text[start:end].strip()
        if not value:
            continue
        start = text.index(value, start, end)
        # Long paragraphs remain explicitly partial, not silently "fully checked".
        yield start, min(start + len(value), start + 1200), value[:1200], len(value) <= 1200


def load_revision(db, actor, mid, expected_version=None):
    manuscript, flow = core.load_submission(db, actor, mid)
    owner = manuscript.author_id == actor.user.id
    caps = core.capabilities(db, actor, manuscript)
    if not owner and (
        actor.role not in {"editor", "chief_editor"}
        or not caps & {"handling_editor", "chief"}
        or core.is_conflicted(db, manuscript, actor.user)
    ):
        raise HTTPException(
            403, "只有本稿作者或有权的责任编辑、主编可对照修回；不开放他人评审或作者草稿"
        )
    target = (
        flow.draft_version_id
        if owner and flow.stage == "author_revision"
        else flow.current_version_id
    )
    if not target:
        raise HTTPException(409, "尚无可读的修回版本，请先完成正式修回请求")
    if expected_version and expected_version != target:
        raise HTTPException(409, "对照目标不是当前可读修回版本，请重新载入")
    request = db.scalar(
        select(RevisionRequest)
        .where(
            RevisionRequest.manuscript_id == mid,
            (RevisionRequest.draft_version_id == target)
            | (RevisionRequest.submitted_version_id == target),
        )
        .order_by(RevisionRequest.request_no.desc())
        .limit(1)
    )
    if not request or (request.status == "requested" and not owner):
        raise HTTPException(409, "尚无可读的正式修回材料；需要已登记修回请求及实际修订稿和回复文件")
    decision = db.get(EditorialDecision, request.decision_id)
    if (
        not decision
        or decision.manuscript_id != mid
        or decision.journal_id != actor.journal_id
        or decision.decision_code != "request_revision"
        or decision.version_id != request.base_version_id
    ):
        raise HTTPException(409, "修回决定与原版本不一致")
    versions = []
    for vid in [request.base_version_id, target]:
        version = db.get(ManuscriptVersion, vid)
        if not version or version.manuscript_id != mid:
            raise HTTPException(409, "修回版本来源不完整")
        core.verify_version_files(db, version)
        signature = core.digest(core.snapshot_evidence(core.version_snapshot(db, version)))
        if version.frozen_at and version.content_digest != signature:
            raise HTTPException(409, "冻结版本摘要与实际材料不一致")
        versions.append((version, signature))
    if versions[0][0].version_no >= versions[1][0].version_no:
        raise HTTPException(409, "修回版本顺序不正确")
    files = {}
    for kind, version, purpose in [
        ("base", versions[0][0], "manuscript"),
        ("revised", versions[1][0], "manuscript"),
        ("response", versions[1][0], "response"),
    ]:
        pair = db.execute(
            select(VersionFile, FileObject)
            .join(FileObject, VersionFile.file_object_id == FileObject.id)
            .where(
                VersionFile.version_id == version.id,
                VersionFile.manuscript_id == mid,
                VersionFile.journal_id == actor.journal_id,
                FileObject.journal_id == actor.journal_id,
                VersionFile.purpose == purpose,
            )
        ).one_or_none()
        if not pair:
            raise HTTPException(
                409, "需要原稿、修订稿和本次逐项回复三个实际文件，不能仅凭作者声称已修改"
            )
        link, blob = pair
        try:
            raw = read_bytes(blob.storage_key)
        except FileValidationError:
            raise HTTPException(409, "修回文件完整性检查失败") from None
        if hashlib.sha256(raw).hexdigest() != blob.sha256 or len(raw) != blob.byte_size:
            raise HTTPException(409, "修回文件内容已变化")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                409, "修回对照需要已经校核的UTF-8全文，不能直接猜读二进制原件"
            ) from None
        files[kind] = {
            "id": kind,
            "kind": kind,
            "file_id": link.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "sha256": blob.sha256,
            "text": text,
        }
    requirements = [
        ("修回要求", request.author_instructions),
        ("主编给作者的决定信", decision.author_letter),
    ]
    for release in db.scalars(
        select(DecisionReportRelease)
        .where(
            DecisionReportRelease.decision_id == decision.id,
            DecisionReportRelease.manuscript_id == mid,
        )
        .order_by(DecisionReportRelease.ordinal)
    ):
        if core.digest(release.author_snapshot) != release.snapshot_digest:
            raise HTTPException(409, "已分享意见摘要不一致")
        snapshot = release.author_snapshot
        requirements.append((f"已分享意见 {release.ordinal}", snapshot.get("author_text", "")))
        for question in snapshot.get("questions", []):
            value = snapshot.get("answers", {}).get(question["key"])
            if question.get("kind") == "text" and isinstance(value, str) and value.strip():
                requirements.append((f"已分享意见 {release.ordinal} · {question['label']}", value))
    points = []
    for label, text in requirements:
        for start, end, value, complete in point_spans(text):
            points.append(
                {
                    "id": f"P{len(points) + 1:02d}",
                    "text": value,
                    "label": label,
                    "start": start,
                    "end": end,
                    "complete": complete,
                }
            )
    if not points:
        raise HTTPException(409, "没有实际向作者分享的修回要求，不以编辑私密意见要求作者回应")
    if credential_like(
        "\n".join([v["text"] for v in files.values()] + [p["text"] for p in points])
    ):
        raise HTTPException(422, "修回材料含疑似密钥，已阻止发送至模型")
    fingerprint = core.digest(
        {
            "request": request.id,
            "decision": decision.id,
            "revision": flow.revision,
            "versions": [s for _, s in versions],
            "files": {k: f["sha256"] for k, f in files.items()},
            "points": points,
            "requirements_digest": core.digest(requirements),
        }
    )
    return {
        "manuscript_id": mid,
        "request_id": request.id,
        "revision": flow.revision,
        "base_version_id": request.base_version_id,
        "revised_version_id": target,
        "rereview_required": request.rereview_required,
        "files": files,
        "points": points[:8],
        "point_count": len(points),
        "all_points_included": len(points) <= 8 and all(p["complete"] for p in points),
        "source_fingerprint": fingerprint,
    }
