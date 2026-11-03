"""Deterministic peer-review gateway. Models never execute these confirmations."""

from copy import deepcopy
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from ..models import User, now, uid
from . import core
from . import review_access as access
from .models import (
    Assignment,
    FormDraft,
    HumanConfirmation,
    ManuscriptVersion,
    StepRun,
    WorkItem,
)
from .review_models import ReviewInvitation, ReviewReport, ReviewRound, ReviewRoundFile
from .review_schemas import (
    FORM,
    CancelInvitation,
    CloseReview,
    InvitationResponse,
    InviteInput,
    OpenReviewInput,
    ReportCandidates,
    ReportData,
    SubmitReport,
)


def staff_task(db, actor, manuscript, flow):
    task = core.require_task(db, actor, manuscript, flow)
    if "handling_editor" not in core.capabilities(db, actor, manuscript) or core.is_conflicted(
        db, manuscript, actor.user
    ):
        raise HTTPException(403, "本稿当前责任编辑才能管理同行评审")
    return task


def typed_task(db, actor, manuscript, flow, action, invitation=None, report=None):
    if actor.role != "reviewer":
        raise HTTPException(403, "此操作只能由收到邀请的审稿人本人完成")
    query = select(WorkItem).where(
        WorkItem.manuscript_id == manuscript.id,
        WorkItem.journal_id == actor.journal_id,
        WorkItem.assignee_id == actor.user.id,
        WorkItem.kind == action,
        WorkItem.status == "pending",
    )
    if action == "respond_review_invitation":
        query = query.where(WorkItem.review_invitation_id == invitation.id)
    else:
        query = query.where(WorkItem.review_report_id == report.id)
    task = db.scalar(query)
    if not task:
        raise HTTPException(403, "当前账号没有这项待处理评审任务")
    return task


def independent_task(
    db,
    manuscript,
    flow,
    kind,
    assignee_id,
    version_id,
    due_at,
    *,
    invitation_id=None,
    report_id=None,
):
    cycle = (
        db.scalar(
            select(func.max(StepRun.cycle_no)).where(
                StepRun.manuscript_id == manuscript.id, StepRun.step_key == kind
            )
        )
        or 0
    ) + 1
    step = StepRun(
        id=uid(),
        manuscript_id=manuscript.id,
        version_id=version_id,
        step_key=kind,
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
        kind=kind,
        assignee_id=assignee_id,
        review_invitation_id=invitation_id,
        review_report_id=report_id,
        due_at=due_at,
        status="pending",
    )
    db.add(task)
    db.flush()
    return task


def finish_task(db, task, confirmation_id, outcome, *, cancelled=False):
    task.status = "cancelled" if cancelled else "completed"
    task.completed_at = now()
    task.confirmation_id = confirmation_id
    step = db.get(StepRun, task.step_run_id)
    step.status = "cancelled" if cancelled else "completed"
    step.completed_at = now()
    step.confirmation_id = confirmation_id
    step.outcome_json = outcome
    db.flush()


def _files_for_version(db, version):
    core.verify_version_files(db, version)
    files = core.files_for_version(db, version.id)
    blinded = [
        file
        for file in files
        if file["purpose"] == "blinded_manuscript" and file["visibility"] == "reviewer"
    ]
    if len(blinded) != 1:
        raise HTTPException(422, "需要当前已冻结版本中明确供审稿人使用的匿名稿件")
    return [
        {
            "version_file_id": f["id"],
            "sha256": f["sha256"],
            "role": "blinded_manuscript",
            "display_name": "review-manuscript.md"
            if f["media_type"] == "text/markdown"
            else "review-manuscript.txt",
        }
        for f in sorted(blinded, key=lambda file: file["id"])
    ]


def _round_material(db, round):
    version = db.get(ManuscriptVersion, round.version_id)
    actual = _files_for_version(db, version)
    recorded = [
        {
            "version_file_id": f.version_file_id,
            "sha256": next(
                a["sha256"] for a in actual if a["version_file_id"] == f.version_file_id
            ),
            "role": f.role,
            "display_name": f.display_name,
        }
        for f in db.scalars(
            select(ReviewRoundFile)
            .where(ReviewRoundFile.round_id == round.id)
            .order_by(ReviewRoundFile.version_file_id)
        )
    ]
    if (
        actual != recorded
        or core.digest(recorded) != round.material_digest
        or core.digest(round.form_snapshot) != round.form_digest
    ):
        raise HTTPException(409, "本轮固定材料或评审表校验失败")
    return recorded


