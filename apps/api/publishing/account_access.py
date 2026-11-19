"""Authentication lifecycle locks, independent of HTTP and model execution."""

import hashlib

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import TrialAccount


def lock_account_access(db: Session, user_id: str, *, exclusive: bool = False):
    # Always acquire BEFORE session/member locks. Shared commits/login/switches may
    # proceed together; an operator suspension waits, then revokes every session.
    key = int.from_bytes(
        hashlib.sha256(f"trial-access:{user_id}".encode()).digest()[:8], "big", signed=True
    )
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    db.execute(text(f"SELECT {function}(:key)"), {"key": key})


def account_enabled(db: Session, user_id: str) -> bool:
    # Scalar projection deliberately avoids stale ORM identity-map state.
    status = db.scalar(select(TrialAccount.status).where(TrialAccount.user_id == user_id))
    return status is None or status == "active"
