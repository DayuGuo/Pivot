"""Explicit human checks over an actual proof, never model declarations."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schemas import StrictInput

PRODUCTION_ACTIONS = {"send_proof", "confirm_proof", "prepare_local_preview"}


class ProofDeclarations(StrictInput):
    proof_reviewed: Literal[True]

    @field_validator("proof_reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError("需要本人实际阅读校样后确认")
        return value


class SendDeclarations(ProofDeclarations):
    metadata_reviewed: Literal[True]

    @field_validator("metadata_reviewed", mode="before")
    @classmethod
    def explicit_metadata(cls, value):
        if value is not True:
            raise ValueError("需要本人核对冻结录用版本元数据")
        return value


class SendProof(StrictInput):
    declarations: SendDeclarations


class ConfirmProof(StrictInput):
    package_id: str
    outcome: Literal["approve", "request_corrections"]
    notes: str = Field(default="", max_length=4000)
    declarations: ProofDeclarations

    @field_validator("package_id")
    @classmethod
    def identifier(cls, value):
        return str(UUID(value))

    @model_validator(mode="after")
    def correction_notes(self):
        if self.outcome == "request_corrections" and len(self.notes) < 20:
            raise ValueError("要求更正需要具体说明，至少20个字符")
        return self


class PreviewDeclarations(StrictInput):
    metadata_reviewed: Literal[True]
    approved_proof_reviewed: Literal[True]

    @field_validator("metadata_reviewed", "approved_proof_reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError("需要制作负责人本人阅读并确认")
        return value


class PreparePreview(StrictInput):
    declarations: PreviewDeclarations