def _planned_review(db, actor, manuscript, flow, action, data):
    opening = action == "open_review"
    input = (OpenReviewInput if opening else InviteInput).model_validate(data)
    round = access.current_round(db, manuscript.id)
    version = db.get(ManuscriptVersion, flow.current_version_id)
    if not version or not version.frozen_at:
        raise HTTPException(409, "只有已确认冻结版本可以进入同行评审")
    if opening:
        if flow.stage != "reviewer_selection" or (round and round.status == "open"):
            raise HTTPException(409, "当前不能重复打开评审轮次")
        round_id = uid()
        round_no = (round.round_no + 1) if round else 1
        required = input.required_reports
        form = deepcopy(FORM)
        files = _files_for_version(db, version)
    else:
        if (
            not round
            or round.status != "open"
            or flow.stage not in {"reviewer_selection", "peer_review"}
        ):
            raise HTTPException(409, "当前没有可追加邀请的有效轮次")
        if round.version_id != version.id:
            raise HTTPException(409, "当前版本与已打开轮次不一致")
        round_id, round_no, required, form = (
            round.id,
            round.round_no,
            round.required_reports,
            round.form_snapshot,
        )
        files = _round_material(db, round)
    candidates = {
        user["id"]: user
        for user in access.eligible_reviewers(db, manuscript, round if not opening else None)
    }
    if opening and required > len(candidates):
        raise HTTPException(422, "当前可邀请的独立审稿人不足以满足本轮报告目标")
    if any(user_id not in candidates for user_id in input.reviewer_ids):
        raise HTTPException(422, "请选择无已知作者利益冲突且没有本轮有效邀请的本刊审稿人")
    invitations = []
    timestamp = now()
    for reviewer_id in input.reviewer_ids:
        user = candidates[reviewer_id]
        previous = (
            db.scalar(
                select(func.max(ReviewInvitation.attempt_no)).where(
                    ReviewInvitation.round_id == round_id,
                    ReviewInvitation.reviewer_id == reviewer_id,
                )
            )
            or 0
        )
        snapshot = {
            "title": version.title,
            "abstract": version.abstract,
            "instructions": input.instructions,
        }
        content = {
            "round_id": round_id,
            "version_id": version.id,
            "reviewer_id": reviewer_id,
            "invitation_snapshot": snapshot,
            "response_due_at": (timestamp + timedelta(days=input.response_due_days)).isoformat(),
            "report_due_at": (timestamp + timedelta(days=input.report_due_days)).isoformat(),
        }
        invitations.append(
            {
                "id": uid(),
                "reviewer_id": reviewer_id,
                "reviewer_name": user["name"],
                "reviewer_email": user["email"],
                "attempt_no": previous + 1,
                "invitation_snapshot": snapshot,
                "response_due_at": content["response_due_at"],
                "report_due_at": content["report_due_at"],
                "content_digest": core.digest(content),
            }
        )
    review = {
        "round_id": round_id,
        "round_no": round_no,
        "version_id": version.id,
        "required_reports": required,
        "form_snapshot": form,
        "form_digest": core.digest(form),
        "material_digest": core.digest(files),
        "files": files,
        "invitations": invitations,
    }
    return version, {"input": input.model_dump(), "review": review}


