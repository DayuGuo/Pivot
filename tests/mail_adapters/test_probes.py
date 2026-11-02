import importlib
import smtplib
import ssl
from dataclasses import replace

import httpx
import pytest

from packages.mail_adapters import MailCredentials, ProbeConfig, ProbeResult, probe

adapter = importlib.import_module("packages.mail_adapters.probe")
ADDRESS = "editor@example.test"
TOKEN = "synthetic-token-do-not-log"
PASSWORD = "synthetic-password-do-not-log"
SMTP = ProbeConfig("smtp", ADDRESS, "smtp.example.test", 587, auth_mode="password")
TARGETS = {("smtp.example.test", 587), ("mailpit", 1025)}


def cloud(provider="gmail"):
    return ProbeConfig(provider, ADDRESS, auth_mode="oauth2")


def check(config, credentials=None, transport=None, targets=None):
    return probe(
        config,
        credentials or MailCredentials(access_token=TOKEN, password=PASSWORD),
        allowed_smtp_targets=TARGETS if targets is None else targets,
        transport=transport,
    )


def test_credentials_repr_omits_values():
    credentials = MailCredentials(password=PASSWORD, access_token=TOKEN)
    assert repr(credentials) == "MailCredentials()"


@pytest.mark.parametrize(
    ("provider", "url", "profile"),
    [
        ("gmail", adapter.GMAIL_PROFILE_URL, {"emailAddress": ADDRESS.upper()}),
        ("outlook", adapter.OUTLOOK_PROFILE_URL, {"mail": ADDRESS, "userPrincipalName": "x@test"}),
        ("outlook", adapter.OUTLOOK_PROFILE_URL, {"mail": None, "userPrincipalName": ADDRESS}),
    ],
)
def test_cloud_fixed_get_identity_only(provider, url, profile, caplog, capsys):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == url
        assert request.url.scheme == "https"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert not request.content
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 8
        )
        return httpx.Response(200, json=profile)

    assert check(cloud(provider), transport=httpx.MockTransport(handler)) == ProbeResult("verified")
    assert len(calls) == 1
    assert TOKEN not in caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_cloud_credentials_required_without_network(provider):
    def unexpected(request):
        pytest.fail("Credentials missing must not create an HTTP request")

    assert check(
        cloud(provider), MailCredentials(), httpx.MockTransport(unexpected)
    ) == ProbeResult("credentials_required", "credentials_missing")


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_cloud_wrong_identity(provider):
    profile = {"emailAddress": "other@example.test", "mail": "other@example.test"}
    result = check(
        cloud(provider), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=profile))
    )
    assert result == ProbeResult("blocked", "identity_mismatch")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
    ],
)
def test_cloud_http_errors_do_not_return_provider_content(status, expected):
    result = check(
        cloud(), transport=httpx.MockTransport(lambda _: httpx.Response(status, text=TOKEN))
    )
    assert result == ProbeResult("error", expected)
    assert TOKEN not in repr(result)


def test_cloud_redirect_is_not_followed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://attacker.example.test/collect"})

    assert check(cloud(), transport=httpx.MockTransport(handler)) == ProbeResult(
        "blocked", "redirect_blocked"
    )
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"{}", b'{"emailAddress":42}', b"x" * 65537])
def test_cloud_malformed_response(body):
    assert check(
        cloud(), transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) == ProbeResult("error", "provider_response_invalid")


@pytest.mark.parametrize(
    ("exception", "code"),
    [(httpx.ReadTimeout(TOKEN), "timeout"), (httpx.ConnectError(TOKEN), "network_error")],
)
def test_cloud_transport_failure_is_sanitized(exception, code):
    def handler(request):
        raise exception

    result = check(cloud(), transport=httpx.MockTransport(handler))
    assert result == ProbeResult("error", code)
    assert TOKEN not in repr(result)


@pytest.mark.parametrize("token", ["bad\r\nInjected: token", "with space", "nonascii-密码"])
def test_cloud_rejects_unsafe_token_without_network(token):
    assert check(cloud(), MailCredentials(access_token=token)) == ProbeResult(
        "blocked", "invalid_credentials"
    )


