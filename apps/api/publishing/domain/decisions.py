"""Confirmed editorial decisions and versioned formal revision requests.

Editorial suggestions, chief decisions and author-visible releases are separate facts.
No network or model calls, email transmission or public publication occur here.
"""

from copy import deepcopy
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from ..models import Membership, User, now, uid
from . import core
from .decision_models import DecisionReportRelease, EditorialDecision, RevisionRequest
from .decision_schemas import Assessment, Decision, Recommendation
from .models import HumanConfirmation, ManuscriptVersion, StepRun
from .review_access import current_round
from .review_models import ReviewInvitation, ReviewReport
from .reviews import _new_confirmation, finish_task
from .schemas import missing_requirements


def latest_request(db, manuscript_id, *, draft_id=None, submitted_id=None):
    query = select(RevisionRequest).where(RevisionRequest.manuscript_id == manuscript_id)
    if draft_id:
        query = query.where(RevisionRequest.draft_version_id == draft_id)
    if submitted_id:
        query = query.where(RevisionRequest.submitted_version_id == submitted_id)
    return db.scalar(query.order_by(RevisionRequest.request_no.desc()))


def completed_confirmation(db, manuscript, version_id, step_key, action):
    rows = db.scalars(
        select(StepRun)
        .where(
            StepRun.manuscript_id == manuscript.id,
            StepRun.version_id == version_id,
            StepRun.step_key == step_key,
            StepRun.status == "completed",
        )
        .order_by(StepRun.cycle_no.desc())
    )
    for step in rows:
        confirmation = db.get(HumanConfirmation, step.confirmation_id)
        proposal = db.get(core.ActionProposal, confirmation.proposal_id) if confirmation else None
        if proposal and proposal.action_type == action and proposal.version_id == version_id:
            return confirmation, proposal
    raise HTTPException(409, "缺少当前版本负责人确认的前置证据")


def basis(db, manuscript, flow):
    """An old round is evidence only through an explicit minor-revision chain."""
    round = current_round(db, manuscript.id)
    if not round or round.status != "closed":
        raise HTTPException(409, "需要已经由责任编辑结束的同行评审轮次")
    reports = list(
        db.scalars(
            select(ReviewReport)
            .join(ReviewInvitation, ReviewReport.invitation_id == ReviewInvitation.id)
            .where(ReviewInvitation.round_id == round.id, ReviewReport.status == "submitted")
            .order_by(ReviewReport.submitted_at, ReviewReport.id)
        )
    )
    if len(reports) < round.required_reports:
        raise HTTPException(409, "实际提交的报告不足，不能形成编辑决定依据")
    reassessment = None
    if round.version_id != flow.current_version_id:
        request = latest_request(db, manuscript.id, submitted_id=flow.current_version_id)
        if not request or request.status != "submitted" or request.rereview_required:
            raise HTTPException(409, "此版本需要新的评审轮次，不能沿用旧报告")
        source = db.get(EditorialDecision, request.decision_id)
        if (
            not source
            or source.version_id != request.base_version_id
            or source.basis_round_id != round.id
            or source.decision_code != "request_revision"
        ):
            raise HTTPException(409, "修回来源决定与评审依据不一致")
        reassessment, proposal = completed_confirmation(
            db, manuscript, flow.current_version_id, "revision_assessment", "assess_revision"
        )
        assessment = proposal.payload_snapshot["assessment"]
        if (
            assessment["revision_request_id"] != request.id
            or assessment["outcome"] != "ready_for_chief"
            or assessment["basis_round_id"] != round.id
        ):
            raise HTTPException(409, "当前修回复核未批准使用本轮报告")
        # Validate each immutable bridge back to the nearest actual round version.
        # A major revision before that round is irrelevant; a major after it is not.
        cursor, visited = flow.current_version_id, set()
        while cursor != round.version_id:
            if cursor in visited:
                raise HTTPException(409, "修回依据链出现循环")
            visited.add(cursor)
            link = latest_request(db, manuscript.id, submitted_id=cursor)
            decision = db.get(EditorialDecision, link.decision_id) if link else None
            if (
                not link
                or link.status != "submitted"
                or link.rereview_required
                or not decision
                or decision.version_id != link.base_version_id
                or decision.basis_round_id != round.id
            ):
                raise HTTPException(409, "修回依据链未连续连接到实际评审版本")
            _, prior = completed_confirmation(
                db, manuscript, cursor, "revision_assessment", "assess_revision"
            )
            proof = prior.payload_snapshot["assessment"]
            if (
                proof["revision_request_id"] != link.id
                or proof["outcome"] != "ready_for_chief"
                or proof["basis_round_id"] != round.id
            ):
                raise HTTPException(409, "修回链缺少每一版本的独立复核")
            base = db.get(ManuscriptVersion, link.base_version_id)
            current = db.get(ManuscriptVersion, cursor)
            if not base or not current or base.version_no >= current.version_no:
                raise HTTPException(409, "修回版本顺序无效")
            cursor = base.id
    return round, reports, reassessment


