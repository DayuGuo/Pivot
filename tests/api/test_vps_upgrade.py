"""Upgrade boundaries plus a rollback-only PostgreSQL shadow-schema scanner test.

The snapshot_sql case needs an explicitly selected test database. Other cases
are offline and do not use Docker, user state, credentials or network.
"""

import hashlib
import importlib.util
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)

from apps.api.publishing.db import engine

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "upgrade_contract", ROOT / "scripts/accept-vps-upgrade.py"
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    path = tmp_path / "artifacts"
    path.mkdir()
    monkeypatch.setattr(upgrade, "ROOT", tmp_path)
    monkeypatch.setattr(upgrade, "ARTIFACTS", path)
    return path


def bundle(artifacts, name="old", source=None):
    path = artifacts / name
    path.mkdir()
    hashes = {}
    for filename in upgrade.BUNDLE_FILES:
        content = (
            "from pathlib import Path\nBUNDLE = Path(__file__).resolve().parent\n"
            if filename == "manage.py"
            else "Synthetic contract fixture, not an executable image.\n"
        )
        (path / filename).write_text(content)
        hashes[filename] = hashlib.sha256(content.encode()).hexdigest()
    manifest = {
        "platform": "linux/amd64",
        "source": source or upgrade.PREVIEW4_SOURCE,
        "images": {
            service: f"pivot-app-{service}:synthetic-amd64" for service in ("db", "api", "web")
        },
        "sha256": hashes,
    }
    (path / "bundle.json").write_text(json.dumps(manifest))
    return path, manifest


def save_manifest(path, value):
    (path / "bundle.json").write_text(json.dumps(value))


def snapshot():
    return {
        "database": {
            "schema_head": "old",
            "tables": {
                "synthetic": {"rows": 2, "sha256": "a" * 64, "columns_sha256": "b" * 64},
            },
        },
        "cas": {"files": {"ab/" + "a" * 64: {"size": 20, "sha256": "c" * 64}}},
    }


def test_only_repository_artifacts_are_accepted(artifacts, tmp_path):
    assert upgrade.artifact_path(artifacts / "new") == artifacts / "new"
    for path in (tmp_path / "private-state", artifacts, Path("/opt/pivot-app-data")):
        with pytest.raises(upgrade.UpgradeError, match="artifact_path_required"):
            upgrade.artifact_path(path)


def test_symlink_directory_or_artifacts_root_never_grants_access(artifacts):
    real = artifacts / "real"
    real.mkdir()
    link = artifacts / "linked"
    link.symlink_to(real, target_is_directory=True)
    for path in (link, link / "new"):
        with pytest.raises(upgrade.UpgradeError, match="artifact_symlink_refused"):
            upgrade.artifact_path(path)
    actual = artifacts.with_name("actual-artifacts")
    artifacts.rename(actual)
    artifacts.symlink_to(actual, target_is_directory=True)
    with pytest.raises(upgrade.UpgradeError, match="artifact_root_symlink_refused"):
        upgrade.artifact_path(artifacts / "new")


def test_checked_bundle_platform_preview4_and_independent_manager_roots(artifacts):
    old, manifest = bundle(artifacts)
    new, _ = bundle(artifacts, "candidate", "f" * 40 + "-worktree-" + "e" * 64)
    assert upgrade.validate_bundle(old, "linux/amd64", old=True) == (old, manifest)
    upgrade.validate_bundle(new, "linux/amd64")
    first, second = upgrade.load_manager(old), upgrade.load_manager(new)
    assert first is not second and first.BUNDLE == old and second.BUNDLE == new
    with pytest.raises(upgrade.UpgradeError, match="preview4_source_required"):
        upgrade.validate_bundle(new, "linux/amd64", old=True)
    with pytest.raises(upgrade.UpgradeError, match="bundle_platform_mismatch"):
        upgrade.validate_bundle(old, "linux/arm64")


