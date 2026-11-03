"""Read-only DOI protocol tests. No model, real manuscript or real mail involved."""

import asyncio
import json
import time

import httpx
import pytest

from packages import review_sources as sources

DOI = "10.1371/journal.pmed.0020124"


def record(**changes):
    return {
        "status": "ok",
        "message-type": "work",
        "message": {
            "DOI": DOI,
            "title": ["Why Most Published Research Findings Are False"],
            "author": [{"given": "John P. A.", "family": "Ioannidis"}],
            "published": {"date-parts": [[2005, 8, 30]]},
            "URL": "http://127.0.0.1/private-do-not-fetch",
            "abstract": "PRIVATE-UPSTREAM-BODY-MUST-NOT-BE-EXPOSED",
            **changes,
        },
    }


def respond(data=None, status=200, **kwargs):
    return httpx.Response(status, json=record() if data is None else data, **kwargs)


@pytest.mark.parametrize(
    "value",
    [
        DOI,
        DOI.upper(),
        f"  {DOI}  ",
        f"doi:{DOI}",
        f"DOI: {DOI}",
        f"https://doi.org/{DOI}",
        "https://doi.org/10.1371%2Fjournal.pmed.0020124",
        f"http://dx.doi.org/{DOI}",
    ],
)
def test_normalizes_only_supported_identifier_forms(value):
    assert sources.normalize_doi(value) == DOI


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        "",
        "ordinary text",
        "10.123/x",
        "10.1234567890/x",
        "10.1234/has space",
        "10.1234/汉字",
        "10.1234/../secret",
        "10.1234/x\nInjected",
        "10.1234/x\u202eInjected",
        "10.1234/x?query=private",
        "10.1234/x#private",
        "10.1234/<script>",
        "10.1234/x\\private",
        "10.1234/" + "x" * 250,
        f"https://doi.org:443/{DOI}",
        f"https://doi.org@evil.test/{DOI}",
        f"https://evil.test/https://doi.org/{DOI}",
        f"https://doi.org/{DOI}?private=data",
        f"https://doi.org/{DOI}#section",
        f"https://doi.org/{DOI}\nprivate",
        "https://doi.org/10.1234%2F..%2Fsecret",
        f"file:///doi.org/{DOI}",
    ],
)
def test_rejects_unsafe_unbounded_or_non_identifier_input_without_http(value):
    called = []
    transport = httpx.MockTransport(lambda request: called.append(request))
    assert sources.normalize_doi(value) is None
    assert sources.lookup_doi(value, transport=transport) == {"status": "unavailable", "doi": None}
    assert called == []


def test_exact_verified_projection_contains_only_bounded_metadata_and_fixed_links():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.scheme == "https" and request.url.host == "api.crossref.org"
        assert request.url.raw_path == b"/works/10.1371%2Fjournal.pmed.0020124"
        assert request.url.query == b"" and request.content == b""
        assert "authorization" not in request.headers and "cookie" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        return respond()

    result = sources.lookup_doi(DOI.upper(), transport=httpx.MockTransport(handler))
    assert result["status"] == "verified_metadata" and result["doi"] == DOI
    assert result["title"] == "Why Most Published Research Findings Are False"
    assert result["authors"] == ["John P. A. Ioannidis"] and result["year"] == 2005
    assert result["url"] == f"https://doi.org/{DOI}"
    assert result["source_url"] == "https://api.crossref.org/works/10.1371%2Fjournal.pmed.0020124"
    assert result["scope"] == "bibliographic_metadata_only"
    assert result["retrieved_at"].endswith("+00:00")
    assert "127.0.0.1" not in json.dumps(result) and "PRIVATE-UPSTREAM" not in json.dumps(result)
    assert len(calls) == 1


def test_external_text_is_plain_bounded_and_author_and_year_projection_is_safe():
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(
            lambda request: respond(
                record(
                    title=["<i>Title &amp; names</i>\u202e\n" + "x" * 1500],
                    author=[{"name": "<b>Group author</b>\x00"}] * 15,
                    published={"date-parts": [[True]]},
                    issued={"date-parts": [[2006]]},
                )
            )
        ),
    )
    assert result["status"] == "verified_metadata"
    assert result["title"].startswith("Title & names") and len(result["title"]) == 1200
    assert "<" not in result["title"] and "\u202e" not in result["title"]
    assert result["authors"] == ["Group author"] * 10 and result["year"] == 2006


@pytest.mark.parametrize("title", ["<![bad[abc]]>", "<![foo]>"])
def test_malformed_html_title_fails_closed_without_parser_error_or_upstream_text(title):
    assert sources._text(title, 1200) == ""
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(lambda request: respond(record(title=[title]))),
    )
    assert result == {"status": "unavailable", "doi": DOI}


@pytest.mark.parametrize("malformed", ["<![bad[abc]]>", "<![foo]>"])
def test_malformed_html_author_is_omitted_without_losing_other_valid_metadata(malformed):
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(
            lambda request: respond(
                record(
                    author=[
                        {"name": malformed},
                        {"given": malformed, "family": "Safe Surname"},
                        {"given": "Safe", "family": "Author"},
                    ]
                )
            )
        ),
    )
    assert result["status"] == "verified_metadata"
    assert result["authors"] == ["Safe Author"]
    assert malformed not in json.dumps(result)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 500, 503])
