"""Additive trial schema and populated downgrade refusal in disposable schemas."""

from uuid import uuid4

import pytest
from alembic import config, script
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from apps.api.publishing.db import engine


def test_trial_migration_preserves_prior_records_and_refuses_losing_suspension():
    migration = script.ScriptDirectory.from_config(config.Config("alembic.ini")).get_revision(
        "33a1b9c7d204"
    )
    assert migration.down_revision == "29b6d4a01c75"
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = "test_trial_migration_" + uuid4().hex
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("CREATE TABLE users (id varchar(36) PRIMARY KEY, marker text)"))
            connection.execute(text("CREATE TABLE journals (id varchar(36) PRIMARY KEY)"))
            user_id, owner_id, journal_id = (str(uuid4()) for _ in range(3))
            connection.execute(
                text("INSERT INTO users VALUES (:id, 'preserve-original-account')"), {"id": user_id}
            )
            connection.execute(text("INSERT INTO users VALUES (:id, 'operator')"), {"id": owner_id})
            connection.execute(text("INSERT INTO journals VALUES (:id)"), {"id": journal_id})
            with Operations.context(MigrationContext.configure(connection)):
                migration.module.upgrade()
                assert (
                    connection.scalar(
                        text("SELECT marker FROM users WHERE id=:id"), {"id": user_id}
                    )
                    == "preserve-original-account"
                )
                migration.module.downgrade()  # An empty additive table may be removed.
                assert "trial_accounts" not in inspect(connection).get_table_names()
                migration.module.upgrade()
                connection.execute(
                    text("""
                    INSERT INTO trial_accounts(user_id,journal_id,operator_id,status,revision,created_at,updated_at)
                    VALUES(:user,:journal,:owner,'disabled',2,now(),now())
                """),
                    {"user": user_id, "journal": journal_id, "owner": owner_id},
                )
                with pytest.raises(RuntimeError, match="refusing to discard suspension"):
                    migration.module.downgrade()
                assert (
                    connection.scalar(
                        text("SELECT status FROM trial_accounts WHERE user_id=:id"), {"id": user_id}
                    )
                    == "disabled"
                )
                assert (
                    connection.scalar(
                        text("SELECT marker FROM users WHERE id=:id"), {"id": user_id}
                    )
                    == "preserve-original-account"
                )
        finally:
            transaction.rollback()