@pytest.fixture
def smtp_log(monkeypatch):
    operations = []

    class FakeSMTP:
        def __init__(self, host, port, **options):
            operations.append(("connect", host, port, options))
            assert options["timeout"] == 8

        def ehlo(self):
            operations.append(("ehlo",))
            return 250, b"synthetic greeting"

        def starttls(self, *, context):
            operations.append(("starttls", context))
            return 220, b"synthetic tls"

        def login(self, username, password):
            operations.append(("auth", username))
            assert password == PASSWORD
            return 235, b"synthetic auth"

        def close(self):
            operations.append(("close",))

        def sendmail(self, *args, **kwargs):
            pytest.fail("Sending is forbidden")

        send_message = mail = rcpt = data = sendmail

    monkeypatch.setattr(adapter.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(adapter.smtplib, "SMTP_SSL", FakeSMTP)
    return operations, FakeSMTP


def test_smtp_starttls_auth_no_envelope(smtp_log, caplog, capsys):
    operations, _ = smtp_log
    assert check(SMTP) == ProbeResult("verified")
    assert [op[0] for op in operations] == ["connect", "ehlo", "starttls", "ehlo", "auth", "close"]
    assert operations[2][1].verify_mode == ssl.CERT_REQUIRED
    assert operations[2][1].check_hostname is True
    assert operations[4][1] == ADDRESS
    assert PASSWORD not in repr(operations) + caplog.text + capsys.readouterr().out


def test_smtp_implicit_tls_verified(smtp_log):
    operations, _ = smtp_log
    assert check(replace(SMTP, tls_mode="tls")) == ProbeResult("verified")
    context = operations[0][3]["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert [op[0] for op in operations] == ["connect", "ehlo", "auth", "close"]


def test_smtp_local_mailpit_ehlo_only(smtp_log):
    operations, _ = smtp_log
    assert check(ProbeConfig("smtp", ADDRESS, "mailpit", 1025, "none")) == ProbeResult("verified")
    assert [op[0] for op in operations] == ["connect", "ehlo", "close"]


def test_smtp_exact_allowlist_and_plaintext_rejection(smtp_log):
    operations, _ = smtp_log
    assert check(SMTP, targets=set()) == ProbeResult("blocked", "smtp_target_blocked")
    assert check(replace(SMTP, smtp_host="SMTP.example.test")) == ProbeResult(
        "blocked", "smtp_target_blocked"
    )
    assert check(replace(SMTP, tls_mode="none")) == ProbeResult("blocked", "smtp_tls_required")
    assert not operations


@pytest.mark.parametrize(
    "host",
    [
        "smtp.test\r\nMAIL FROM:x",
        "https://smtp.test",
        "smtp.test:587",
        "smtp.test/",
        "-bad.test",
        "bad..test",
        "a" * 64 + ".test",
    ],
)
def test_smtp_unsafe_hosts_never_connect(host, smtp_log):
    assert check(replace(SMTP, smtp_host=host), targets={(host, 587)}) == ProbeResult(
        "blocked", "invalid_configuration"
    )
    assert not smtp_log[0]


@pytest.mark.parametrize("port", [0, 65536, True, "587", None])
def test_smtp_invalid_port_never_connect(port, smtp_log):
    assert check(replace(SMTP, smtp_port=port)) == ProbeResult("blocked", "invalid_configuration")
    assert not smtp_log[0]


def test_smtp_missing_password_never_connect(smtp_log):
    assert check(SMTP, MailCredentials()) == ProbeResult(
        "credentials_required", "credentials_missing"
    )
    assert not smtp_log[0]


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (smtplib.SMTPAuthenticationError(535, PASSWORD.encode()), "authentication_failed"),
        (ssl.SSLCertVerificationError(PASSWORD), "tls_failed"),
        (TimeoutError(PASSWORD), "timeout"),
        (OSError(PASSWORD), "network_error"),
    ],
)
def test_smtp_failure_sanitized_and_closed(exception, code, smtp_log, monkeypatch):
    operations, fake = smtp_log

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(fake, "login", fail)
    result = check(SMTP)
    assert result == ProbeResult("error", code)
    assert PASSWORD not in repr(result)
    assert operations[-1] == ("close",)


def test_smtp_failed_ehlo_cannot_verify(smtp_log, monkeypatch):
    _, fake = smtp_log
    monkeypatch.setattr(fake, "ehlo", lambda self: (500, b"private-provider-body"))
    assert check(SMTP) == ProbeResult("error", "smtp_protocol_error")


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (smtplib.SMTPNotSupportedError("STARTTLS not supported"), "smtp_protocol_error"),
        (ssl.SSLCertVerificationError("untrusted certificate"), "tls_failed"),
    ],
)
def test_smtp_starttls_failure_never_authenticates(exception, code, smtp_log, monkeypatch):
    operations, fake = smtp_log

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(fake, "starttls", fail)
    assert check(SMTP) == ProbeResult("error", code)
    assert [op[0] for op in operations] == ["connect", "ehlo", "close"]


def test_smtp_local_plaintext_cannot_authenticate(smtp_log):
    config = ProbeConfig("smtp", ADDRESS, "mailpit", 1025, "none", "password")
    assert check(config) == ProbeResult("blocked", "smtp_tls_required")
    assert not smtp_log[0]


def test_smtp_control_character_password_never_connects(smtp_log):
    assert check(SMTP, MailCredentials(password="secret\r\n")) == ProbeResult(
        "blocked", "invalid_credentials"
    )
    assert not smtp_log[0]


@pytest.mark.parametrize(
    "config",
    [
        replace(SMTP, username="user\r\n"),
        replace(SMTP, address="user@example.test\n"),
        replace(SMTP, auth_mode="oauth2"),
        replace(cloud(), auth_mode="password"),
        replace(cloud(), provider="unknown"),
    ],
)
def test_unsupported_or_injected_config_blocked(config, smtp_log):
    assert check(config).status == "blocked"
    assert not smtp_log[0]


def test_cloud_ignores_proxy_environment(monkeypatch):
    options = []
    original = adapter.httpx.Client

    def client(**kwargs):
        options.append(kwargs)
        return original(**kwargs)

    monkeypatch.setenv("HTTPS_PROXY", "http://attacker.example.test:8080")
    monkeypatch.setattr(adapter.httpx, "Client", client)
    assert (
        check(
            cloud(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"emailAddress": ADDRESS})
            ),
        ).status
        == "verified"
    )
    assert options[0]["trust_env"] is False
    assert options[0]["verify"].verify_mode == ssl.CERT_REQUIRED
    assert options[0]["verify"].check_hostname is True
    assert options[0]["follow_redirects"] is False


def test_tls_context_never_enables_environment_key_logging(monkeypatch, tmp_path, smtp_log):
    keylog = tmp_path / "must-not-exist.log"
    monkeypatch.setenv("SSLKEYLOGFILE", str(keylog))
    context = adapter._tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.keylog_filename is None
    assert check(SMTP).status == "verified"
    assert (
        check(
            cloud(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"emailAddress": ADDRESS})
            ),
        ).status
        == "verified"
    )
    assert not keylog.exists()
