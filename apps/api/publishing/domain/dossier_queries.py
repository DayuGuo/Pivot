"""Owner-scoped list projection with one content query, independent of routes."""

from sqlalchemy import and_, select

from .dossier_access import require_staff
from .dossier_models import Dossier, DossierCheck, DossierVersion


def list_summaries(db, actor):
    require_staff(db, actor)
    checked = (
        select(DossierCheck.id)
        .where(
            DossierCheck.dossier_id == Dossier.id,
            DossierCheck.journal_id == Dossier.journal_id,
            DossierCheck.version_id == DossierVersion.id,
        )
        .exists()
    )
    rows = db.execute(
        select(
            Dossier.id,
            Dossier.revision,
            Dossier.current_version_id.label("version_id"),
            Dossier.updated_at,
            DossierVersion.version_no,
            DossierVersion.data_json["title"].as_string().label("title"),
            checked.label("verified"),
        )
        .join(
            DossierVersion,
            and_(
                DossierVersion.id == Dossier.current_version_id,
                DossierVersion.dossier_id == Dossier.id,
                DossierVersion.journal_id == Dossier.journal_id,
            ),
        )
        .where(Dossier.journal_id == actor.journal_id, Dossier.created_by == actor.user.id)
        .order_by(Dossier.updated_at.desc(), Dossier.id)
    ).all()
    require_staff(db, actor)
    return [
        {
            "id": item.id,
            "title": item.title,
            "revision": item.revision,
            "version_id": item.version_id,
            "version_no": item.version_no,
            "verified": item.verified,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in rows
    ]