def _response(db, actor, manuscript, flow, data):
    response = InvitationResponse.model_validate(data)
    invitation = access.require_invitation(db, actor, response.invitation_id, manuscript.id)
    round = db.get(ReviewRound, invitation.round_id)
    if invitation.status != "pending" or round.status != "open":
        raise HTTPException(409, "本次邀请已处理或轮次已结束")
    if response.outcome == "accept" and invitation.response_due_at <= now():
        raise HTTPException(409, "邀请已超过响应期限，请由编辑重新安排")
    if response.outcome == "accept" and core.is_conflicted(db, manuscript, actor.user):
        raise HTTPException(403, "已知作者不能接受自己稿件的审稿邀请")
    task = typed_task(
        db, actor, manuscript, flow, "respond_review_invitation", invitation=invitation
    )
    version = db.get(ManuscriptVersion, invitation.version_id)
    summary = {
        **invitation.invitation_snapshot,
        "response_due_at": invitation.response_due_at.isoformat(),
        "report_due_at": invitation.report_due_at.isoformat(),
        "attempt_no": invitation.attempt_no,
    }
    return (
        task,
        version,
        {"input": response.model_dump(), "response": response.model_dump(), "invitation": summary},
    )


def _submit_report(db, actor, manuscript, flow, data):
    input = SubmitReport.model_validate(data)
    report, invitation = access.require_report(db, actor, input.report_id, write=True)
    if (
        invitation.manuscript_id != manuscript.id
        or report.revision != input.expected_report_revision
    ):
        raise HTTPException(409, "报告目标或修订已变化，请重新载入")
    round = db.get(ReviewRound, invitation.round_id)
    values = ReportData.model_validate(
        {
            "author_text": report.author_text,
            "editor_private_text": report.editor_private_text,
            "answers_json": report.answers_json,
            "recommendation": report.recommendation,
        }
    )
    if values.missing():
        raise HTTPException(
            422, {"message": "请完整填写本人的评审意见与建议", "missing": values.missing()}
        )
    files = _round_material(db, round)
    if report.form_digest != round.form_digest or report.form_snapshot != round.form_snapshot:
        raise HTTPException(409, "报告评审表与本轮固定表不一致")
    task = typed_task(db, actor, manuscript, flow, "submit_review", report=report)
    version = db.get(ManuscriptVersion, round.version_id)
    snapshot = {
        "id": report.id,
        "invitation_id": invitation.id,
        "form_digest": report.form_digest,
        "data": values.model_dump(),
        "content_digest": core.digest(values.model_dump()),
    }
    # The reviewer snapshot has only fixed anonymous files/form; no other invitees.
    review = {
        "round_id": round.id,
        "round_no": round.round_no,
        "version_id": round.version_id,
        "required_reports": round.required_reports,
        "form_snapshot": round.form_snapshot,
        "form_digest": round.form_digest,
        "material_digest": round.material_digest,
        "files": files,
        "invitations": [],
    }
    return task, version, {"input": input.model_dump(), "review_report": snapshot, "review": review}


def _closure(db, actor, manuscript, flow, action, data):
    input = (CloseReview if action == "finish_review" else CancelInvitation).model_validate(data)
    round = access.current_round(db, manuscript.id)
    if (
        not round
        or round.status != "open"
        or flow.stage not in {"reviewer_selection", "peer_review"}
    ):
        raise HTTPException(409, "没有可结束或管理的有效评审轮次")
    invitations = db.scalars(
        select(ReviewInvitation)
        .where(ReviewInvitation.round_id == round.id)
        .order_by(ReviewInvitation.id)
    ).all()
    reports = db.scalars(
        select(ReviewReport)
        .join(ReviewInvitation, ReviewInvitation.id == ReviewReport.invitation_id)
        .where(ReviewInvitation.round_id == round.id, ReviewReport.status == "submitted")
    ).all()
    if action == "finish_review":
        if len(reports) < round.required_reports:
            raise HTTPException(422, "本轮已提交的有效报告尚未达到既定数量")
        selected = [i for i in invitations if i.status in {"pending", "accepted"}]
        if selected and not input.cancel_pending:
            raise HTTPException(422, "请明确批准取消剩余未完成邀请和草稿任务，或继续等待")
    else:
        selected = [
            i
            for i in invitations
            if i.id == input.invitation_id and i.status in {"pending", "accepted"}
        ]
        if len(selected) != 1:
            raise HTTPException(422, "只能取消本轮尚未提交报告的有效邀请")
    cancellations = []
    for invitation in selected:
        report = db.scalar(select(ReviewReport).where(ReviewReport.invitation_id == invitation.id))
        cancellations.append(
            {
                "id": invitation.id,
                "reviewer_name": db.get(User, invitation.reviewer_id).name,
                "reviewer_email": db.get(User, invitation.reviewer_id).email,
                "status": invitation.status,
                "report_status": report.status if report else None,
                "report_revision": report.revision if report else None,
            }
        )
    version = db.get(ManuscriptVersion, round.version_id)
    _round_material(db, round)
    return version, {
        "input": input.model_dump(),
        "review_closure": {
            "round_id": round.id,
            "reason": input.reason,
            "submitted_report_ids": sorted(r.id for r in reports),
            "cancel_invitation_ids": sorted(i.id for i in selected),
        },
        "cancellations": cancellations,
    }


