"""Fixed v0.1 peer-review form; no caller-supplied state, identity grants or templates."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schemas import StrictInput

REVIEW_ACTIONS = {
    "open_review",
    "invite_reviewers",
    "respond_review_invitation",
    "submit_review",
    "finish_review",
    "cancel_review_invitation",
}
FORM = {
    "key": "basic_peer_review",
    "version": 1,
    "questions": [
        {
            "key": "rigor",
            "label": "方法与证据是否充分",
            "kind": "text",
            "required": True,
            "audience": "author",
        },
        {
            "key": "confidential_assessment",
            "label": "给编辑的保密评估",
            "kind": "text",
            "required": True,
            "audience": "editor_only",
        },
    ],
}
Identifier = Annotated[str, Field(min_length=36, max_length=36)]


class InviteInput(StrictInput):
    reviewer_ids: list[Identifier] = Field(min_length=1, max_length=3)
    instructions: str = Field(min_length=10, max_length=4000)
    response_due_days: int = Field(default=7, ge=1, le=30)
    report_due_days: int = Field(default=21, ge=2, le=90)

    @field_validator("reviewer_ids")
    @classmethod
    def distinct_valid_ids(cls, values):
        normalized = [str(UUID(value)) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("不能重复选择同一审稿人")
        return normalized

    @model_validator(mode="after")
    def deadlines(self):
        if self.report_due_days <= self.response_due_days:
            raise ValueError("报告截止时间必须晚于邀请响应时间")
        return self


class OpenReviewInput(InviteInput):
    required_reports: int = Field(default=1, ge=1, le=3)


class InvitationResponse(StrictInput):
    invitation_id: Identifier
    outcome: Literal["accept", "decline"]
    conflict_status: Literal["none", "declared"]
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def conflict(self):
        if self.outcome == "accept" and self.conflict_status != "none":
            raise ValueError("声明有利益冲突时不能接受审稿")
        if self.conflict_status == "declared" and not self.notes:
            raise ValueError("请说明利益冲突或拒绝原因")
        return self


class ReviewAnswers(StrictInput):
    rigor: str = Field(default="", max_length=4000)
    confidential_assessment: str = Field(default="", max_length=4000)


class ReportData(StrictInput):
    author_text: str = Field(default="", max_length=12000)
    editor_private_text: str = Field(default="", max_length=4000)
    answers_json: ReviewAnswers = Field(default_factory=ReviewAnswers)
    recommendation: Literal[
        "unanswered", "accept", "minor_revision", "major_revision", "reject"
    ] = "unanswered"

    def missing(self):
        missing = []
        if len(self.author_text) < 40:
            missing.append({"field": "author_text", "message": "给作者的评审意见至少需要40个字符"})
        for key in ("rigor", "confidential_assessment"):
            if len(getattr(self.answers_json, key)) < 10:
                missing.append(
                    {
                        "field": "answers_json." + key,
                        "message": "请完成评审表中的问题，至少10个字符",
                    }
                )
        if self.recommendation == "unanswered":
            missing.append(
                {"field": "recommendation", "message": "请选择审稿建议；建议不是主编最终决定"}
            )
        return missing


class SubmitReport(StrictInput):
    report_id: Identifier
    expected_report_revision: int = Field(ge=0)


class CloseReview(StrictInput):
    reason: str = Field(min_length=1, max_length=4000)
    cancel_pending: bool = False


class CancelInvitation(StrictInput):
    invitation_id: Identifier
    reason: str = Field(min_length=1, max_length=4000)


class ReportCandidates(StrictInput):
    """Model prose candidates exclude COI, recommendation and final confirmation."""

    author_text: str | None = Field(default=None, max_length=12000)
    editor_private_text: str | None = Field(default=None, max_length=4000)
    answers_json: ReviewAnswers | None = None
