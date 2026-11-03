"""Append-only model evidence, separate from a responsible person's dossier check."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base, now


class DossierAnswer(Base):
    __tablename__ = "publishing_dossier_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "dossier_id", "journal_id"],
            [
                "publishing_dossier_versions.id",
                "publishing_dossier_versions.dossier_id",
                "publishing_dossier_versions.journal_id",
            ],
            name="fk_dossier_answer_version",
        ),
        CheckConstraint(
            "COALESCE(jsonb_typeof(result_json)='object' AND "
            "result_json->>'schema'='dossier_answer.v1' AND "
            "result_json->>'provider' IN ('mock','deepseek') AND "
            "jsonb_typeof(result_json->'claims')='array' AND "
            "jsonb_typeof(result_json->'coverage')='object', false) AND "
            "octet_length(result_json::text)<=131072",
            name="ck_dossier_answer_result",
        ),
    )
    id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publishing_dossier_turns.id"), primary_key=True
    )
    dossier_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    result_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