def prepare(db, actor, manuscript, flow, action, data):
    try:
        if action in {"respond_review_invitation", "submit_review"}:
            task, version, extra = (
                _response if action == "respond_review_invitation" else _submit_report
            )(db, actor, manuscript, flow, data)
            snapshot = None
        else:
            task = staff_task(db, actor, manuscript, flow)
            if action in {"open_review", "invite_reviewers"}:
                version, extra = _planned_review(db, actor, manuscript, flow, action, data)
            else:
                version, extra = _closure(db, actor, manuscript, flow, action, data)
            snapshot = core.version_snapshot(db, version)
        payload = {
            "action": action,
            "stage": flow.stage,
            "version": snapshot,
            "schema_version": 1,
            "synthetic_only": True,
            **extra,
        }
        evidence = {"version": version.id, "review_payload": core.digest(extra)}
        return core.store_proposal(
            db, actor, manuscript, flow, task, version, action, payload, evidence
        )
    except ValidationError:
        raise HTTPException(422, "请核对本轮审稿操作的必填字段、期限和显式选择") from None


def _new_confirmation(db, actor, manuscript, proposal, reason):
    row = HumanConfirmation(
        id=uid(),
        manuscript_id=manuscript.id,
        proposal_id=proposal.id,
        responsible_user_id=actor.user.id,
        session_hash=actor.session.token_hash,
        digest=proposal.digest,
        outcome="confirm",
        reason=reason,
    )
    db.add(row)
    db.flush()
    return row


