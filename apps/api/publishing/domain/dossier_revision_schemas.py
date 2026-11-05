"""Small internal comparison packets, separate from formal publication decisions."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from .dossier_schemas import ExplicitTrue, RequestID
from .schemas import StrictInput


class RevisionRequirement(StrictInput):
    text: str = Field(min_length=1, max_length=1200)
    original_context: str = Field(min_length=1, max_length=4000)

    @field_validator("text", "original_context")
    @classmethod
    def no_empty_or_null(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("请提供实际意见及原意见上下文，不能含空字符")
        return value


class DossierRevisionInput(StrictInput):
    request_id: RequestID
    expected_revision: int = Field(ge=2)
    base_version_id: RequestID
    revised_version_id: RequestID
    base_complete: bool
    revised_complete: bool
    requirements: list[RevisionRequirement] = Field(min_length=1, max_length=8)
    requirements_complete: bool
    response_text: str = Field(min_length=1, max_length=24000)
    response_complete: bool
    source_note: str = Field(min_length=5, max_length=2000)
    authorized_material: ExplicitTrue

    @field_validator("response_text", "source_note")
    @classmethod
    def meaningful_material(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("请提供实际回复和来源，不能含空字符")
        return value

    @field_validator("requirements")
    @classmethod
    def unique_requirements(cls, value):
        if len({r.text for r in value}) != len(value):
            raise ValueError("同批核对要求不能重复；请保留原意见上下文")
        return value


class DossierRevisionReviewInput(StrictInput):
    request_id: RequestID
    check_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_review_id: RequestID | None
    response_verdict: Literal["addressed", "not_addressed", "uncertain"]
    implementation_verdict: Literal["changed", "partial", "unchanged", "not_located", "uncertain"]
    editor_verdict: Literal["sufficient", "follow_up", "needs_judgment"]
    reason: str = Field(min_length=5, max_length=2000)
    acknowledged: ExplicitTrue

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 5 or "\x00" in value:
            raise ValueError("请填写至少5字的本人核对理由，不能含空字符")
        return value


PointID = Annotated[str, Field(pattern=r"^P0[1-8]$")]