def test_hash_mismatch_or_symlink_file_is_rejected_before_import(artifacts):
    path, _ = bundle(artifacts)
    (path / "manage.py").write_text("raise AssertionError('Must never import this')\n")
    with pytest.raises(upgrade.UpgradeError, match="bundle_hash_mismatch"):
        upgrade.validate_bundle(path, "linux/amd64", old=True)
    (path / "manage.py").unlink()
    (path / "manage.py").symlink_to(path / "README.md")
    with pytest.raises(upgrade.UpgradeError, match="bundle_file_invalid"):
        upgrade.validate_bundle(path, "linux/amd64", old=True)


@pytest.mark.parametrize("name", ["credentials.json", "../credentials.json", "/tmp/private-key"])
def test_manifest_cannot_make_validator_read_private_state(artifacts, name):
    path, manifest = bundle(artifacts)
    manifest["sha256"][name] = "a" * 64
    save_manifest(path, manifest)
    with pytest.raises(upgrade.UpgradeError, match="bundle_file_allowlist_mismatch"):
        upgrade.validate_bundle(path, "linux/amd64")


def test_upgrade_permits_only_empty_added_tables_and_preserves_every_existing_hash():
    before = snapshot()
    after = deepcopy(before)
    after["database"]["schema_head"] = "new"
    after["database"]["tables"]["new_table"] = {
        "rows": 0,
        "sha256": "d" * 64,
        "columns_sha256": "e" * 64,
    }
    result = upgrade.compare_snapshots(before, after, allow_new_tables=True)
    assert result["old_rows"] == 2 and result["new_empty_tables"] == 1
    with pytest.raises(upgrade.UpgradeError, match="unexpected_new_tables"):
        upgrade.compare_snapshots(before, after)
    after["database"]["tables"]["new_table"]["rows"] = 1
    with pytest.raises(upgrade.UpgradeError, match="new_tables_not_empty"):
        upgrade.compare_snapshots(before, after, allow_new_tables=True)


@pytest.mark.parametrize("part", ["rows", "sha256", "columns_sha256"])
def test_existing_table_row_column_or_content_changes_fail(part):
    before, after = snapshot(), snapshot()
    after["database"]["tables"]["synthetic"][part] = "changed"
    with pytest.raises(upgrade.UpgradeError, match="old_table_content_changed"):
        upgrade.compare_snapshots(before, after, allow_new_tables=True)


def test_cas_missing_changed_or_unexpected_restore_bytes_fail():
    before, after = snapshot(), snapshot()
    after["cas"]["files"] = {}
    with pytest.raises(upgrade.UpgradeError, match="old_cas_files_missing"):
        upgrade.compare_snapshots(before, after)
    after = snapshot()
    next(iter(after["cas"]["files"].values()))["sha256"] = "bad"
    with pytest.raises(upgrade.UpgradeError, match="old_cas_content_changed"):
        upgrade.compare_snapshots(before, after)
    after = snapshot()
    after["cas"]["files"]["unexpected"] = {"size": 1, "sha256": "d" * 64}
    with pytest.raises(upgrade.UpgradeError, match="restore_cas_set_changed"):
        upgrade.compare_snapshots(before, after)


def test_api_projection_may_add_fields_but_not_change_old_values_or_types():
    original = {"version": "exact-old", "message": [{"quote": "unaltered"}], "verified": True}
    assert upgrade.projection_preserved(original, {**original, "new_field": "allowed"})
    assert not upgrade.projection_preserved(original, {**original, "version": "new"})
    assert not upgrade.projection_preserved(original, {**original, "message": []})
    assert not upgrade.projection_preserved(original, {**original, "verified": 1})


def state_config(artifacts):
    state = artifacts / "pivot-upgrade-old-1234abcd"
    state.mkdir(mode=0o700)
    credentials = state / "credentials.json"
    credentials.write_text("{}")
    credentials.chmod(0o600)
    return state, {
        "project": state.name,
        "key": "",
        "access": "tunnel",
        "email": "operator@example.test",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"project": "pivot-app"},
        {"project": "publishing-os"},
        {"key": "synthetic-private-placeholder"},
        {"access": "https"},
        {"email": "editor@publishing.test"},
    ],
)
def test_user_project_or_live_configuration_is_never_accepted(artifacts, changes):
    state, config = state_config(artifacts)
    with pytest.raises(upgrade.UpgradeError):
        upgrade.require_test_config(state, {**config, **changes})