def author_report_snapshot(report):
    questions = [
        {key: question[key] for key in ("key", "label", "kind", "required")}
        for question in report.form_snapshot["questions"]
        if question["audience"] == "author"
    ]
    return {
        "author_text": report.author_text,
        "answers": {q["key"]: report.answers_json[q["key"]] for q in questions},
        "questions": questions,
    }


def staff_task(db, actor, manuscript, flow, stage):
    if flow.stage != stage:
        raise HTTPException(409, "此操作不属于稿件当前关口")
    return core.require_task(db, actor, manuscript, flow)


def _recommendation(db, manuscript, flow, value):
    round, reports, assessment = basis(db, manuscript, flow)
    return {
        "version_id": flow.current_version_id,
        "basis_round_id": round.id,
        **value.model_dump(),
        "report_digests": [
            {"report_id": r.id, "content_digest": r.content_digest, "form_digest": r.form_digest}
            for r in reports
        ],
        "reassessment_confirmation_id": assessment.id if assessment else None,
    }


def _assessment(db, manuscript, flow, value):
    request = latest_request(db, manuscript.id, submitted_id=flow.current_version_id)
    if not request or request.status != "submitted":
        raise HTTPException(409, "当前版本没有正式提交的修回请求")
    if request.rereview_required and value.outcome != "rereview":
        raise HTTPException(422, "大修需要重新送审，不能直接准备主编决定")
    source = db.get(EditorialDecision, request.decision_id)
    files = core.files_for_version(db, flow.current_version_id)
    responses = [f for f in files if f["purpose"] == "response"]
    if len(responses) != 1:
        raise HTTPException(409, "本次修回缺少确定的实际回复文件")
    return {
        "revision_request_id": request.id,
        "version_id": flow.current_version_id,
        **value.model_dump(),
        "base_version_id": request.base_version_id,
        "response_file": {"id": responses[0]["id"], "sha256": responses[0]["sha256"]},
        "basis_round_id": source.basis_round_id,
    }


def _decision(db, actor, manuscript, flow, value, *, planned=None):
    round, reports, assessment = basis(db, manuscript, flow)
    recommendation, _ = completed_confirmation(
        db, manuscript, flow.current_version_id, "editor_recommendation", "recommend_decision"
    )
    available = {r.id: r for r in reports}
    if any(rid not in available for rid in value.share_report_ids):
        raise HTTPException(422, "只能分享本次决定依据轮次中已提交的报告")
    decision_id = planned["id"] if planned else uid()
    request = None
    if value.decision_code == "request_revision":
        number = (
            db.scalar(
                select(func.max(RevisionRequest.request_no)).where(
                    RevisionRequest.manuscript_id == manuscript.id
                )
            )
            or 0
        ) + 1
        old = planned["revision_request"] if planned else None
        request = {
            "id": old["id"] if old else uid(),
            "decision_id": decision_id,
            "request_no": number,
            "base_version_id": flow.current_version_id,
            "planned_draft_version_id": old["planned_draft_version_id"] if old else uid(),
            "kind": value.revision_kind,
            "rereview_required": value.revision_kind == "major",
            "author_instructions": value.author_instructions,
            "due_at": old["due_at"]
            if old
            else (now() + timedelta(days=value.due_days)).isoformat(),
        }
        if datetime.fromisoformat(request["due_at"]) <= now():
            raise HTTPException(409, "修回期限已经过期，请重新准备")
    production = None
    if value.decision_code == "accept":
        user = core.staff(db, actor.journal_id, "production_editor", manuscript=manuscript)
        if planned:
            chosen = planned["production_assignee"]
            user = db.get(User, chosen["id"]) if chosen else None
            member = (
                db.scalar(
                    select(Membership).where(
                        Membership.user_id == user.id,
                        Membership.journal_id == actor.journal_id,
                        Membership.role == "production_editor",
                    )
                )
                if user
                else None
            )
            if not member or core.is_conflicted(db, manuscript, user):
                raise HTTPException(409, "审核中的制作负责人权限或利益冲突已变化")
        production = {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": "production_editor",
        }
    return {
        "id": decision_id,
        "version_id": flow.current_version_id,
        "basis_round_id": round.id,
        "recommendation_confirmation_id": recommendation.id,
        "reassessment_confirmation_id": assessment.id if assessment else None,
        "decision_code": value.decision_code,
        "revision_kind": value.revision_kind,
        "rationale_private": value.rationale_private,
        "author_letter": value.author_letter,
        "policy_version": flow.policy_version,
        "production_assignee": production,
        "share_reports_anonymity_reviewed": value.share_reports_anonymity_reviewed,
        "public_reports": [
            {
                "report_id": rid,
                "ordinal": index + 1,
                "author_snapshot": author_report_snapshot(available[rid]),
                "snapshot_digest": core.digest(author_report_snapshot(available[rid])),
            }
            for index, rid in enumerate(value.share_report_ids)
        ],
        "revision_request": request,
    }