def _validate_open_snapshot(db, actor, manuscript, flow, proposal):
    planned = proposal.payload_snapshot["review"]
    opening = proposal.action_type == "open_review"
    input = (OpenReviewInput if opening else InviteInput).model_validate(
        proposal.payload_snapshot["input"]
    )
    round = access.current_round(db, manuscript.id)
    version = db.get(ManuscriptVersion, proposal.version_id)
    if version.id != flow.current_version_id or not version.frozen_at:
        raise HTTPException(409, "本次评审的版本已变化")
    if opening:
        if flow.stage != "reviewer_selection" or (round and round.status == "open"):
            raise HTTPException(409, "已经存在开放轮次，不能重复创建")
        expected_round_no = round.round_no + 1 if round else 1
        if (
            planned["round_no"] != expected_round_no
            or planned["required_reports"] != input.required_reports
            or planned["form_snapshot"] != FORM
        ):
            raise HTTPException(409, "本轮策略或表单已变化")
        files = _files_for_version(db, version)
    else:
        if (
            not round
            or round.status != "open"
            or planned["round_id"] != round.id
            or round.version_id != version.id
        ):
            raise HTTPException(409, "当前评审轮次已变化或结束")
        if (
            planned["required_reports"] != round.required_reports
            or planned["form_snapshot"] != round.form_snapshot
            or planned["round_no"] != round.round_no
        ):
            raise HTTPException(409, "不能修改本轮已经固定的评审策略")
        files = _round_material(db, round)
    if (
        planned["version_id"] != version.id
        or planned["files"] != files
        or planned["material_digest"] != core.digest(files)
        or planned["form_digest"] != core.digest(planned["form_snapshot"])
    ):
        raise HTTPException(409, "固定评审文件或表单摘要不一致")
    candidates = {
        u["id"]: u
        for u in access.eligible_reviewers(db, manuscript, round if not opening else None)
    }
    if [i["reviewer_id"] for i in planned["invitations"]] != input.reviewer_ids:
        raise HTTPException(409, "拟邀请名单与审核快照不一致")
    if opening and planned["required_reports"] > len(candidates):
        raise HTTPException(409, "当前独立审稿人配置已不足以满足审核中的报告目标")
    for invitation in planned["invitations"]:
        user = candidates.get(invitation["reviewer_id"])
        if not user or (user["name"], user["email"]) != (
            invitation["reviewer_name"],
            invitation["reviewer_email"],
        ):
            raise HTTPException(409, "审稿人身份、角色或有效邀请已变化，请重新准备")
        expected = (
            db.scalar(
                select(func.max(ReviewInvitation.attempt_no)).where(
                    ReviewInvitation.round_id == planned["round_id"],
                    ReviewInvitation.reviewer_id == user["id"],
                )
            )
            or 0
        ) + 1
        if invitation["attempt_no"] != expected:
            raise HTTPException(409, "邀请历史已经变化，请重新准备")
        response_due = datetime.fromisoformat(invitation["response_due_at"])
        report_due = datetime.fromisoformat(invitation["report_due_at"])
        if not (now() < response_due < report_due):
            raise HTTPException(409, "拟邀请的响应或报告期限已经失效")
        snapshot = {
            "title": version.title,
            "abstract": version.abstract,
            "instructions": input.instructions,
        }
        content = {
            "round_id": planned["round_id"],
            "version_id": version.id,
            "reviewer_id": user["id"],
            "invitation_snapshot": snapshot,
            "response_due_at": invitation["response_due_at"],
            "report_due_at": invitation["report_due_at"],
        }
        if (
            invitation["invitation_snapshot"] != snapshot
            or core.digest(content) != invitation["content_digest"]
        ):
            raise HTTPException(409, "拟邀请的完整内容校验失败")
    return version, round, planned


def update_wait_state(db, manuscript, flow, round):
    counts = access.round_summary(db, round)
    enough = counts["submitted_reports"] >= round.required_reports
    flow.stage = "peer_review" if counts["accepted_count"] or enough else "reviewer_selection"
    task = db.scalar(
        select(WorkItem).where(
            WorkItem.manuscript_id == manuscript.id,
            WorkItem.step_run_id == flow.current_step_id,
            WorkItem.kind == "peer_review",
            WorkItem.status.in_(["pending", "waiting"]),
        )
    )
    if task:
        task.status = (
            "pending"
            if enough or not (counts["accepted_count"] or counts["pending_count"])
            else "waiting"
        )


def _open_confirm(db, actor, manuscript, flow, proposal, confirmation, task):
    version, round, planned = _validate_open_snapshot(db, actor, manuscript, flow, proposal)
    opening = proposal.action_type == "open_review"
    if opening:
        round = ReviewRound(
            id=planned["round_id"],
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            version_id=version.id,
            round_no=planned["round_no"],
            status="initializing",
            required_reports=planned["required_reports"],
            policy_version=flow.policy_version,
            review_method="double_anonymous",
            form_key=FORM["key"],
            form_version=FORM["version"],
            form_snapshot=planned["form_snapshot"],
            form_digest=planned["form_digest"],
            material_digest=planned["material_digest"],
            opened_by=actor.user.id,
            opening_confirmation_id=confirmation.id,
            opened_at=now(),
        )
        db.add(round)
        db.flush()
        for file in planned["files"]:
            db.add(
                ReviewRoundFile(
                    id=uid(),
                    manuscript_id=manuscript.id,
                    round_id=round.id,
                    version_id=version.id,
                    version_file_id=file["version_file_id"],
                    role=file["role"],
                    display_name=file["display_name"],
                )
            )
        db.flush()
        round.status = "open"
        round.material_sealed_at = now()
        db.flush()
    for item in planned["invitations"]:
        invitation = ReviewInvitation(
            id=item["id"],
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            round_id=round.id,
            version_id=version.id,
            reviewer_id=item["reviewer_id"],
            attempt_no=item["attempt_no"],
            status="pending",
            invited_by=actor.user.id,
            invitation_snapshot=item["invitation_snapshot"],
            content_digest=item["content_digest"],
            policy_version=flow.policy_version,
            response_due_at=datetime.fromisoformat(item["response_due_at"]),
            report_due_at=datetime.fromisoformat(item["report_due_at"]),
            invitation_confirmation_id=confirmation.id,
            invited_at=now(),
            conflict_status="unanswered",
            response_notes="",
        )
        db.add(invitation)
        db.flush()
        independent_task(
            db,
            manuscript,
            flow,
            "respond_review_invitation",
            invitation.reviewer_id,
            version.id,
            invitation.response_due_at,
            invitation_id=invitation.id,
        )
    if opening:
        finish_task(db, task, confirmation.id, {"action": "open_review", "round_id": round.id})
        management = core.start_step(
            db,
            manuscript,
            flow,
            "peer_review",
            actor.user.id,
            version_id=version.id,
            due_days=proposal.payload_snapshot["input"]["report_due_days"] + 1,
        )
        management.due_at = max(
            datetime.fromisoformat(i["report_due_at"]) for i in planned["invitations"]
        ) + timedelta(days=1)
    update_wait_state(db, manuscript, flow, round)
    return round


