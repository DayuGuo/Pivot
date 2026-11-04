"""Bounded keyset navigation. Cursors are untrusted positions, never authority."""

import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_


def scope_key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def cursor_position(cursor, scope):
    if cursor is None:
        return None
    try:
        if len(cursor) > 600:
            raise ValueError
        value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if (
            not isinstance(value, dict)
            or set(value) != {"scope", "at", "id"}
            or value["scope"] != scope
            or not isinstance(value["at"], str)
            or not isinstance(value["id"], str)
        ):
            raise ValueError
        at = datetime.fromisoformat(value["at"])
        if at.tzinfo is None or str(UUID(value["id"])) != value["id"]:
            raise ValueError
        return at, value["id"]
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, "分页位置无效或不属于当前资料，请重新载入。") from None


def older_than(timestamp, identifier, position):
    at, key = position
    return or_(timestamp < at, and_(timestamp == at, identifier < key))


def next_cursor(rows, limit, scope, timestamp="created_at"):
    if len(rows) <= limit:
        return None
    row = rows[limit - 1]
    return base64.urlsafe_b64encode(
        json.dumps(
            {"scope": scope, "at": getattr(row, timestamp).isoformat(), "id": row.id}
        ).encode()
    ).decode()
