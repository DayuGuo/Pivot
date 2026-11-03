"""Credential preservation is checked with fake Docker processes only."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "start-local.py"
spec = importlib.util.spec_from_file_location("local_start", PATH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    for name in ("DEEPSEEK_API_KEY", "EDITORIAL_MODEL_PROVIDER", "EDITORIAL_MODEL_LIVE_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def docker(
    monkeypatch,
    *,
    existing=True,
    provider="deepseek",
    key="fixture-current-private",
    malformed=False,
    warm_code=0,
    read_code=0,
):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if "ps" in args:
            return SimpleNamespace(returncode=0, stdout="fixture-container\n" if existing else "")
        if "--no-recreate" in args:
            return SimpleNamespace(returncode=warm_code)
        if "exec" in args:
            assert kwargs["capture_output"] and kwargs["text"]
            return SimpleNamespace(
                returncode=read_code,
                stdout=key
                if malformed
                else json.dumps({"provider": provider, "live": "true", "key": key}),
            )
        assert args == ["docker", "compose", "up", "-d", "--build", "--wait"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    return calls


def test_default_restart_preserves_live_key_only_in_child_environment(monkeypatch, capsys):
    calls = docker(monkeypatch)
    assert launcher.main() == 0
    final_args, final = calls[-1]
    assert final["env"]["DEEPSEEK_API_KEY"] == "fixture-current-private"
    assert final["env"]["EDITORIAL_MODEL_PROVIDER"] == "deepseek"
    assert final["env"]["EDITORIAL_MODEL_LIVE_ENABLED"] == "true"
    assert "fixture-current-private" not in json.dumps(final_args)
    assert "fixture-current-private" not in str(capsys.readouterr())
    assert any("--no-recreate" in args for args, _ in calls)


def test_host_fresh_key_overrides_old_runtime_without_echo(monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-fresh-private")
    calls = docker(monkeypatch)
    assert launcher.main() == 0
    assert calls[-1][1]["env"]["DEEPSEEK_API_KEY"] == "fixture-fresh-private"
    assert "fixture-fresh-private" not in str(capsys.readouterr())


def test_first_start_keeps_default_mock_without_reading_any_runtime_secret(monkeypatch):
    calls = docker(monkeypatch, existing=False)
    assert launcher.main() == 0
    assert len(calls) == 2
    assert "DEEPSEEK_API_KEY" not in calls[-1][1]["env"]


def test_explicit_mock_switch_does_not_read_existing_live_key(monkeypatch):
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "mock")
    calls = docker(monkeypatch)
    assert launcher.main() == 0
    assert len(calls) == 1
    assert calls[0][1]["env"]["EDITORIAL_MODEL_PROVIDER"] == "mock"


@pytest.mark.parametrize("name", ["EDITORIAL_MODEL_PROVIDER", "EDITORIAL_MODEL_LIVE_ENABLED"])
def test_empty_host_setting_does_not_erase_valid_existing_live_configuration(monkeypatch, name):
    monkeypatch.setenv(name, "")
    calls = docker(monkeypatch)
    assert launcher.main() == 0
    assert calls[-1][1]["env"]["EDITORIAL_MODEL_PROVIDER"] == "deepseek"
    assert calls[-1][1]["env"]["EDITORIAL_MODEL_LIVE_ENABLED"] == "true"


def test_unknown_host_provider_cannot_replace_valid_existing_live_configuration(monkeypatch):
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "mistyped-provider")
    calls = docker(monkeypatch)
    assert launcher.main() == 2
    assert not any("--build" in args for args, _ in calls)


@pytest.mark.parametrize(
    "settings",
    [
        {"malformed": True},
        {"warm_code": 1},
        {"read_code": 1},
        {"key": ""},
        {"key": "fixture bad key"},
        {"provider": "unsupported-private-provider"},
    ],
)
def test_restore_failure_never_recreates_or_prints_captured_secret(monkeypatch, capsys, settings):
    calls = docker(monkeypatch, **settings)
    assert launcher.main() == 2
    assert not any("--build" in args for args, _ in calls)
    output = str(capsys.readouterr())
    assert "fixture-current-private" not in output and "unsupported-private-provider" not in output
