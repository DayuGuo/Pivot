"""Version and transcript projections. Bounded history is loaded in batches."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.model_gateway.editorial import editorial_model_status

from ..security import Actor
from .document_sources import source_projection
from .dossier_access import file_content, load, version
from .dossier_chat_models import DossierAnswer
from .dossier_models import DossierCheck, DossierTurn, DossierVersion
from .dossier_schemas import DossierData, missing


def turn_projection(db: Session, turn: DossierTurn, *, versions=None, answers=None):
    item = (
        versions[turn.version_id]
        if versions is not None
        else db.get(DossierVersion, turn.version_id)
    )
    answer = answers.get(turn.id) if answers is not None else db.get(DossierAnswer, turn.id)
    return {
        **(answer.result_json if answer else {"provider": "rules"}),
        "id": turn.id,
        "question": turn.question,
        "answer": turn.answer,
        "version_id": turn.version_id,
        "version_no": item.version_no,
    }


def projection(db: Session, actor: Actor, dossier_id: str, version_id: str | None = None):
    row = load(db, actor, dossier_id)
    item = version(db, row, version_id)
    data = DossierData.model_validate(item.data_json)
    material = file_content(db, item)
    check = db.scalar(select(DossierCheck).where(DossierCheck.version_id == item.id))
    versions = db.scalars(
        select(DossierVersion)
        .where(DossierVersion.dossier_id == row.id)
        .order_by(DossierVersion.version_no.desc())
    ).all()
    checked = set(
        db.scalars(select(DossierCheck.version_id).where(DossierCheck.dossier_id == row.id)).all()
    )
    turns = db.scalars(
        select(DossierTurn)
        .where(DossierTurn.dossier_id == row.id, DossierTurn.user_id == actor.user.id)
        .order_by(DossierTurn.created_at.desc(), DossierTurn.id.desc())
        .limit(50)
    ).all()

    answers = (
        {
            answer.id: answer
            for answer in db.scalars(
                select(DossierAnswer).where(
                    DossierAnswer.dossier_id == row.id,
                    DossierAnswer.journal_id == row.journal_id,
                    DossierAnswer.id.in_([turn.id for turn in turns]),
                )
            ).all()
        }
        if turns
        else {}
    )
    versions_by_id = {item.id: item for item in versions}
    document = source_projection(db, row, item)
    status = editorial_model_status()
    return {
        "id": row.id,
        "revision": row.revision,
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "is_current": item.id == row.current_version_id,
        "verified": check is not None,
        "verification": {"id": check.id, "by": check.checked_by, "at": check.checked_at.isoformat()}
        if check
        else None,
        "data": data.model_dump(),
        "document": document,
        "file": {
            "filename": item.file_name,
            "sha256": material[0].sha256,
            "byte_size": material[0].byte_size,
            "media_type": item.file_media_type,
            "text": material[1].decode("utf-8"),
            "download_url": f"/api/dossiers/{row.id}/versions/{item.id}/file",
        }
        if material
        else None,
        "missing": missing(data, bool(material)),
        "versions": [
            {
                "id": v.id,
                "number": v.version_no,
                "title": v.data_json["title"],
                "created_at": v.created_at.isoformat(),
                "verified": v.id in checked,
            }
            for v in versions
        ],
        "messages": [
            turn_projection(db, t, versions=versions_by_id, answers=answers)
            for t in reversed(turns)
        ],
        "model": {
            "provider": status["provider"],
            "model": status["model"],
            "ready": status["available"],
        },
    }
