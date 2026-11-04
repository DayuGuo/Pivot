"""Version and transcript projections. Bounded history is loaded in batches."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.model_gateway.editorial import editorial_model_status

from ..security import Actor
from .author_links import author_issues
from .document_sources import source_projection
from .dossier_access import file_content, load, version
from .dossier_chat_models import DossierAnswer
from .dossier_models import DossierCheck, DossierTurn, DossierVersion
from .dossier_schemas import DossierData, missing
from .pagination import cursor_position, next_cursor, older_than, scope_key


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


def message_page(db, actor, row, *, limit=50, cursor=None):
    scope = scope_key("messages", actor.user.id, row.journal_id, row.id)
    position = cursor_position(cursor, scope)
    turns = db.scalars(
        select(DossierTurn)
        .where(
            DossierTurn.dossier_id == row.id,
            DossierTurn.journal_id == row.journal_id,
            DossierTurn.user_id == actor.user.id,
        )
        .where(older_than(DossierTurn.created_at, DossierTurn.id, position) if position else True)
        .order_by(DossierTurn.created_at.desc(), DossierTurn.id.desc())
        .limit(limit + 1)
    ).all()
    following = next_cursor(turns, limit, scope)
    turns = turns[:limit]
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
    versions = (
        {
            v.id: v
            for v in db.scalars(
                select(DossierVersion).where(
                    DossierVersion.dossier_id == row.id,
                    DossierVersion.journal_id == row.journal_id,
                    DossierVersion.id.in_({turn.version_id for turn in turns}),
                )
            ).all()
        }
        if turns
        else {}
    )
    return {
        "items": [
            turn_projection(db, t, versions=versions, answers=answers) for t in reversed(turns)
        ],
        "next_cursor": following,
    }


def version_page(db, actor, row, *, limit=50, cursor=None):
    scope = scope_key("versions", actor.user.id, row.journal_id, row.id)
    position = cursor_position(cursor, scope)
    versions = db.scalars(
        select(DossierVersion)
        .where(DossierVersion.dossier_id == row.id, DossierVersion.journal_id == row.journal_id)
        .where(
            older_than(DossierVersion.created_at, DossierVersion.id, position) if position else True
        )
        .order_by(DossierVersion.created_at.desc(), DossierVersion.id.desc())
        .limit(limit + 1)
    ).all()
    checked = set(
        db.scalars(
            select(DossierCheck.version_id).where(
                DossierCheck.dossier_id == row.id,
                DossierCheck.journal_id == row.journal_id,
                DossierCheck.version_id.in_([v.id for v in versions[:limit]]),
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": v.id,
                "number": v.version_no,
                "title": v.data_json["title"],
                "created_at": v.created_at.isoformat(),
                "verified": v.id in checked,
            }
            for v in versions[:limit]
        ],
        "next_cursor": next_cursor(versions, limit, scope),
    }


def projection(db: Session, actor: Actor, dossier_id: str, version_id: str | None = None):
    row = load(db, actor, dossier_id)
    item = version(db, row, version_id)
    data = DossierData.model_validate(item.data_json)
    material = file_content(db, item)
    check = db.scalar(select(DossierCheck).where(DossierCheck.version_id == item.id))
    history = message_page(db, actor, row)
    versions = version_page(db, actor, row)
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
        "author_issues": author_issues(data.model_dump()),
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
        "versions": versions["items"],
        "versions_next_cursor": versions["next_cursor"],
        "messages": history["items"],
        "messages_next_cursor": history["next_cursor"],
        "model": {
            "provider": status["provider"],
            "model": status["model"],
            "ready": status["available"],
        },
    }