def _response_confirm(db, actor, manuscript, flow, proposal, confirmation, task):
    _, version, extra = _response(db, actor, manuscript, flow, proposal.payload_snapshot["input"])
    if any(proposal.payload_snapshot.get(key) != value for key, value in extra.items()):
        raise HTTPException(409, "邀请或回应内容已变化，请重新审核")
    response = extra["response"]
    invitation = db.get(ReviewInvitation, response["invitation_id"])
    invitation.status = "accepted" if response["outcome"] == "accept" else "declined"
    invitation.responded_at = now()
    invitation.response_confirmation_id = confirmation.id
    invitation.conflict_status = response["conflict_status"]
    invitation.response_notes = response["notes"]
    if invitation.status == "accepted":
        invitation.accepted_at = now()
    else:
        invitation.declined_at = now()
    db.flush()
    round = db.get(ReviewRound, invitation.round_id)
    if invitation.status == "accepted":
        grant = Assignment(
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            user_id=actor.user.id,
            capability="reviewer",
            review_invitation_id=invitation.id,
            assigned_by=actor.user.id,
            reason="本人确认接受已由编辑批准的站内审稿邀请",
        )
        db.add(grant)
        db.flush()
        report = ReviewReport(
            id=uid(),
            manuscript_id=manuscript.id,
            invitation_id=invitation.id,
            status="draft",
            revision=0,
            form_snapshot=deepcopy(round.form_snapshot),
            form_digest=round.form_digest,
            author_text="",
            editor_private_text="",
            answers_json={},
            recommendation="unanswered",
        )
        db.add(report)
        db.flush()
        independent_task(
            db,
            manuscript,
            flow,
            "submit_review",
            actor.user.id,
            version.id,
            invitation.report_due_at,
            report_id=report.id,
        )
    finish_task(
        db,
        task,
        confirmation.id,
        {
            "action": "respond_review_invitation",
            "invitation_id": invitation.id,
            "outcome": response["outcome"],
        },
    )
    update_wait_state(db, manuscript, flow, round)
    return round


def _report_confirm(db, actor, manuscript, flow, proposal, confirmation, task):
    _, _, extra = _submit_report(db, actor, manuscript, flow, proposal.payload_snapshot["input"])
    if any(proposal.payload_snapshot.get(key) != value for key, value in extra.items()):
        raise HTTPException(409, "报告内容或固定材料已经变化，请重新审核")
    report = db.get(ReviewReport, extra["review_report"]["id"])
    invitation = db.get(ReviewInvitation, report.invitation_id)
    report.status = "submitted"
    report.revision += 1
    report.submitted_at = now()
    report.human_confirmation_id = confirmation.id
    report.content_digest = extra["review_report"]["content_digest"]
    db.flush()
    invitation.status = "submitted"
    invitation.completed_at = now()
    invitation.terminal_confirmation_id = confirmation.id
    db.flush()
    finish_task(
        db,
        task,
        confirmation.id,
        {"action": "submit_review", "report_id": report.id, "round_id": invitation.round_id},
    )
    round = db.get(ReviewRound, invitation.round_id)
    update_wait_state(db, manuscript, flow, round)
    return round


