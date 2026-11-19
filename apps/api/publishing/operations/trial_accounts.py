"""Server-operator Action Gateway for a small, single-journal editor trial.

Invoke through the private install manager. stdin carries a bounded JSON request;
credentials are never CLI arguments, receipts, audit details or error messages.
"""

import json
import os
import re
import sys
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from ..account_access import lock_account_access
from ..audit import record
from ..bootstrap import PUBLIC_USERS
from ..db import SessionLocal
from ..domain.core import digest
from ..domain.models import ActionReceipt
from ..models import LoginSession, Membership, TrialAccount, User, now
from ..security import check_password, hash_password

MAX_ACCOUNTS = 10


class TrialAccessError(Exception):
    """Only fixed, non-sensitive messages may cross this boundary."""


class TrialCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["list", "create", "disable", "resume", "rotate-password"]
    journal_id: UUID | None = None
    request_id: UUID | None = None
    user_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    email: str | None = Field(default=None, max_length=254)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: SecretStr | None = None
    reason: (
        Literal[
            "pilot_enrollment",
            "pilot_finished",
            "access_recovery",
            "credential_rotation",
            "participant_request",
        ]
        | None
    ) = None
    confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def shape(self):
        if self.action == "list":
            if (
                any(
                    getattr(self, key) is not None
                    for key in (
                        "request_id",
                        "user_id",
                        "expected_revision",
                        "email",
                        "name",
                        "password",
                        "reason",
                    )
                )
                or self.confirmed
            ):
                raise ValueError("Unexpected list fields")
            return self
        if not self.journal_id or not self.request_id or not self.confirmed or not self.reason:
            raise ValueError("Explicit confirmation, request ID and reason required")
        if self.action == "create":
            if (
                self.user_id
                or self.expected_revision
                or not self.email
                or not self.name
                or not self.name.strip()
            ):
                raise ValueError("Creation fields required")
            self.email = self.email.strip().lower()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.email) or self.email.endswith(
                "@publishing.test"
            ):
                raise ValueError("Private email required")
        elif not self.user_id or self.expected_revision is None or self.email or self.name:
            raise ValueError("Existing account identity and revision required")
        if self.action == "disable":
            if self.password is not None:
                raise ValueError("No password for suspension")
        elif self.password is None or not 16 <= len(self.password.get_secret_value()) <= 256:
            raise ValueError("Private password must contain 16–256 characters")
        return self


def require(condition, message):
    if not condition:
        raise TrialAccessError(message)


def operator(db: Session, journal_id: str | None) -> User:
    require(os.getenv("PIVOT_BOOTSTRAP_PROFILE") == "private-preview", "Private profile required")
    require(
        os.getenv("EMAIL_SEND_ENABLED", "false").lower() == "false", "Mail must remain disabled"
    )
    email = os.getenv("PIVOT_OPERATOR_EMAIL", "").strip().lower()
    password = os.getenv("PIVOT_OPERATOR_PASSWORD", "")
    require(email and len(password) >= 16, "Private operator credentials required")
    user = db.scalar(select(User).where(User.email == email))
    require(user is not None, "Configured operator not found")
    require(
        check_password(password, user.password_hash), "Configured operator credentials rejected"
    )
    require(db.get(TrialAccount, user.id) is None, "Trial participants cannot manage access")
    memberships = list(db.scalars(select(Membership).where(Membership.user_id == user.id)))
    require(
        memberships
        and len({m.journal_id for m in memberships}) == 1
        and (journal_id is None or {m.journal_id for m in memberships} == {journal_id})
        and any(m.role == "editor" for m in memberships),
        "Operator must belong to the requested journal as editor",
    )
    return user


def projection(account: TrialAccount, user: User):
    return {
        "user_id": user.id,
        "journal_id": account.journal_id,
        "email": user.email,
        "name": user.name,
        "role": "editor",
        "status": account.status,
        "revision": account.revision,
    }


