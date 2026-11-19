"""Isolated launcher/acceptance guards. No real provider, Docker or DB calls."""

import importlib.util
import json
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


launcher = module("trial_launcher", "scripts/start-trial-live.py")
live = module("trial_live", "evals/editorial_trial/live.py")
evaluator = module("trial_public", "scripts/evaluate-public-papers.py")


def test_explicit_live_required_before_reading_secret(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["start-trial-live.py"])
    monkeypatch.setattr(launcher, "fresh_key", lambda: pytest.fail("must not read"))
    with pytest.raises(SystemExit) as error:
        launcher.main()
    assert error.value.code == 2


def test_missing_key_noninteractive_does_not_start(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["start-trial-live.py", "--live"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("must not start"))
    assert launcher.main() == 2


def test_no_echo_fallback_is_refused(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def insecure(_):
        warnings.warn("cannot disable echo", launcher.getpass.GetPassWarning, stacklevel=1)
        pytest.fail("must not read fallback")

    monkeypatch.setattr(launcher.getpass, "getpass", insecure)
    with pytest.raises(launcher.getpass.GetPassWarning):
        launcher.fresh_key()


def test_fixed_project_stdin_free_no_logs_and_child_key_removed(monkeypatch, capsys):
    secret = "fixture-not-a-live-credential"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    monkeypatch.setenv("DOCKER_HOST", "ssh://remote.invalid")
    monkeypatch.setenv("DOCKER_CONTEXT", "remote-production")
    monkeypatch.setattr(sys, "argv", ["start-trial-live.py", "--live"])
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=secret, stderr=secret)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 0
    args, settings = calls[0]
    assert args[:7] == [
        "docker",
        "--host",
        "unix:///var/run/docker.sock",
        "compose",
        "-p",
        "pivot-trial-live",
        "-f",
    ]
    assert "DOCKER_HOST" not in settings["env"]
    assert "DOCKER_CONTEXT" not in settings["env"]
    assert args[-3:] == ["db", "api", "mailpit"]
    assert secret not in str(args)
    assert settings["env"]["DEEPSEEK_API_KEY"] == secret
    assert settings["capture_output"] is True
    assert "DEEPSEEK_API_KEY" not in calls[1][1]["env"]
    assert secret not in str(capsys.readouterr())


def test_start_failure_suppresses_child_output(monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-secret")
    monkeypatch.setattr(sys, "argv", ["start-trial-live.py", "--live"])
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="fixture-secret", stderr="fixture-secret"
        ),
    )
    assert launcher.main() == 1
    assert "fixture-secret" not in str(capsys.readouterr())


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "http://user:secret@localhost",
        "http://127.0.0.1/remote",
        "http://localhost?url=remote",
    ],
)
def test_public_staging_refuses_external_targets_before_network(url, monkeypatch):
    monkeypatch.setattr(evaluator.httpx, "Client", lambda **k: pytest.fail("no network"))
    with pytest.raises(ValueError, match="local_api_required"):
        evaluator.stage({}, base_url=url)


def test_pinned_selection_is_two_distinct_original_formats():
    selected = live.selected_manifest(
        json.loads((ROOT / "evals/public_documents/manifest.json").read_text())
    )
    files = [f for p in selected["papers"] for f in p["files"]]
    assert len(files) == 2 and {f["format"] for f in files} == {"pdf", "docx"}
    assert all("derived_from" not in f for f in files)
    with pytest.raises(ValueError, match="public_cases_missing"):
        live.selected_manifest({"papers": []})


def test_overlay_does_not_inherit_mail_credentials_or_main_ports():
    content = (ROOT / "infrastructure/compose.trial-live.yaml").read_text()
    assert "env_file: !reset []" in content
    assert 'EMAIL_SEND_ENABLED: "false"' in content
    assert "127.0.0.1:55434:5432" in content
    assert "127.0.0.1:18101:8100" in content
    assert "127.0.0.1:18026:8025" in content


@pytest.mark.parametrize(
    "field,value",
    [("corresponding", False), ("orcid", "invented"), ("email", ""), ("affiliations", [])],
)
def test_author_gate_detects_missing_and_misassigned_fields(field, value):
    expected = {
        "name": "Synthetic Author",
        "email": "test@example.invalid",
        "affiliations": ["Synthetic Institute"],
        "corresponding": True,
        "orcid": None,
    }
    assert evaluator.author_audit([expected], [expected])["passed"]
    assert not evaluator.author_audit([expected], [{**expected, field: value}])["passed"]


def test_required_checks_survive_python_optimization():
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "import runpy; m=runpy.run_path('scripts/evaluate-public-papers.py'); m['require'](False, 'guard_remains_active')",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "guard_remains_active" in result.stderr