def revision_payload(db, manuscript, flow, version):
    request = latest_request(db, manuscript.id, draft_id=version.id)
    if not request or request.status != "requested" or version.id != flow.draft_version_id:
        raise HTTPException(409, "此作者草稿没有有效的正式修回请求")
    missing = missing_requirements(
        core.version_data(db, version),
        {f["purpose"] for f in core.files_for_version(db, version.id)},
    )
    if not any(f["purpose"] == "response" for f in core.files_for_version(db, version.id)):
        missing.append(
            {"field": "files.response", "message": "请上传逐项回应修回要求的实际回复文件"}
        )
    if missing:
        raise HTTPException(422, {"message": "请补齐修回资料并重新确认声明", "missing": missing})
    return {
        "id": request.id,
        "decision_id": request.decision_id,
        "base_version_id": request.base_version_id,
        "draft_version_id": request.draft_version_id,
        "kind": request.kind,
        "rereview_required": request.rereview_required,
        "author_instructions": request.author_instructions,
        "due_at": request.due_at.isoformat(),
        "submitted_version_id": version.id,
    }


def _extras(db, actor, manuscript, flow, action, data, *, planned=None):
    if action == "recommend_decision":
        staff_task(db, actor, manuscript, flow, "editor_recommendation")
        return {
            "recommendation": _recommendation(
                db, manuscript, flow, Recommendation.model_validate(data)
            )
        }
    if action == "record_decision":
        staff_task(db, actor, manuscript, flow, "chief_decision")
        value = _decision(
            db, actor, manuscript, flow, Decision.model_validate(data), planned=planned
        )
        return {"decision": value, "decision_digest": core.digest(value)}
    if action == "assess_revision":
        staff_task(db, actor, manuscript, flow, "revision_assessment")
        return {"assessment": _assessment(db, manuscript, flow, Assessment.model_validate(data))}
    if action == "submit_revision":
        staff_task(db, actor, manuscript, flow, "author_revision")
        if manuscript.author_id != actor.user.id:
            raise HTTPException(403, "只有提交作者本人可以确认修回")
        if data:
            raise HTTPException(422, "修回提交不接受额外字段")
        version = db.get(ManuscriptVersion, flow.draft_version_id)
        return {"revision_request": revision_payload(db, manuscript, flow, version)}
    raise HTTPException(422, "未知编辑决定操作")


def prepare(db, actor, manuscript, flow, action, data):
    try:
        extra = _extras(db, actor, manuscript, flow, action, data)
    except ValidationError:
        raise HTTPException(422, "请完整填写本关口的人工选择、意见及声明") from None
    version_id = flow.draft_version_id if action == "submit_revision" else flow.current_version_id
    version = db.get(ManuscriptVersion, version_id)
    core.verify_version_files(db, version)
    snapshot = core.version_snapshot(db, version)
    payload = {
        "action": action,
        "stage": flow.stage,
        "version": snapshot,
        "schema_version": 1,
        "synthetic_only": True,
        "input": deepcopy(data),
        **extra,
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
        core.snapshot_evidence(snapshot),
    )