def _cancel_one(db, manuscript, invitation, confirmation):
    invitation.status = "cancelled"
    invitation.cancelled_at = now()
    invitation.terminal_confirmation_id = confirmation.id
    db.flush()
    for grant in db.scalars(
        select(Assignment).where(
            Assignment.review_invitation_id == invitation.id, Assignment.ends_at.is_(None)
        )
    ):
        grant.ends_at = now()
    report = db.scalar(select(ReviewReport).where(ReviewReport.invitation_id == invitation.id))
    if report and report.status == "draft":
        report.status = "withdrawn"
        report.revision += 1
    db.flush()
    query = select(WorkItem).where(
        WorkItem.manuscript_id == manuscript.id, WorkItem.status.in_(["pending", "waiting"])
    )
    targets = [
        task
        for task in db.scalars(query)
        if task.review_invitation_id == invitation.id
        or (report and task.review_report_id == report.id)
    ]
    for task in targets:
        finish_task(
            db,
            task,
            confirmation.id,
            {"action": "cancel_review_invitation", "invitation_id": invitation.id},
            cancelled=True,
        )


def _closure_confirm(db, actor, manuscript, flow, proposal, confirmation, task):
    _, extra = _closure(
        db, actor, manuscript, flow, proposal.action_type, proposal.payload_snapshot["input"]
    )
    if any(proposal.payload_snapshot.get(key) != value for key, value in extra.items()):
        raise HTTPException(409, "报告或未完成邀请列表已变化，请重新核对")
    closure = extra["review_closure"]
    round = db.get(ReviewRound, closure["round_id"])
    for invitation_id in closure["cancel_invitation_ids"]:
        _cancel_one(db, manuscript, db.get(ReviewInvitation, invitation_id), confirmation)
    if proposal.action_type == "finish_review":
        invitation_ids = db.scalars(
            select(ReviewInvitation.id).where(ReviewInvitation.round_id == round.id)
        ).all()
        for grant in db.scalars(
            select(Assignment).where(
                Assignment.review_invitation_id.in_(invitation_ids), Assignment.ends_at.is_(None)
            )
        ):
            grant.ends_at = now()
        db.flush()
        round.status = "closed"
        round.closed_at = now()
        round.closure_reason = closure["reason"]
        round.closing_confirmation_id = confirmation.id
        db.flush()
        finish_task(db, task, confirmation.id, {"action": "finish_review", "round_id": round.id})
        core.start_step(
            db,
            manuscript,
            flow,
            "editor_recommendation",
            actor.user.id,
            version_id=round.version_id,
        )
    else:
        update_wait_state(db, manuscript, flow, round)
    return round


