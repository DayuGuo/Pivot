"""Human choices, never model-selected final editorial decisions."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schemas import StrictInput

EDITORIAL_ACTIONS = {"recommend_decision", "record_decision", "submit_revision", "assess_revision"}


class Recommendation(StrictInput):
    recommendation: Literal["request_revision", "accept", "reject"]
    revision_kind: Literal["minor", "major"] | None = None
    rationale_private: str = Field(min_length=20, max_length=8000)
    author_letter: str = Field(min_length=20, max_length=12000)

    @model_validator(mode="after")
    def conditional_kind(self):
        if (self.recommendation == "request_revision") != (self.revision_kind is not None):
            raise ValueError("只有修回建议必须选择小修或大修")
        return self


class Decision(StrictInput):
    decision_code: Literal["request_revision", "accept", "reject"]
    revision_kind: Literal["minor", "major"] | None = None
    rationale_private: str = Field(min_length=20, max_length=8000)
    author_letter: str = Field(min_length=20, max_length=12000)
    share_report_ids: list[str] = Field(default_factory=list, max_length=32)
    share_reports_anonymity_reviewed: bool = False
    author_instructions: str = Field(default="", max_length=12000)
    due_days: int | None = Field(default=None, ge=1, le=90)

    @field_validator("share_report_ids")
    @classmethod
    def report_ids(cls, values):
        normalized = [str(UUID(v)) for v in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("不能重复分享同一报告")
        return normalized

    @model_validator(mode="after")
    def conditional_revision(self):
        if self.share_report_ids and not self.share_reports_anonymity_reviewed:
            raise ValueError("请本人检查拟分享意见正文的匿名性与保密内容")
        if self.decision_code == "request_revision":
            if not self.revision_kind or len(self.author_instructions) < 20 or not self.due_days:
                raise ValueError("修回决定需要类别、具体要求和期限")
        elif (
            self.revision_kind is not None or self.author_instructions or self.due_days is not None
        ):
            raise ValueError("录用或退稿不能附带修回请求")
        return self


class RevisionDeclarations(StrictInput):
    reviewed_current_version: Literal[True]
    reviewed_response: Literal[True]
    anonymous_material_reviewed: bool = False

    @field_validator("reviewed_current_version", "reviewed_response", mode="before")
    @classmethod
    def explicitly_true(cls, value):
        if value is not True:
            raise ValueError("需要本人明确确认布尔声明")
        return value


class Assessment(StrictInput):
    outcome: Literal["ready_for_chief", "rereview"]
    notes: str = Field(min_length=20, max_length=8000)
    declarations: RevisionDeclarations

    @model_validator(mode="after")
    def anonymous_material(self):
        if self.outcome == "rereview" and not self.declarations.anonymous_material_reviewed:
            raise ValueError("重新送审必须由本人检查匿名材料")
        return self