def _record_decision(db, actor, manuscript, flow, task, version, confirmation, value):
    decision = EditorialDecision(
        id=value["id"],
        manuscript_id=manuscript.id,
        journal_id=manuscript.journal_id,
        version_id=version.id,
        step_run_id=task.step_run_id,
        basis_round_id=value["basis_round_id"],
        recommendation_confirmation_id=value["recommendation_confirmation_id"],
        reassessment_confirmation_id=value["reassessment_confirmation_id"],
        decision_code=value["decision_code"],
        revision_kind=value["revision_kind"],
        rationale_private=value["rationale_private"],
        author_letter=value["author_letter"],
        policy_version=flow.policy_version,
        chief_id=actor.user.id,
        human_confirmation_id=confirmation.id,
        payload_digest=core.digest(value),
    )
    db.add(decision)
    db.flush()
    for report in value["public_reports"]:
        db.add(
            DecisionReportRelease(
                manuscript_id=manuscript.id,
                decision_id=decision.id,
                **report,
            )
        )
    db.flush()
    if decision.decision_code == "request_revision":
        from .stages import clone_for_return

        planned = value["revision_request"]
        draft = clone_for_return(
            db,
            actor,
            manuscript,
            flow,
            version,
            planned["author_instructions"],
            "chief_decision",
            planned_id=planned["planned_draft_version_id"],
            formal_request_id=planned["id"],
        )
        request = RevisionRequest(
            id=planned["id"],
            manuscript_id=manuscript.id,
            journal_id=manuscript.journal_id,
            decision_id=decision.id,
            request_no=planned["request_no"],
            base_version_id=version.id,
            draft_version_id=draft.id,
            kind=planned["kind"],
            rereview_required=planned["rereview_required"],
            author_instructions=planned["author_instructions"],
            due_at=datetime.fromisoformat(planned["due_at"]),
            status="requested",
        )
        db.add(request)
        task = db.scalar(
            select(core.WorkItem).where(core.WorkItem.step_run_id == flow.current_step_id)
        )
        task.due_at = request.due_at
    elif decision.decision_code == "accept":
        production = db.get(User, value["production_assignee"]["id"])
        core.assign(db, actor, manuscript, production.id, "production")
        flow.production_editor_id = production.id
        flow.accepted_version_id = version.id
        manuscript.status = "accepted"
        core.start_step(db, manuscript, flow, "production", production.id, version_id=version.id)
    else:
        manuscript.status = "rejected"
        flow.stage = "rejected"
        flow.current_step_id = None
    return decision


