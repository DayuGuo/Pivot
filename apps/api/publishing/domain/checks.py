"""Human-reviewed screening evidence; no detector, policy authority or state transition.

Research: OJS separates submission stage/round/decision facts; Janeway separates
workflow tasks/checklists from decisions. Our immutable confirmation/evidence binding
is stricter and independently implemented (spec007). Similarity remains manual review
of a real locally uploaded report, never an automatic plagiarism result.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now, uid
from .models import _same_manuscript, _tenant_manuscript
from .schemas import IntakeData, StrictInput, missing_requirements

CHECK_KINDS = (
    "precheck_completeness",
    "similarity_review",
    "technical_screening",
    "chief_scope",
    "editor_quality",
)
CheckKind = Literal[
    "precheck_completeness",
    "similarity_review",
    "technical_screening",
    "chief_scope",
    "editor_quality",
]
Identifier = Annotated[str, Field(min_length=1, max_length=36)]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class CheckRun(Base):
    __tablename__ = "publishing_check_runs"
    __table_args__ = (
        _tenant_manuscript("fk_pub_check_manuscript_journal"),
        _same_manuscript("version_id", "publishing_versions", "fk_pub_check_version"),
        _same_manuscript("step_run_id", "publishing_step_runs", "fk_pub_check_step"),
        _same_manuscript(
            "human_confirmation_id", "publishing_human_confirmations", "fk_pub_check_confirmation"
        ),
        ForeignKeyConstraint(
            ["file_object_id", "journal_id"],
            ["publishing_file_objects.id", "publishing_file_objects.journal_id"],
            name="fk_pub_check_file_journal",
        ),
        UniqueConstraint("id", "manuscript_id", name="uq_pub_check_id_manuscript"),
        UniqueConstraint("human_confirmation_id", name="uq_pub_check_confirmation"),
        CheckConstraint(
            "kind IN (" + ",".join(repr(kind) for kind in CHECK_KINDS) + ")",
            name="ck_pub_check_kind",
        ),
        CheckConstraint("outcome IN ('pass','return')", name="ck_pub_check_outcome"),
        CheckConstraint("check_method = 'manual_review'", name="ck_pub_check_method"),
        CheckConstraint("length(btrim(notes)) > 0", name="ck_pub_check_notes"),
        CheckConstraint(
            "outcome <> 'return' OR length(btrim(reason)) > 0", name="ck_pub_check_return_reason"
        ),
        CheckConstraint(
            "(human_confirmation_id IS NULL) = (finalized_at IS NULL)",
            name="ck_pub_check_finalization",
        ),
        CheckConstraint(
            "kind <> 'similarity_review' OR file_object_id IS NOT NULL",
            name="ck_pub_check_similarity_report",
        ),
        Index(
            "uq_pub_check_finalized_step",
            "step_run_id",
            unique=True,
            postgresql_where=text("finalized_at IS NOT NULL"),
        ),
        Index("ix_pub_check_manuscript_kind", "manuscript_id", "kind", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    manuscript_id: Mapped[str] = mapped_column(String(36), ForeignKey("manuscripts.id"))
    journal_id: Mapped[str] = mapped_column(String(36), ForeignKey("journals.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    step_run_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(50))
    outcome: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    check_method: Mapped[str] = mapped_column(
        String(60), default="manual_review", server_default="manual_review"
    )
    file_object_id: Mapped[str | None] = mapped_column(String(36))
    evidence_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    prepared_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    human_confirmation_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CheckDeclarations(StrictInput):
    materials_reviewed: Literal[True]
    report_reviewed: bool = False
    anonymous_material_reviewed: bool = False
    scope_matches: bool | None = None
    quality_sufficient: bool | None = None

    @field_validator("materials_reviewed", mode="before")
    @classmethod
    def explicit_reviewed_boolean(cls, value):
        if value is not True:
            raise ValueError("必须明确声明已人工检查材料")
        return value


class CheckInput(StrictInput):
    """User-proposed finding, never a permission/actor/target-stage or confirmation."""

    outcome: Literal["pass", "return"]
    notes: str = Field(min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=4000)
    file_object_id: Identifier | None = None
    declarations: CheckDeclarations

    @model_validator(mode="after")
    def return_requires_reason(self):
        if self.outcome == "return" and not self.reason:
            raise ValueError("退回必须说明原因")
        return self


class CheckMaterialFile(StrictInput):
    """Server-read immutable VersionFile projection, not model-declared file facts."""

    id: Identifier
    purpose: Literal["manuscript", "blinded_manuscript", "response", "similarity_report", "proof"]
    sha256: Sha256
    visibility: Literal["author_editor", "reviewer", "production"]


class CheckFileEvidence(StrictInput):
    """Server-resolved FileObject; callers must also verify its actual CAS bytes."""

    id: Identifier
    journal_id: Identifier
    sha256: Sha256
    byte_size: int = Field(ge=1, le=1048576)
    media_type: Literal["text/plain", "text/markdown"]
    scan_status: Literal["validated_text"]
    check_method: Literal["utf8_text_safety"]
    original_filename: str = Field(min_length=1, max_length=255)


class CheckMaterial(StrictInput):
    manuscript_id: Identifier
    journal_id: Identifier
    version_id: Identifier
    step_run_id: Identifier
    step_key: CheckKind
    data: IntakeData
    files: list[CheckMaterialFile] = Field(default_factory=list, max_length=5)
    report: CheckFileEvidence | None = None

    @model_validator(mode="after")
    def unique_files(self):
        if len({f.id for f in self.files}) != len(self.files) or len(
            {f.purpose for f in self.files}
        ) != len(self.files):
            raise ValueError("检查材料不能包含重复文件或重复用途")
        return self


class PreparedCheck(StrictInput):
    kind: CheckKind
    outcome: Literal["pass", "return"]
    notes: str
    reason: str
    check_method: Literal["manual_review"] = "manual_review"
    file_object_id: Identifier | None
    evidence_json: dict
    requires_human_confirmation: Literal[True] = True


class CheckPreparationError(ValueError):
    """Safe deterministic validation error, translated by the Action Gateway."""


def prepare_check(
    kind: CheckKind, payload: CheckInput | dict, material: CheckMaterial | dict
) -> PreparedCheck:
    """Prepare a bounded finding without DB writes, model calls or state advancement.

    Actor/assignment/COI/current revision/frozen-version/actual-file verification are
    the gateway's responsibility at preparation AND human confirmation. This function
    validates typed material and explicit manual declarations, not their truthfulness.
    """
    payload = CheckInput.model_validate(payload)
    material = CheckMaterial.model_validate(material)
    if kind not in CHECK_KINDS or material.step_key != kind:
        raise CheckPreparationError("检查类型与当前步骤不一致")
    report = material.report
    if payload.file_object_id:
        if (
            not report
            or report.id != payload.file_object_id
            or report.journal_id != material.journal_id
        ):
            raise CheckPreparationError("检查报告必须是当前期刊的已上传证据")
    elif report:
        raise CheckPreparationError("提供报告时必须明确绑定报告编号")
    if kind == "similarity_review":
        if not report or not payload.file_object_id or not payload.declarations.report_reviewed:
            raise CheckPreparationError(
                "相似度复核需要实际报告和负责人明确人工复核声明；不会自动查重"
            )
    elif report or payload.file_object_id:
        raise CheckPreparationError("此检查不接受相似度报告附件")
    missing = missing_requirements(material.data, {file.purpose for file in material.files})
    if payload.outcome == "pass":
        if kind == "precheck_completeness" and missing:
            raise CheckPreparationError("材料尚有必需项缺失，不能准备预审通过")
        if kind == "technical_screening" and not (
            payload.declarations.anonymous_material_reviewed
            and any(
                f.purpose == "blinded_manuscript" and f.visibility == "reviewer"
                for f in material.files
            )
        ):
            raise CheckPreparationError("需要实际盲审文件和负责人匿名材料人工复核声明")
        if kind == "chief_scope" and payload.declarations.scope_matches is not True:
            raise CheckPreparationError("主编需明确确认符合本刊受稿范围")
        if kind == "editor_quality" and payload.declarations.quality_sufficient is not True:
            raise CheckPreparationError("责任编辑需明确确认稿件质量适合送审")
    return PreparedCheck(
        kind=kind,
        outcome=payload.outcome,
        notes=payload.notes,
        reason=payload.reason,
        file_object_id=payload.file_object_id,
        evidence_json={
            "schema_version": 1,
            "manuscript_id": material.manuscript_id,
            "journal_id": material.journal_id,
            "version_id": material.version_id,
            "step_run_id": material.step_run_id,
            "step_key": kind,
            "check_method": "manual_review",
            "declarations": payload.declarations.model_dump(),
            "files": [f.model_dump() for f in material.files],
            "report": report.model_dump() if report else None,
            "missing_requirements": missing,
            "automatic_similarity_detection": False,
        },
    )