def execute(db: Session, command: TrialCommand) -> dict:
    """Atomic operator gateway; never grants capabilities to ordinary editor sessions."""
    try:
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '10s'"))
        journal_id = str(command.journal_id) if command.journal_id else None
        owner = operator(db, journal_id)
        if journal_id is None:
            journal_id = db.scalar(
                select(Membership.journal_id).where(Membership.user_id == owner.id)
            )
        # Bounded local operation; serialize roster creation/count/replays, never model I/O.
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 718420033})
        if command.action == "list":
            rows = db.execute(
                select(TrialAccount, User)
                .join(User, User.id == TrialAccount.user_id)
                .where(TrialAccount.journal_id == journal_id, TrialAccount.operator_id == owner.id)
                .order_by(TrialAccount.created_at, TrialAccount.user_id)
                .limit(MAX_ACCOUNTS + 1)
            ).all()
            require(len(rows) <= MAX_ACCOUNTS, "Trial roster exceeds supported size")
            return {"journal_id": journal_id, "accounts": [projection(a, u) for a, u in rows]}
        password = command.password.get_secret_value() if command.password else None
        if password is not None:
            require(
                password not in {u[3] for u in PUBLIC_USERS}
                and not check_password(password, owner.password_hash),
                "Use an independent private password",
            )
        payload = command.model_dump(mode="json", exclude={"password"})
        fingerprint = digest(payload)
        previous = db.scalar(
            select(ActionReceipt).where(
                ActionReceipt.user_id == owner.id,
                ActionReceipt.journal_id == journal_id,
                ActionReceipt.request_id == str(command.request_id),
            )
        )
        if previous:
            require(
                previous.action_type == "trial.account" and previous.input_digest == fingerprint,
                "Request ID already belongs to different content",
            )
            account = db.get(TrialAccount, previous.response["user_id"])
            require(account is not None, "Trial account no longer available")
            lock_account_access(db, account.user_id, exclusive=True)
            db.refresh(account)
            user = db.get(User, account.user_id, populate_existing=True)
            require(
                account.revision == previous.response["revision"],
                "Receipt superseded; read current roster",
            )
            require(
                password is None or check_password(password, user.password_hash),
                "Retry password differs",
            )
            return previous.response
        if command.action == "create":
            require(
                db.scalar(select(User.id).where(User.email == command.email)) is None,
                "Email already exists; existing accounts are never changed",
            )
            count = db.scalar(
                select(func.count())
                .select_from(TrialAccount)
                .where(TrialAccount.journal_id == journal_id)
            )
            require(count < MAX_ACCOUNTS, "Trial roster limit reached")
            user = User(
                email=command.email,
                name=command.name.strip(),
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
            db.add(Membership(user_id=user.id, journal_id=journal_id, role="editor"))
            account = TrialAccount(user_id=user.id, journal_id=journal_id, operator_id=owner.id)
            db.add(account)
            db.flush()
            revoked = 0
        else:
            account = db.get(TrialAccount, str(command.user_id))
            require(
                account is not None
                and account.journal_id == journal_id
                and account.operator_id == owner.id,
                "Account is not managed by this journal operator",
            )
            lock_account_access(db, account.user_id, exclusive=True)
            db.refresh(account)
            require(
                account.revision == command.expected_revision,
                "Account changed; read current roster",
            )
            user = db.get(User, account.user_id, populate_existing=True)
            memberships = list(db.scalars(select(Membership).where(Membership.user_id == user.id)))
            require(
                len(memberships) == 1
                and memberships[0].journal_id == journal_id
                and memberships[0].role == "editor",
                "Managed account roles changed; specialist review required",
            )
            expected_status = "disabled" if command.action == "resume" else "active"
            require(account.status == expected_status, "Action does not match current access state")
            if password is not None:
                require(
                    not check_password(password, user.password_hash), "A new password is required"
                )
                user.password_hash = hash_password(password)
            account.status = "disabled" if command.action == "disable" else "active"
            account.revision += 1
            account.updated_at = now()
            revoked = db.execute(
                delete(LoginSession).where(LoginSession.user_id == user.id)
            ).rowcount
        result = {**projection(account, user), "revoked_sessions": revoked}
        # No password or derivative enters receipts/audit. Reason is human operational text.
        record(
            db,
            actor_id=owner.id,
            journal_id=journal_id,
            action=f"trial.account_{command.action}",
            entity_id=user.id,
            details={
                "request_id": str(command.request_id),
                "reason": command.reason,
                "revision": account.revision,
                "status": account.status,
                "revoked_sessions": revoked,
            },
        )
        db.add(
            ActionReceipt(
                user_id=owner.id,
                journal_id=journal_id,
                request_id=str(command.request_id),
                action_type="trial.account",
                input_digest=fingerprint,
                response=result,
            )
        )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def main():
    try:
        raw = sys.stdin.buffer.read(8193)
        require(len(raw) <= 8192, "Account request too large")
        command = TrialCommand.model_validate_json(raw)
        with SessionLocal() as db:
            result = execute(db, command)
        print(json.dumps(result, ensure_ascii=False))
    except TrialAccessError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        # DB/validation errors may contain passwords; never echo raw exception/input.
        print("Trial access request failed; no partial change committed", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
