# Read-only mailbox connection probes

Retrieved primary documentation with Firecrawl on 2026-11-02. This implementation checks SMTP connectivity/authentication or cloud account identity. It does not fetch messages, create message envelopes, send messages, register OAuth applications, obtain consent grants, or refresh tokens. Credentials are supplied by the API from dedicated environment references; the adapter reads no environment variables or database records.

## Provider evidence and choices

| Provider | Retrieved official source | Implementation choice |
| --- | --- | --- |
| Gmail | [users.getProfile](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile) documents a GET with `me`, the `emailAddress` response field, and accepted OAuth scopes. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) documents metadata-only permission. | GET `https://gmail.googleapis.com/gmail/v1/users/me/profile` with an operator-supplied access token. Recommend `https://www.googleapis.com/auth/gmail.metadata` for this probe. This scope permits message metadata access beyond the profile, but this adapter invokes only the profile method. It has no send permission. The official scopes page places metadata in the restricted scope group; consent/verification requirements remain the operator's responsibility. |
| Outlook / Microsoft 365 | [Microsoft Graph Get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0) documents `/me`, delegated `User.Read` as least privilege, and `$select` for requested properties. `/me` requires a signed-in user, not application-only permission. | GET `https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName` with a delegated OAuth access token. Compare the requested address with the returned `mail` or `userPrincipalName`. No `Mail.Read` or `Mail.Send` permission is needed for this identity check. |
| Self-hosted SMTP | [Python smtplib](https://docs.python.org/3/library/smtplib.html) documents the explicit connection timeout, implicit TLS via `SMTP_SSL`, `starttls(context=...)`, a second EHLO after STARTTLS, and `login`. [Python SSL](https://docs.python.org/3/library/ssl.html) documents verified client TLS contexts and `create_default_context`'s `SSLKEYLOGFILE` behavior. | Exact operator host/port allowlist; verified implicit TLS or STARTTLS; EHLO, optional AUTH, and close only. TLS uses `SSLContext(PROTOCOL_TLS_CLIENT)` with default CA loading, preventing `SSLKEYLOGFILE` from enabling TLS key logs in either SMTP or HTTP. Username/password AUTH is supported. SMTP OAuth2 is deliberately rejected by this adapter; Gmail/Outlook use their profile APIs. Plaintext is allowed only for the configured local Mailpit host on port 1025, without AUTH. |

Provider identity addresses are compared case-insensitively. No alias lookup or mailbox authorization beyond provider identity is inferred. A successful SMTP check confirms its greeting and selected authentication mode; it does not prove that a sender address may send messages.

## Enforcement

- `ProbeConfig`, secret-redacted `MailCredentials`, `ProbeResult`, and `probe(...)` are exported from `packages.mail_adapters`.
- Cloud URLs are constants. HTTP redirects and environment proxies are disabled, TLS certificate verification is enabled, timeout is eight seconds per operation, and accepted profile content is bounded at 64 KiB.
- Missing credentials return `credentials_required` before any provider request. Invalid configuration and unsupported authentication modes are blocked. HTTP/SMTP/TLS/network errors become fixed codes, never raw provider exceptions or response bodies.
- SMTP rejects unsafe hostnames, invalid ports and control characters. The allowlist is exact and case-sensitive. An allowlisted remote host still cannot use plaintext. No `sendmail`, `send_message`, `MAIL`, `RCPT`, or `DATA` operation exists in the adapter.
- The caller owns journal/role/ownership checks, dedicated environment reference resolution, persisted statuses, and audit transactions. There is no send transport; `EMAIL_SEND_ENABLED=false` remains the product contract.

## Executed validation

`2026-11-02`: `.venv/bin/ruff check packages/mail_adapters tests/mail_adapters`, `.venv/bin/ruff format --check packages/mail_adapters tests/mail_adapters`, and `.venv/bin/pytest tests/mail_adapters -q` passed (56 tests).

Tests use `httpx.MockTransport` and a fake SMTP operation log. They verify fixed endpoints and methods, missing credentials without networking, identity mismatch, 401/403/429/500, malformed/oversized responses, redirects without follow-up, sanitized timeouts and failures, verified TLS, exact allowlisting, rejected injected configuration, and absence of envelope/sending operations. Secrets in fixtures are synthetic strings.

An actual local Mailpit check ran through the API container on the Compose network, executing the current adapter source via stdin and calling `probe(ProbeConfig("smtp", "editor@example.test", "mailpit", 1025, "none"), MailCredentials(), allowed_smtp_targets={("mailpit", 1025)})`. It returned `ProbeResult(status='verified', error_code=None)`, process exit 0. The path used EHLO and close only; it did not authenticate, read messages, or send a message. No real Gmail, Outlook, or external SMTP account was probed, and no real credentials were used.

The root agent owns the full `scripts/verify.sh` run and API/browser integration. These adapter results do not claim those broader checks passed.
