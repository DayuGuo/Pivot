"""Action-gateway adapter and audit for private dossiers; no endpoint registration."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from ..audit import record
from ..security import Actor
from .core import run_action
from .dossier_access import load
from .dossier_models import Dossier


def gateway(
    db: Session,
    actor: Actor,
    body,
    action: str,
    dossier_id: str | None,
    execute,
    *,
    revalidate_resource=None,
):
    payload = body.model_dump(mode="json", exclude={"request_id"})
    if dossier_id:
        payload["dossier_id"] = dossier_id
    # Deterministic create ID also lets a replay re-check the exact private object.
    target = dossier_id or str(
        uuid5(NAMESPACE_URL, f"pivot:dossier:{actor.journal_id}:{actor.user.id}:{body.request_id}")
    )

    def revalidate():
        load(db, actor, target)
        if revalidate_resource is not None:
            revalidate_resource()

    result = run_action(
        db,
        actor,
        str(body.request_id),
        f"dossier.{action}",
        payload,
        execute,
        revalidate_replay=revalidate,
    )
    return result


def event(
    db: Session,
    actor: Actor,
    row: Dossier,
    action: str,
    version_id: str,
    *,
    evidence_id: str | None = None,
):
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action=f"publishing.dossier_{action}",
        entity_id=row.id,
        details={"version_id": version_id, "revision": row.revision}
        | ({"evidence_id": evidence_id} if evidence_id else {}),
    )