def test_state_and_generated_credential_modes_are_enforced_without_reading_them(artifacts):
    state, config = state_config(artifacts)
    upgrade.require_test_config(state, config)
    (state / "credentials.json").chmod(0o644)
    with pytest.raises(upgrade.UpgradeError, match="private_credential_mode_required"):
        upgrade.require_test_config(state, config)


def test_report_cannot_overwrite_arbitrary_private_state_filename(artifacts):
    with pytest.raises(upgrade.UpgradeError, match="upgrade_report_name_required"):
        upgrade.write_report(artifacts / "credentials.json", {"passed": False})
    report = artifacts / "vps-upgrade-contract.json"
    upgrade.write_report(report, {"passed": False, "provider": "mock"})
    assert report.stat().st_mode & 0o077 == 0
    assert json.loads(report.read_text())["provider"] == "mock"


def test_command_failure_does_not_print_captured_secret_output(monkeypatch, capsys):
    secret = "synthetic-private-value-never-output"
    monkeypatch.setattr(
        upgrade.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout=secret, stderr=secret),
    )
    with pytest.raises(upgrade.UpgradeError, match="isolated_command_failed") as raised:
        upgrade.safe_run(["synthetic-command"])
    assert secret not in str(raised.value) and secret not in capsys.readouterr().out