def test_http_errors_and_redirects_are_fixed_failures_and_never_followed(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"Location": "http://127.0.0.1/private"},
            content=b"PRIVATE-UPSTREAM-BODY",
        )

    assert sources.lookup_doi(DOI, transport=httpx.MockTransport(handler)) == {
        "status": "unavailable",
        "doi": DOI,
    }
    assert len(calls) == 1


def test_not_found_is_distinguished_without_exposing_its_body():
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(lambda request: httpx.Response(404, text="PRIVATE-BODY")),
    )
    assert result == {"status": "not_found", "doi": DOI}


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"status": "error", "message-type": "work", "message": record()["message"]},
        {"status": "ok", "message-type": "work-list", "message": record()["message"]},
        record(DOI="10.1371/another-paper"),
        record(DOI=None),
        record(title=[]),
        record(title="A plain string isn't the registered title array"),
        record(title=[None]),
        record(title=["\u202e\n"]),
    ],
)
def test_malformed_or_mismatched_record_never_becomes_verified_metadata(data):
    assert sources.lookup_doi(
        DOI, transport=httpx.MockTransport(lambda request: respond(data))
    ) == {
        "status": "unavailable",
        "doi": DOI,
    }


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/html"},
        {"Content-Type": "application/json", "Content-Encoding": "gzip"},
        {"Content-Type": "application/json", "Content-Length": str(sources.MAX_BYTES + 1)},
        {"Content-Type": "application/json", "Content-Length": "-1"},
        {"Content-Type": "application/json", "Content-Length": "not-a-number"},
        {"Content-Type": "application/json", "Content-Length": "1"},
    ],
)
def test_invalid_media_compression_and_length_are_rejected(headers):
    # Stream rather than json= prevents HTTPX from eagerly decoding a mocked body.
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers=headers, stream=Chunks([b"{}\n"]))
        ),
    )
    assert result == {"status": "unavailable", "doi": DOI}


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


def test_streamed_limit_without_content_length_closes_body():
    stream = Chunks([b"x" * (sources.MAX_BYTES // 2)] * 3)
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "application/json"}, stream=stream
            )
        ),
    )
    assert result == {"status": "unavailable", "doi": DOI} and stream.closed


@pytest.mark.parametrize(
    "body",
    [
        b"{broken-json",
        b"\xff",
        b'{"status":"ok","status":"ok"}',
        b'{"number":NaN}',
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_untrusted_json_errors_are_sanitized(body):
    result = sources.lookup_doi(
        DOI,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "application/json"}, stream=Chunks([body])
            )
        ),
    )
    assert result == {"status": "unavailable", "doi": DOI}


@pytest.mark.parametrize("timeout", [None, True, 0, -1, 10.1, float("nan"), float("inf"), "5"])
def test_invalid_timeout_does_not_attempt_network(timeout):
    calls = []
    result = sources.lookup_doi(
        DOI, timeout=timeout, transport=httpx.MockTransport(lambda request: calls.append(request))
    )
    assert result == {"status": "unavailable", "doi": DOI} and not calls


def test_total_deadline_limits_trickled_response_and_closes_stream():
    stream = Chunks([b"{"], delay=2.0)
    start = time.monotonic()
    result = sources.lookup_doi(
        DOI,
        timeout=0.05,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"Content-Type": "application/json"}, stream=stream
            )
        ),
    )
    assert result == {"status": "unavailable", "doi": DOI}
    assert time.monotonic() - start < 1.0 and stream.closed


def test_transport_exception_does_not_expose_upstream_private_diagnostics():
    def handler(request):
        raise httpx.ReadTimeout("PRIVATE-UPSTREAM-BODY", request=request)

    assert sources.lookup_doi(DOI, transport=httpx.MockTransport(handler)) == {
        "status": "unavailable",
        "doi": DOI,
    }


def test_env_proxies_and_tls_key_logging_are_not_honored(monkeypatch, tmp_path):
    log = tmp_path / "do-not-create.keylog"
    monkeypatch.setenv("SSLKEYLOGFILE", str(log))
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    seen = {}
    original_client = httpx.AsyncClient

    def client(**kwargs):
        seen.update(kwargs)
        return original_client(**kwargs)

    monkeypatch.setattr(sources.httpx, "AsyncClient", client)
    result = sources.lookup_doi(DOI, transport=httpx.MockTransport(lambda request: respond()))
    assert result["status"] == "verified_metadata"
    assert seen["trust_env"] is False and seen["follow_redirects"] is False
    assert seen["verify"].keylog_filename is None and not log.exists()


def test_sync_boundary_inside_event_loop_fails_closed_without_unawaited_coroutine():
    async def run():
        return sources.lookup_doi(DOI, transport=httpx.MockTransport(lambda request: respond()))

    assert asyncio.run(run()) == {"status": "unavailable", "doi": DOI}
