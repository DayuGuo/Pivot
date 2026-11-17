"""Independent PostgreSQL connections prove suspension/login ordering."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.publishing import main
from apps.api.publishing.db import engine
from apps.api.publishing.models import Journal, LoginSession, Membership, User
from apps.api.publishing.operations import trial_accounts
from apps.api.publishing.security import hash_password
from tests.api.test_trial_accounts import (
    NEW_PASSWORD,
    OPERATOR_PASSWORD,
    PARTICIPANT_PASSWORD,
    change_command,
    create_command,
)


@pytest.fixture
def persisted_trial(monkeypatch):
    # Unique synthetic evidence, matching existing concurrency tests; never clear a DB.
    with Session(engine, expire_on_commit=False) as db:
        journal = Journal(name=f"Trial concurrency {uuid4().hex}")
        owner = User(
            email=f"trial-owner-{uuid4().hex}@synthetic.test",
            name="合成负责人",
            password_hash=hash_password(OPERATOR_PASSWORD),
        )
        db.add_all([journal, owner])
        db.flush()
        db.add(Membership(user_id=owner.id, journal_id=journal.id, role="editor"))
        db.commit()
        monkeypatch.setenv("PIVOT_BOOTSTRAP_PROFILE", "private-preview")
        monkeypatch.setenv("PIVOT_OPERATOR_EMAIL", owner.email)
        monkeypatch.setenv("PIVOT_OPERATOR_PASSWORD", OPERATOR_PASSWORD)
        monkeypatch.setenv("EMAIL_SEND_ENABLED", "false")
        return trial_accounts.execute(db, create_command(SimpleNamespace(journal=journal)))


def login_on_connection(account, password=PARTICIPANT_PASSWORD):
    with Session(engine, expire_on_commit=False) as db:
        db.execute(text("SET LOCAL statement_timeout='8s'"))
        return main.login(
            main.LoginInput(email=account["email"], password=password), Response(), db
        )


def mutate_on_connection(command):
    with Session(engine, expire_on_commit=False) as db:
        db.execute(text("SET LOCAL statement_timeout='8s'"))
        return trial_accounts.execute(db, command)


def test_login_in_progress_is_revoked_by_waiting_disable(persisted_trial, monkeypatch):
    locked, release, waiting = Event(), Event(), Event()
    check = main.check_password
    account_lock = trial_accounts.lock_account_access

    def pause_login(password, encoded):
        result = check(password, encoded)
        locked.set()
        assert release.wait(6)
        return result

    def announce_wait(db, user_id, **kwargs):
        waiting.set()
        return account_lock(db, user_id, **kwargs)

    monkeypatch.setattr(main, "check_password", pause_login)
    monkeypatch.setattr(trial_accounts, "lock_account_access", announce_wait)
    with ThreadPoolExecutor(max_workers=2) as pool:
        login = pool.submit(login_on_connection, persisted_trial)
        try:
            assert locked.wait(5)
            disable = pool.submit(mutate_on_connection, change_command(persisted_trial))
            assert waiting.wait(5)
            assert not disable.done()
        finally:
            release.set()
        assert login.result(timeout=8)["landing_path"] == "/library"
        result = disable.result(timeout=8)
        assert result["revoked_sessions"] == 1
    with Session(engine) as db:
        assert (
            db.scalar(
                select(LoginSession).where(LoginSession.user_id == persisted_trial["user_id"])
            )
            is None
        )


@pytest.mark.parametrize("action", ["disable", "rotate-password"])
def test_queued_login_reloads_credentials_and_state_after_mutation(
    persisted_trial, monkeypatch, action
):
    locked, release, waiting = Event(), Event(), Event()
    original_record = trial_accounts.record
    original_lock = main.lock_account_access

    def pause_mutation(*args, **kwargs):
        original_record(*args, **kwargs)
        locked.set()
        assert release.wait(6)

    def announce_login(db, user_id, **kwargs):
        # login has already loaded the old User/hash before this lock.
        waiting.set()
        return original_lock(db, user_id, **kwargs)

    monkeypatch.setattr(trial_accounts, "record", pause_mutation)
    monkeypatch.setattr(main, "lock_account_access", announce_login)
    with ThreadPoolExecutor(max_workers=2) as pool:
        mutation = pool.submit(mutate_on_connection, change_command(persisted_trial, action))
        try:
            assert locked.wait(5)
            login = pool.submit(login_on_connection, persisted_trial)
            assert waiting.wait(5)
            assert not login.done()
        finally:
            release.set()
        mutation.result(timeout=8)
        with pytest.raises(HTTPException) as failure:
            login.result(timeout=8)
        assert failure.value.status_code == 401
    if action == "rotate-password":
        assert login_on_connection(persisted_trial, NEW_PASSWORD)["landing_path"] == "/library"


def test_cli_real_request_creates_account_and_hides_secrets(persisted_trial):
    import json
    import subprocess
    import sys

    command = dict(
        action="create",
        journal_id=persisted_trial["journal_id"],
        request_id=str(uuid4()),
        email=f"cli-{uuid4().hex}@synthetic.test",
        name="CLI合成编辑",
        password=PARTICIPANT_PASSWORD,
        reason="pilot_enrollment",
        confirmed=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "apps.api.publishing.operations.trial_accounts"],
        input=json.dumps(command),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    account = json.loads(result.stdout)
    assert account["status"] == "active"
    assert PARTICIPANT_PASSWORD not in result.stdout + result.stderr
    assert OPERATOR_PASSWORD not in result.stdout + result.stderr
    assert login_on_connection(account)["landing_path"] == "/library"
    with Session(engine) as db:
        disabled = trial_accounts.execute(db, change_command(account))
    assert disabled["revoked_sessions"] == 1


def test_cli_validation_failure_never_echoes_secret(persisted_trial):
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "apps.api.publishing.operations.trial_accounts"],
        input=json.dumps({"action": "unknown", "password": PARTICIPANT_PASSWORD}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert PARTICIPANT_PASSWORD not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
