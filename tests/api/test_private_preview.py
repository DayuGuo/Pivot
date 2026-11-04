"""Private bootstrap never enables the published local-demo credentials."""

import importlib.util
from pathlib import Path

import pytest

from apps.api.publishing.bootstrap import DEMO_USERS, configured_users

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "preview_manage", ROOT / "infrastructure/vps/manage.py"
)
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


def private(monkeypatch):
    monkeypatch.setenv("PIVOT_BOOTSTRAP_PROFILE", "private-preview")
    monkeypatch.setenv("PIVOT_OPERATOR_EMAIL", "owner@example.test")
    monkeypatch.setenv("PIVOT_OPERATOR_PASSWORD", "PrivateLocalTest2026!")


def test_private_bootstrap_only_operator_password_known(monkeypatch):
    private(monkeypatch)
    users = configured_users()
    assert users[0] == ("owner@example.test", "编辑", "editor", "PrivateLocalTest2026!")
    assert len(users) == 7
    for user in users[1:]:
        old = next(item for item in DEMO_USERS if item[0] == user[0])
        assert user[:3] == old[:3]
        assert user[3] != old[3]
        assert len(user[3]) >= 48
    assert {item[3] for item in users[1:]}.isdisjoint({item[3] for item in configured_users()[1:]})


@pytest.mark.parametrize(
    "key,value",
    [
        ("PIVOT_BOOTSTRAP_PROFILE", "typo"),
        ("PIVOT_OPERATOR_EMAIL", "editor@publishing.test"),
        ("PIVOT_OPERATOR_EMAIL", "bad"),
        ("PIVOT_OPERATOR_PASSWORD", "short"),
        ("PIVOT_OPERATOR_PASSWORD", ""),
    ],
)
def test_invalid_private_configuration_fails_before_write(monkeypatch, key, value):
    private(monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError):
        configured_users()


def config():
    return dict(
        email="owner@example.test",
        password="PrivateLocalTest2026!",
        key="",
        access="tunnel",
        port=3210,
        project="pivot-test",
    )


def test_private_state_permissions_no_reinit_or_secret_arguments(tmp_path):
    state = tmp_path / "state"
    c = manage.configure(state, **config())
    assert state.stat().st_mode & 0o777 == 0o700
    assert (state / "credentials.json").stat().st_mode & 0o777 == 0o600
    assert manage.read_config(state) == c
    manifest = {"images": {"api": "a", "web": "w", "db": "d"}}
    deployment = manage.Deployment(state, c, manifest)
    assert c["password"] not in " ".join(deployment.command)
    assert c["db_password"] not in " ".join(deployment.command)
    assert deployment.env["PIVOT_COOKIE_SECURE"] == "false"
    with pytest.raises(manage.PreviewError):
        manage.configure(state, **config())
    (state / "credentials.json").chmod(0o644)
    with pytest.raises(manage.PreviewError):
        manage.read_config(state)


@pytest.mark.parametrize(
    "field,value",
    [
        ("project", "publishing-os"),
        ("project", "pivot-../../old"),
        ("port", 80),
        ("port", True),
        ("email", "editor@publishing.test"),
        ("access", "http-public"),
        ("password", "short"),
        ("db_password", "unsafe@url"),
    ],
)
def test_manager_refuses_unsafe_configuration(tmp_path, field, value):
    c = {**config(), "db_password": "A" * 48, field: value}
    with pytest.raises(manage.PreviewError):
        manage.validate_config(c)
    assert not (tmp_path / "credentials.json").exists()


def test_model_and_secure_cookie_environment_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "old-static-site")
    c = manage.configure(
        tmp_path / "state",
        **{**config(), "access": "https", "key": "synthetic-model-key-not-live-123456"},
    )
    env = manage.environment(c, {"images": {"api": "a", "web": "w", "db": "d"}})
    assert "COMPOSE_PROJECT_NAME" not in env
    assert env["PIVOT_MODEL_PROVIDER"] == "deepseek"
    assert env["PIVOT_COOKIE_SECURE"] == "true"
    assert env["PIVOT_MODEL_KEY"] == c["key"]