def confirm(db, actor, manuscript, flow, proposal, reason):
    try:
        if proposal.action_type == "respond_review_invitation":
            task, version, _ = _response(
                db, actor, manuscript, flow, proposal.payload_snapshot["input"]
            )
        elif proposal.action_type == "submit_review":
            task, version, _ = _submit_report(
                db, actor, manuscript, flow, proposal.payload_snapshot["input"]
            )
        else:
            task = staff_task(db, actor, manuscript, flow)
            version = db.get(ManuscriptVersion, proposal.version_id)
        if task.id != proposal.work_item_id or version.id != proposal.version_id:
            raise HTTPException(409, "此审核不属于当前负责人任务或固定版本")
        if proposal.payload_snapshot.get("version") is not None:
            if core.version_snapshot(db, version) != proposal.payload_snapshot["version"]:
                raise HTTPException(409, "当前版本或文件已变化，请重新核对")
        confirmation = _new_confirmation(db, actor, manuscript, proposal, reason)
        if proposal.action_type in {"open_review", "invite_reviewers"}:
            round = _open_confirm(db, actor, manuscript, flow, proposal, confirmation, task)
        elif proposal.action_type == "respond_review_invitation":
            round = _response_confirm(db, actor, manuscript, flow, proposal, confirmation, task)
        elif proposal.action_type == "submit_review":
            round = _report_confirm(db, actor, manuscript, flow, proposal, confirmation, task)
        else:
            round = _closure_confirm(db, actor, manuscript, flow, proposal, confirmation, task)
        core.bump(db, flow)
        core.event(
            db,
            actor,
            manuscript.id,
            "review_action_confirmed",
            {
                "action": proposal.action_type,
                "proposal_id": proposal.id,
                "confirmation_id": confirmation.id,
                "round_id": round.id,
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
    except ValidationError:
        raise HTTPException(422, "审稿操作内容不完整或不符合固定表单要求") from None


def save_report(db, actor, report_id, revision, data):
    report, invitation = access.require_report(db, actor, report_id, write=True)
    manuscript, flow = core.load_submission(db, actor, invitation.manuscript_id, write=True)
    db.expire_all()
    core.ensure_actor(db, actor)
    report, invitation = access.require_report(db, actor, report_id, write=True)
    if report.revision != revision:
        raise HTTPException(409, "报告草稿已更新，请保留当前输入并载入最新版本")
    report.author_text = data.author_text
    report.editor_private_text = data.editor_private_text
    report.answers_json = data.answers_json.model_dump()
    report.recommendation = data.recommendation
    report.revision += 1
    report.updated_at = now()
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "review_draft_saved",
        {"report_id": report.id, "report_revision": report.revision},
    )
    db.flush()
    return {
        "report_id": report.id,
        "revision": report.revision,
        "manuscript_revision": flow.revision,
    }


def save_report_candidates(
    db, actor, manuscript_id, revision, candidates: ReportCandidates, message_id
):
    manuscript, flow = core.load_submission(db, actor, manuscript_id, write=True)
    core.require_revision(flow, revision)
    invitation = access.own_invitation(db, actor, manuscript.id)
    if not invitation:
        raise HTTPException(404, "没有可整理的本人报告")
    report = db.scalar(select(ReviewReport).where(ReviewReport.invitation_id == invitation.id))
    if not report:
        raise HTTPException(403, "请先由本人接受邀请并声明利益冲突")
    access.require_report(db, actor, report.id, write=True)
    form = db.scalar(
        select(FormDraft).where(
            FormDraft.owner_id == actor.user.id,
            FormDraft.version_id == invitation.version_id,
            FormDraft.schema_key == "report_" + report.id,
        )
    )
    if not form:
        form = FormDraft(
            manuscript_id=manuscript.id,
            version_id=invitation.version_id,
            owner_id=actor.user.id,
            schema_key="report_" + report.id,
            base_revision=flow.revision,
            data_json={},
            sources_json={},
        )
        db.add(form)
        db.flush()
    form.data_json = candidates.model_dump(exclude_none=True)
    form.sources_json = {"source": "ai_candidate", "verified": False, "message_id": message_id}
    form.revision += 1
    form.updated_at = now()
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "review_notes_suggested",
        {"report_id": report.id, "candidate_digest": core.digest(form.data_json)},
    )
    db.flush()


def staff_allowed_actions(db, actor, manuscript, flow):
    try:
        staff_task(db, actor, manuscript, flow)
    except HTTPException:
        return []
    round = access.current_round(db, manuscript.id)
    if not round or round.status != "open":
        return (
            [{"action": "open_review", "label": "准备站内审稿邀请", "requires_human": True}]
            if access.eligible_reviewers(db, manuscript)
            else []
        )
    actions = []
    if access.eligible_reviewers(db, manuscript, round):
        actions.append(
            {"action": "invite_reviewers", "label": "准备追加审稿邀请", "requires_human": True}
        )
    counts = access.round_summary(db, round)
    if counts["pending_count"] or counts["accepted_count"]:
        actions.append(
            {
                "action": "cancel_review_invitation",
                "label": "准备取消本次邀请审核",
                "requires_human": True,
            }
        )
    if counts["submitted_reports"] >= round.required_reports:
        actions.append(
            {"action": "finish_review", "label": "准备结束本轮评审", "requires_human": True}
        )
    return actions