def confirm(db, actor, manuscript, flow, proposal, reason):
    core.authorize_proposal_content(db, actor, proposal)
    task = core.require_task(db, actor, manuscript, flow, proposal.work_item_id)
    version = db.get(ManuscriptVersion, proposal.version_id)
    expected = (
        flow.draft_version_id
        if proposal.action_type == "submit_revision"
        else flow.current_version_id
    )
    if version.id != expected:
        raise HTTPException(409, "本次审核的稿件版本已经变化")
    core.verify_version_files(db, version)
    snapshot = core.version_snapshot(db, version)
    if (
        snapshot != proposal.payload_snapshot["version"]
        or core.snapshot_evidence(snapshot) != proposal.evidence_digests
    ):
        raise HTTPException(409, "当前内容与独立审核快照不一致")
    try:
        extra = _extras(
            db,
            actor,
            manuscript,
            flow,
            proposal.action_type,
            proposal.payload_snapshot["input"],
            planned=proposal.payload_snapshot.get("decision"),
        )
    except ValidationError:
        raise HTTPException(409, "审核字段与当前政策不一致") from None
    if any(proposal.payload_snapshot.get(key) != value for key, value in extra.items()):
        raise HTTPException(409, "决定依据、报告或修回请求已经变化")
    confirmation = _new_confirmation(db, actor, manuscript, proposal, reason)
    finish_task(db, task, confirmation.id, {"action": proposal.action_type, **extra})
    if proposal.action_type == "recommend_decision":
        from .stages import next_assignee

        chief_id = next_assignee(db, manuscript, flow, "chief_decision")
        core.start_step(db, manuscript, flow, "chief_decision", chief_id, version_id=version.id)
    elif proposal.action_type == "record_decision":
        _record_decision(
            db, actor, manuscript, flow, task, version, confirmation, extra["decision"]
        )
    elif proposal.action_type == "submit_revision":
        request = db.get(RevisionRequest, extra["revision_request"]["id"])
        version.content_digest = core.digest(core.snapshot_evidence(snapshot))
        version.frozen_at = now()
        db.flush()
        request.status = "submitted"
        request.submitted_version_id = version.id
        request.author_confirmation_id = confirmation.id
        request.submitted_at = now()
        db.flush()
        flow.current_version_id, flow.draft_version_id = version.id, None
        manuscript.title, manuscript.status = version.title, "submitted"
        from .stages import next_assignee

        editor = next_assignee(db, manuscript, flow, "revision_assessment")
        core.start_step(db, manuscript, flow, "revision_assessment", editor, version_id=version.id)
    else:
        target = (
            "reviewer_selection"
            if extra["assessment"]["outcome"] == "rereview"
            else "editor_recommendation"
        )
        core.start_step(db, manuscript, flow, target, actor.user.id, version_id=version.id)
    core.bump(db, flow)
    core.event(
        db,
        actor,
        manuscript.id,
        "editorial_confirmed",
        {
            "action": proposal.action_type,
            "proposal_id": proposal.id,
            "confirmation_id": confirmation.id,
            "version_id": version.id,
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


def request_projection(request):
    if not request:
        return None
    return {
        key: getattr(request, key)
        for key in (
            "id",
            "decision_id",
            "request_no",
            "base_version_id",
            "draft_version_id",
            "submitted_version_id",
            "kind",
            "rereview_required",
            "author_instructions",
            "status",
        )
    } | {"due_at": request.due_at.isoformat()}


def projection(db, actor, manuscript, flow):
    request = latest_request(db, manuscript.id)
    if manuscript.author_id == actor.user.id:
        feedback = []
        for decision in db.scalars(
            select(EditorialDecision)
            .where(
                EditorialDecision.manuscript_id == manuscript.id,
            )
            .order_by(EditorialDecision.decided_at, EditorialDecision.id)
        ):
            revision = db.scalar(
                select(RevisionRequest).where(RevisionRequest.decision_id == decision.id)
            )
            releases = list(
                db.scalars(
                    select(DecisionReportRelease)
                    .where(
                        DecisionReportRelease.decision_id == decision.id,
                    )
                    .order_by(DecisionReportRelease.ordinal)
                )
            )
            feedback.append(
                {
                    "decision_id": decision.id,
                    "version_id": decision.version_id,
                    "decision_code": decision.decision_code,
                    "revision_kind": decision.revision_kind,
                    "author_letter": decision.author_letter,
                    "decided_at": decision.decided_at.isoformat(),
                    "instructions": revision.author_instructions if revision else "",
                    "due_at": revision.due_at.isoformat() if revision else None,
                    "reports": [
                        {"ordinal": r.ordinal, "author_snapshot": r.author_snapshot}
                        for r in releases
                    ],
                }
            )
        return {
            "mode": "author",
            "feedback": feedback,
            "revision_request": request_projection(request)
            if request and request.status == "requested"
            else None,
        }
    caps = core.capabilities(db, actor, manuscript)
    if not caps & {"handling_editor", "chief"} or core.is_conflicted(db, manuscript, actor.user):
        return None
    recommendation, assessment = None, None
    try:
        _, proposal = completed_confirmation(
            db, manuscript, flow.current_version_id, "editor_recommendation", "recommend_decision"
        )
        recommendation = proposal.payload_snapshot["recommendation"]
    except HTTPException:
        pass
    try:
        _, proposal = completed_confirmation(
            db, manuscript, flow.current_version_id, "revision_assessment", "assess_revision"
        )
        assessment = proposal.payload_snapshot["assessment"]
    except HTTPException:
        pass
    from .review_access import staff_projection

    review = staff_projection(db, actor, manuscript, flow)
    reports = []
    for item in review["reports"] if review else []:
        report = db.get(ReviewReport, item["id"])
        reports.append(
            {
                **item,
                "content_digest": report.content_digest,
                "form_digest": report.form_digest,
                "form": report.form_snapshot,
            }
        )
    return {
        "mode": "staff",
        "recommendation": recommendation,
        "assessment": assessment,
        "reports": reports,
        "revision_request": request_projection(request),
        "decisions": [
            {
                key: getattr(decision, key)
                for key in (
                    "id",
                    "version_id",
                    "basis_round_id",
                    "decision_code",
                    "revision_kind",
                    "rationale_private",
                    "author_letter",
                    "chief_id",
                    "human_confirmation_id",
                )
            }
            | {"decided_at": decision.decided_at.isoformat()}
            for decision in db.scalars(
                select(EditorialDecision)
                .where(
                    EditorialDecision.manuscript_id == manuscript.id,
                )
                .order_by(EditorialDecision.decided_at, EditorialDecision.id)
            )
        ],
    }
