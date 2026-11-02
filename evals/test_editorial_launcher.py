"""Secret handling of interactive local launcher; no Docker or network executed."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "start-live-model.py"
spec = importlib.util.spec_from_file_location("editorial_launcher", PATH)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_launcher_injects_environment_without_echo_arguments_or_files(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(launcher.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(launcher.getpass, "getpass", lambda _: "fresh-local-fixture-never-live")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    assert launcher.main() == 0
    args, kwargs = calls[0]
    assert kwargs["env"]["DEEPSEEK_API_KEY"] == "fresh-local-fixture-never-live"
    assert kwargs["env"]["EDITORIAL_MODEL_PROVIDER"] == "deepseek"
    assert kwargs["env"]["EDITORIAL_MODEL_LIVE_ENABLED"] == "true"
    assert "fixture" not in str(args)
    output = capsys.readouterr()
    assert "fresh-local-fixture-never-live" not in output.out + output.err
    assert args == ["docker", "compose", "up", "--build", "-d", "--wait"]


def test_missing_key_noninteractive_fails_before_start(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(launcher.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    def unexpected(*args, **kwargs):
        pytest.fail("Missing credentials must not start model service")

    monkeypatch.setattr(launcher.subprocess, "run", unexpected)
    assert launcher.main() == 2
    assert "无回显" in capsys.readouterr().err


@pytest.mark.parametrize("key", ["", "replace-me", "line\nbreak", "white space", " leading"])
def test_invalid_environment_credentials_not_echoed_or_used(monkeypatch, capsys, key):
    monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    monkeypatch.setattr(launcher.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid credentials must not start service")

    monkeypatch.setattr(launcher.subprocess, "run", unexpected)
    assert launcher.main() == 2
    captured = capsys.readouterr()
    if key:
        assert key not in captured.out + captured.err
