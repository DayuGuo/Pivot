"""Bounded SMTP greeting/authentication and fixed-endpoint cloud identity checks."""

import re
import smtplib
import ssl
from dataclasses import dataclass, field

import httpx

TIMEOUT_SECONDS = 8
MAX_PROFILE_BYTES = 65536
GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
OUTLOOK_PROFILE_URL = "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName"
_HOST = re.compile(r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\Z")
_ADDRESS = re.compile(r"[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\Z", re.ASCII)


@dataclass(frozen=True)
class ProbeConfig:
    provider: str
    address: str
    smtp_host: str | None = None
    smtp_port: int | None = None
    tls_mode: str = "starttls"
    auth_mode: str = "none"
    username: str | None = None


@dataclass(frozen=True)
class MailCredentials:
    password: str | None = field(default=None, repr=False)
    access_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ProbeResult:
    status: str
    error_code: str | None = None


def _blocked(code: str) -> ProbeResult:
    return ProbeResult("blocked", code)


def _error(code: str) -> ProbeResult:
    return ProbeResult("error", code)


def _safe_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _address(value: object) -> bool:
    return isinstance(value, str) and len(value) <= 254 and bool(_ADDRESS.fullmatch(value))


def _tls_context() -> ssl.SSLContext:
    # create_default_context honors SSLKEYLOGFILE; probes must never log TLS secrets.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


def probe(
    config: ProbeConfig,
    credentials: MailCredentials,
    *,
    allowed_smtp_targets: set[tuple[str, int]],
    local_mailpit_host: str = "mailpit",
    transport: httpx.BaseTransport | None = None,
) -> ProbeResult:
    """Check connectivity and identity without reading messages or creating an envelope.

    The caller resolves environment credentials, checks ownership, and persists audit.
    All provider failures become fixed codes; provider bodies/exceptions never escape.
    """
    if not _address(config.address) or (
        config.username is not None and not _safe_text(config.username)
    ):
        return _blocked("invalid_configuration")
    if config.provider == "smtp":
        return _smtp_probe(config, credentials, allowed_smtp_targets, local_mailpit_host)
    if config.provider in {"gmail", "outlook"}:
        return _cloud_probe(config, credentials, transport)
    return _blocked("provider_unsupported")


def _cloud_probe(
    config: ProbeConfig, credentials: MailCredentials, transport: httpx.BaseTransport | None
) -> ProbeResult:
    if config.auth_mode != "oauth2":
        return _blocked("auth_mode_unsupported")
    token = credentials.access_token
    if not token:
        return ProbeResult("credentials_required", "credentials_missing")
    if not _safe_text(token) or not token.isascii() or any(char.isspace() for char in token):
        return _blocked("invalid_credentials")
    url = GMAIL_PROFILE_URL if config.provider == "gmail" else OUTLOOK_PROFILE_URL
    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
            verify=_tls_context(),
            transport=transport,
        ) as client:
            with client.stream(
                "GET",
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            ) as response:
                status = response.status_code
                if 300 <= status < 400:
                    return _blocked("redirect_blocked")
                if status == 401:
                    return _error("authentication_failed")
                if status == 403:
                    return _error("permission_denied")
                if status == 429:
                    return _error("rate_limited")
                if status != 200:
                    return _error("provider_unavailable")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=MAX_PROFILE_BYTES + 1):
                    body.extend(chunk)
                    if len(body) > MAX_PROFILE_BYTES:
                        return _error("provider_response_invalid")
                profile = httpx.Response(200, content=bytes(body)).json()
        if not isinstance(profile, dict):
            return _error("provider_response_invalid")
        fields = ("emailAddress",) if config.provider == "gmail" else ("mail", "userPrincipalName")
        identities = [profile.get(key) for key in fields if _address(profile.get(key))]
        if not identities:
            return _error("provider_response_invalid")
        if not any(identity.casefold() == config.address.casefold() for identity in identities):
            return _blocked("identity_mismatch")
        return ProbeResult("verified")
    except httpx.TimeoutException:
        return _error("timeout")
    except httpx.RequestError:
        return _error("network_error")
    except (ValueError, UnicodeError):
        return _error("provider_response_invalid")
    except Exception:
        # Never persist or return third-party exception messages, even for unexpected faults.
        return _error("probe_failed")


def _smtp_probe(
    config: ProbeConfig,
    credentials: MailCredentials,
    allowed_targets: set[tuple[str, int]],
    local_mailpit_host: str,
) -> ProbeResult:
    host, port = config.smtp_host, config.smtp_port
    if (
        not isinstance(host, str)
        or not _HOST.fullmatch(host)
        or any(
            not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
            for label in host.split(".")
        )
        or type(port) is not int
        or not 1 <= port <= 65535
        or config.tls_mode not in {"none", "starttls", "tls"}
    ):
        return _blocked("invalid_configuration")
    if (host, port) not in allowed_targets:
        return _blocked("smtp_target_blocked")
    if config.tls_mode == "none" and (host, port) != (local_mailpit_host, 1025):
        return _blocked("smtp_tls_required")
    if config.auth_mode not in {"none", "password"}:
        return _blocked("auth_mode_unsupported")
    if config.auth_mode == "password":
        if not credentials.password:
            return ProbeResult("credentials_required", "credentials_missing")
        if not _safe_text(credentials.password):
            return _blocked("invalid_credentials")
        # The plaintext exception is only an unauthenticated local test capture service.
        if config.tls_mode == "none":
            return _blocked("smtp_tls_required")
    client = None
    try:
        options = {"timeout": TIMEOUT_SECONDS, "local_hostname": "publishing-os.local"}
        if config.tls_mode == "tls":
            client = smtplib.SMTP_SSL(host, port, context=_tls_context(), **options)
        else:
            client = smtplib.SMTP(host, port, **options)
        if client.ehlo()[0] != 250:
            return _error("smtp_protocol_error")
        if config.tls_mode == "starttls":
            if client.starttls(context=_tls_context())[0] != 220:
                return _error("tls_failed")
            if client.ehlo()[0] != 250:
                return _error("smtp_protocol_error")
        if config.auth_mode == "password":
            client.login(config.username or config.address, credentials.password)
        return ProbeResult("verified")
    except smtplib.SMTPAuthenticationError:
        return _error("authentication_failed")
    except ssl.SSLError:
        return _error("tls_failed")
    except smtplib.SMTPNotSupportedError:
        return _error("smtp_protocol_error")
    except TimeoutError:
        return _error("timeout")
    except smtplib.SMTPException:
        return _error("smtp_protocol_error")
    except OSError:
        return _error("network_error")
    except Exception:
        return _error("probe_failed")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
