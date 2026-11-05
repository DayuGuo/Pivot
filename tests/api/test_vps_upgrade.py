"""Pure upgrade harness boundaries; no Docker, user state, credentials or network."""

import hashlib
import importlib.util
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

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