def test_docker_child_environment_never_inherits_model_or_application_credentials(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-key")
    monkeypatch.setenv("PIVOT_OPERATOR_PASSWORD", "synthetic-password")
    monkeypatch.setenv("DATABASE_URL", "synthetic-url")
    assert "DEEPSEEK_API_KEY" not in upgrade.docker_environment()
    assert "PIVOT_OPERATOR_PASSWORD" not in upgrade.docker_environment()
    assert "DATABASE_URL" not in upgrade.docker_environment()
    assert upgrade.docker_environment().get("PATH") == os.environ.get("PATH")


def column_hash(columns):
    return hashlib.sha256(
        json.dumps(columns, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def identity_snapshots():
    before = snapshot()
    before["database"]["schema"] = "public"
    for name, names in {
        "memberships": ["id", "user_id", "journal_id", "role"],
        "login_sessions": ["token_hash", "user_id", "csrf_token", "expires_at"],
    }.items():
        columns = [{"name": field, "type": "VARCHAR(36)", "nullable": False} for field in names]
        before["database"]["tables"][name] = {
            "rows": 2,
            "sha256": "c" * 64,
            "columns": columns,
            "columns_sha256": column_hash(columns),
            "primary_key": {"name": name + "_pkey", "columns": [names[0]]},
            "unique_constraints": [],
            "foreign_keys": [],
        }
    synthetic = before["database"]["tables"]["synthetic"]
    synthetic["primary_key"] = {"name": "synthetic_pkey", "columns": ["id"]}
    synthetic["columns"] = [{"name": "id", "type": "VARCHAR(36)", "nullable": False}]
    before["database"]["tables"]["memberships"]["unique_constraints"] = [
        deepcopy(upgrade.OLD_MEMBERSHIP_UNIQUE)
    ]
    before["database"]["session_bindings"] = {"expected": {"rows": 2, "sha256": "e" * 64}}
    after = deepcopy(before)
    after["database"]["schema_head"] = "29b6d4a01c75"
    for item in after["database"]["tables"].values():
        item["preserved"] = {
            key: deepcopy(item[key]) for key in ("rows", "sha256", "columns_sha256", "primary_key")
        }
    sessions = after["database"]["tables"]["login_sessions"]
    sessions["columns"].append(deepcopy(upgrade.IDENTITY_COLUMN))
    sessions["columns_sha256"] = column_hash(sessions["columns"])
    sessions["sha256"] = "f" * 64
    sessions["foreign_keys"] = [
        {
            "name": "fk_session_active_membership_user",
            "columns": ["active_membership_id", "user_id"],
            "schema": "public",
            "table": "memberships",
            "referred_columns": ["id", "user_id"],
            "options": {},
        }
    ]
    after["database"]["tables"]["memberships"]["unique_constraints"] = deepcopy(
        upgrade.NEW_MEMBERSHIP_UNIQUES
    )
    after["database"]["session_bindings"]["actual"] = deepcopy(
        before["database"]["session_bindings"]["expected"]
    )
    return before, after


def compare_identity(before, after):
    return upgrade.compare_snapshots(
        before, after, allow_new_tables=True, allow_identity_migration=True
    )


def test_identity_upgrade_preserves_all_old_columns_and_explicitly_reports_schema_change():
    before, after = identity_snapshots()
    result = compare_identity(before, after)
    assert result["all_old_columns_equal"] and result["all_old_primary_keys_equal"]
    assert result["identity_membership_migration_verified"]
    assert not result["all_old_tables_equal"]
    with pytest.raises(upgrade.UpgradeError, match="old_table_content_changed"):
        upgrade.compare_snapshots(before, after, allow_new_tables=True)
    with pytest.raises(upgrade.UpgradeError, match="identity_migration_upgrade_only"):
        upgrade.compare_snapshots(before, after, allow_identity_migration=True)


@pytest.mark.parametrize(
    "damage",
    [
        "old_value",
        "old_primary_key",
        "session_count",
        "missing_old_column",
        "old_column_type",
        "extra_column",
        "active_type",
        "active_nullability",
        "missing_fk",
        "foreign_user_fk",
        "fk_cascade",
        "missing_role_unique",
        "extra_unique",
        "old_unique_retained",
        "membership_value",
        "unrelated_table",
        "missing_projection",
    ],
)
def test_identity_upgrade_never_loosens_unrelated_data_or_schema(damage):
    before, after = identity_snapshots()
    tables = after["database"]["tables"]
    sessions, members = tables["login_sessions"], tables["memberships"]
    if damage == "old_value":
        sessions["preserved"]["sha256"] = "changed"
    elif damage == "old_primary_key":
        sessions["primary_key"]["columns"] = ["user_id"]
        sessions["preserved"]["primary_key"]["columns"] = ["user_id"]
    elif damage == "session_count":
        sessions["rows"] += 1
        sessions["preserved"]["rows"] += 1
    elif damage == "missing_old_column":
        sessions["columns"].pop(1)
    elif damage == "old_column_type":
        sessions["columns"][1]["type"] = "TEXT"
    elif damage == "extra_column":
        sessions["columns"].append({"name": "other", "type": "TEXT", "nullable": True})
    elif damage == "active_type":
        sessions["columns"][-1]["type"] = "TEXT"
    elif damage == "active_nullability":
        sessions["columns"][-1]["nullable"] = False
    elif damage == "missing_fk":
        sessions["foreign_keys"] = []
    elif damage == "foreign_user_fk":
        sessions["foreign_keys"][0]["columns"] = ["active_membership_id"]
        sessions["foreign_keys"][0]["referred_columns"] = ["id"]
    elif damage == "fk_cascade":
        sessions["foreign_keys"][0]["options"] = {"ondelete": "CASCADE"}
    elif damage == "missing_role_unique":
        members["unique_constraints"].pop(0)
    elif damage == "extra_unique":
        members["unique_constraints"].append({"name": "other", "columns": ["role"]})
    elif damage == "old_unique_retained":
        members["unique_constraints"].append(deepcopy(upgrade.OLD_MEMBERSHIP_UNIQUE))
    elif damage == "membership_value":
        members["sha256"] = "changed"
    elif damage == "unrelated_table":
        tables["synthetic"]["sha256"] = "changed"
    else:
        sessions.pop("preserved")
    with pytest.raises(upgrade.UpgradeError):
        compare_identity(before, after)


@pytest.mark.parametrize(
    "binding", [None, {"rows": 2, "sha256": "wrong"}, {"rows": 1, "sha256": "e" * 64}]
)
def test_identity_backfill_rejects_missing_wrong_or_incomplete_memberships(binding):
    before, after = identity_snapshots()
    after["database"]["session_bindings"]["actual"] = binding
    with pytest.raises(upgrade.UpgradeError, match="session_membership_backfill_invalid"):
        compare_identity(before, after)


def test_candidate_restore_compares_full_session_column_and_schema_snapshots():
    _, candidate = identity_snapshots()
    for item in candidate["database"]["tables"].values():
        item.pop("preserved")
    result = upgrade.compare_snapshots(candidate, deepcopy(candidate))
    assert result["all_old_tables_equal"]
    assert not result["identity_membership_migration_verified"]
    for field in ("sha256", "columns_sha256", "primary_key", "unique_constraints", "foreign_keys"):
        altered = deepcopy(candidate)
        altered["database"]["tables"]["login_sessions"][field] = "changed"
        with pytest.raises(upgrade.UpgradeError, match="old_table_content_changed"):
            upgrade.compare_snapshots(candidate, altered)
    altered = deepcopy(candidate)
    altered["database"]["schema_head"] = "unexpected"
    with pytest.raises(upgrade.UpgradeError, match="restore_schema_head_changed"):
        upgrade.compare_snapshots(candidate, altered)


def test_capture_passes_only_baseline_schema_to_the_database_program(artifacts, monkeypatch):
    before, _ = identity_snapshots()
    state, config = state_config(artifacts)
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="{}")

    deployment = SimpleNamespace(state=state, config=config, dc=command)
    monkeypatch.setattr(upgrade, "require_test_config", lambda *args: None)
    upgrade.capture(deployment, baseline=before)
    schema = json.loads(calls[0][-1])
    assert set(schema) == set(before["database"]["tables"])
    assert all(set(item) == {"columns", "primary_key"} for item in schema.values())
    assert all("rows" not in item and "sha256" not in item for item in schema.values())
    assert len(calls[1]) == 6  # CAS gets no database schema or private row input.


def test_snapshot_sql_preserves_real_rows_backfill_and_constraints_in_rolled_back_schema():
    namespace = {"__name__": "snapshot_sql_contract"}
    exec(upgrade.DB_SNAPSHOT, namespace)
    scan = namespace["scan_database"]
    schema = "upgrade_scan_" + uuid4().hex

    def qualified(name):
        return '"' + schema + '"."' + name + '"'

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
            metadata = MetaData(schema=schema)
            version = Table(
                "alembic_version", metadata, Column("version_num", String(32), primary_key=True)
            )
            members = Table(
                "memberships",
                metadata,
                Column("id", String(36), primary_key=True),
                Column("user_id", String(36), nullable=False),
                Column("journal_id", String(36), nullable=False),
                Column("role", String(30), nullable=False),
                UniqueConstraint(
                    "user_id", "journal_id", name="memberships_user_id_journal_id_key"
                ),
            )
            sessions = Table(
                "login_sessions",
                metadata,
                Column("token_hash", String(64), primary_key=True),
                Column("user_id", String(36), nullable=False),
                Column("csrf_token", String(64), nullable=False),
                Column("expires_at", DateTime(timezone=True), nullable=False),
            )
            metadata.create_all(connection)
            connection.execute(version.insert(), {"version_num": "old"})
            connection.execute(
                members.insert(),
                [
                    {"id": "m1", "user_id": "u1", "journal_id": "j1", "role": "editor"},
                    {"id": "m2", "user_id": "u2", "journal_id": "j1", "role": "reviewer"},
                    {"id": "m3", "user_id": "u2", "journal_id": "j2", "role": "author"},
                ],
            )
            connection.execute(
                sessions.insert(),
                [
                    {
                        "token_hash": "s" + str(i),
                        "user_id": "u" + str(i),
                        "csrf_token": "synthetic-csrf-" + str(i),
                        "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
                    }
                    for i in (1, 2, 3)
                ],
            )
            before = {"database": scan(connection, schema), "cas": {"files": {}}}
            baseline = {
                name: {key: item[key] for key in ("columns", "primary_key")}
                for name, item in before["database"]["tables"].items()
            }
            for sql in [
                "ALTER TABLE "
                + qualified("memberships")
                + " DROP CONSTRAINT memberships_user_id_journal_id_key",
                "ALTER TABLE "
                + qualified("memberships")
                + " ADD CONSTRAINT uq_membership_user_journal_role UNIQUE(user_id,journal_id,role)",
                "ALTER TABLE "
                + qualified("memberships")
                + " ADD CONSTRAINT uq_membership_id_user UNIQUE(id,user_id)",
                "ALTER TABLE "
                + qualified("login_sessions")
                + " ADD COLUMN active_membership_id VARCHAR(36)",
                "ALTER TABLE "
                + qualified("login_sessions")
                + " ADD CONSTRAINT fk_session_active_membership_user FOREIGN KEY(active_membership_id,user_id) REFERENCES "
                + qualified("memberships")
                + "(id,user_id)",
                "UPDATE "
                + qualified("login_sessions")
                + " s SET active_membership_id=m.id FROM "
                + qualified("memberships")
                + " m WHERE m.user_id=s.user_id AND (SELECT count(*) FROM "
                + qualified("memberships")
                + " x WHERE x.user_id=s.user_id)=1",
                "UPDATE " + qualified("alembic_version") + " SET version_num='29b6d4a01c75'",
            ]:
                connection.execute(text(sql))
            after = {"database": scan(connection, schema, baseline), "cas": {"files": {}}}
            assert compare_identity(before, after)["identity_membership_migration_verified"]
            assert (
                before["database"]["session_bindings"]["expected"]
                == after["database"]["session_bindings"]["actual"]
            )
            assert (
                before["database"]["tables"]["login_sessions"]["sha256"]
                != after["database"]["tables"]["login_sessions"]["sha256"]
            )
            assert "synthetic-csrf" not in json.dumps(after)
            candidate = {"database": scan(connection, schema), "cas": {"files": {}}}
            for damage in [
                "UPDATE "
                + qualified("login_sessions")
                + " SET csrf_token='changed' WHERE token_hash='s1'",
                "UPDATE "
                + qualified("login_sessions")
                + " SET active_membership_id=NULL WHERE token_hash='s1'",
                "UPDATE "
                + qualified("login_sessions")
                + " SET active_membership_id='m2' WHERE token_hash='s2'",
                "ALTER TABLE " + qualified("login_sessions") + " ADD COLUMN unexpected TEXT",
                "ALTER TABLE "
                + qualified("memberships")
                + " DROP CONSTRAINT uq_membership_user_journal_role",
                "ALTER TABLE "
                + qualified("login_sessions")
                + " DROP CONSTRAINT login_sessions_pkey, ADD CONSTRAINT login_sessions_pkey PRIMARY KEY(token_hash,user_id)",
            ]:
                savepoint = connection.begin_nested()
                try:
                    connection.execute(text(damage))
                    changed = {"database": scan(connection, schema, baseline), "cas": {"files": {}}}
                    with pytest.raises(upgrade.UpgradeError):
                        compare_identity(before, changed)
                    strict = {"database": scan(connection, schema), "cas": {"files": {}}}
                    with pytest.raises(upgrade.UpgradeError):
                        upgrade.compare_snapshots(candidate, strict)
                finally:
                    savepoint.rollback()
            assert upgrade.compare_snapshots(
                candidate, {"database": scan(connection, schema), "cas": {"files": {}}}
            )["all_old_tables_equal"]
        finally:
            transaction.rollback()
