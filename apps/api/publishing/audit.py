from sqlalchemy.orm import Session

from .models import AuditEvent


def record(
    db: Session,
    *,
    actor_id: str | None,
    journal_id: str | None,
    action: str,
    entity_id: str | None = None,
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_id=actor_id,
        journal_id=journal_id,
        action=action,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(event)
    return event
