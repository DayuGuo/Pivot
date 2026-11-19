"""Private-package operator UI keeps secrets off argv and error output."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.api.test_private_preview import manage


def deployment():
    instance = object.__new__(manage.Deployment)
    instance.command = ["docker", "compose", "--project-name", "pivot-synthetic"]
    instance.env = {"PATH": "/usr/bin"}
    return instance


def test_account_password_only_in_subprocess_stdin(monkeypatch, capsys):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"status": "active", "revision": 1}))

    monkeypatch.setattr(manage.subprocess, "run", run)
    password = "SyntheticSecretOnlyInPipe2026!"
    deployment().trial_accounts({"action": "create", "password": password})
    args, options = calls[0]
    assert password not in str(args) and password not in str(options["env"])
    assert json.loads(options["input"])["password"] == password
    assert password not in capsys.readouterr().out


def test_child_failure_does_not_echo_secret_exception(monkeypatch, capsys):
    monkeypatch.setattr(
        manage.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=2, stdout="secret output", stderr="password-in-database-exception"
        ),
    )
    with pytest.raises(manage.PreviewError) as failure:
        deployment().trial_accounts({"action": "create"})
    assert "password-in-database" not in str(failure.value)
    assert capsys.readouterr().out == ""


def test_operator_cancellation_never_submits(monkeypatch):
    args = SimpleNamespace(
        command="trial-disable", journal=uuid4(), user=uuid4(), revision=1, request_id=uuid4()
    )
    monkeypatch.setattr("builtins.input", lambda _: "cancel")
    with pytest.raises(manage.PreviewError, match="Cancelled"):
        manage.trial_request(args)


def test_no_password_command_line_option():
    import inspect

    assert 'add_argument("--password"' not in inspect.getsource(manage.main)


def test_list_is_read_only_and_does_not_prompt(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Unexpected prompt"))
    assert manage.trial_request(SimpleNamespace(command="trial-list")) == {"action": "list"}


@pytest.mark.parametrize("action", ["create", "resume", "rotate-password"])
def test_no_tty_password_fallback_refuses_before_read_or_submit(monkeypatch, action, capsys):
    import warnings

    read_fallback = []

    def unavailable_tty(prompt):
        warnings.warn(
            "Cannot control echo on terminal", manage.getpass.GetPassWarning, stacklevel=2
        )
        read_fallback.append(True)
        return "ThisMustNeverBeRead2026!"

    monkeypatch.setattr(manage.getpass, "getpass", unavailable_tty)
    monkeypatch.setattr("builtins.input", lambda _: "synthetic@example.test")
    args = SimpleNamespace(
        command=f"trial-{action}",
        journal=uuid4(),
        request_id=uuid4(),
        user=None if action == "create" else uuid4(),
        revision=None if action == "create" else 1,
    )
    with pytest.raises(manage.PreviewError, match="secure no-echo"):
        manage.trial_request(args)
    assert read_fallback == []
    assert "ThisMustNeverBeRead" not in capsys.readouterr().out


def test_secure_input_restores_warning_filter_and_allows_terminal(monkeypatch):
    import warnings

    before = list(warnings.filters)
    monkeypatch.setattr(manage.getpass, "getpass", lambda _: "SyntheticNoEcho2026!")
    assert manage.secret_input("Password: ") == "SyntheticNoEcho2026!"
    assert warnings.filters == before
