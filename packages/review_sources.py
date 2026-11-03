"""Bounded Crossref DOI metadata, never an arbitrary URL fetcher or a truth oracle.

The caller must allowlist DOI identifiers from the authorized current material.
This adapter deliberately accepts no free-text search, credentials or endpoint.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import ssl
import unicodedata
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlsplit

import httpx

MAX_BYTES = 262_144
MAX_TIMEOUT_SECONDS = 10.0
SCOPE = "bibliographic_metadata_only"
DOI_PATTERN = re.compile(r"10\.[0-9]{4,9}/[^\s?#<>\"\\]+", re.ASCII)


def normalize_doi(value: object) -> str | None:
    """Normalize one bounded ASCII identifier without following an input URL."""
    if not isinstance(value, str) or len(value) > 512:
        return None
    if any(unicodedata.category(char).startswith("C") for char in value):
        return None
    value = value.strip()
    if value.lower().startswith("doi:"):
        value = value[4:].strip()
    elif value.lower().startswith(("https://", "http://")):
        try:
            url = urlsplit(value)
            if (
                url.scheme.lower() not in {"http", "https"}
                or url.netloc.lower() not in {"doi.org", "dx.doi.org"}
                or url.query
                or url.fragment
            ):
                return None
            value = unquote(url.path[1:], errors="strict")
        except (UnicodeError, ValueError):
            return None
    if (
        not value.isascii()
        or len(value) > 256
        or not DOI_PATTERN.fullmatch(value)
        or any(unicodedata.category(char).startswith("C") for char in value)
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        return None
    return value.lower()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or len(value) > 10_000:
        return ""
    parser = _Text()
    try:
        parser.feed(value)
        parser.close()
    except (AssertionError, ValueError):
        # HTMLParser can assert on malformed marked sections from an upstream
        # record. Such text is absent evidence, never an uncaught API failure.
        return ""
    plain = "".join(parser.parts)
    plain = "".join(c for c in plain if not unicodedata.category(c).startswith("C"))
    return " ".join(plain.split())[:limit]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite_json_value")


def _tls_context():
    # Unlike create_default_context(), this never honors SSLKEYLOGFILE.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    return context


def _year(message):
    for key in ("published", "published-print", "published-online", "issued"):
        date = message.get(key)
        if not isinstance(date, dict):
            continue
        parts = date.get("date-parts")
        if (
            isinstance(parts, list)
            and parts
            and isinstance(parts[0], list)
            and parts[0]
            and type(parts[0][0]) is int
            and 1000 <= parts[0][0] <= 3000
        ):
            return parts[0][0]
    return None


def _projection(data, doi, source_url):
    if (
        not isinstance(data, dict)
        or data.get("status") != "ok"
        or data.get("message-type") != "work"
        or not isinstance(data.get("message"), dict)
    ):
        raise ValueError("invalid_record")
    message = data["message"]
    if normalize_doi(message.get("DOI")) != doi:
        raise ValueError("doi_mismatch")
    titles = message.get("title")
    if not isinstance(titles, list) or not titles:
        raise ValueError("missing_title")
    title = _text(titles[0], 1200)
    if not title:
        raise ValueError("missing_title")
    authors = []
    entries = message.get("author")
    for author in entries[:10] if isinstance(entries, list) else []:
        if not isinstance(author, dict):
            continue
        name = _text(author.get("name"), 200) or _text(
            " ".join(v for v in (author.get("given"), author.get("family")) if isinstance(v, str)),
            200,
        )
        if name:
            authors.append(name)
    return {
        "status": "verified_metadata",
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": _year(message),
        "url": "https://doi.org/" + quote(doi, safe="/"),
        "source_url": source_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "scope": SCOPE,
    }


async def _lookup(doi, timeout, transport):
    failure = {"status": "unavailable", "doi": doi}
    endpoint = "https://api.crossref.org/works/" + quote(doi, safe="")
    # A total deadline prevents a trickle response from extending a read timeout.
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout),
            verify=_tls_context(),
            trust_env=False,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "Pivot-DOI-Metadata/1.0",
            },
        ) as client:
            async with client.stream("GET", endpoint) as response:
                if response.status_code == 404:
                    return {"status": "not_found", "doi": doi}
                if response.status_code != 200:
                    return failure
                media = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                if media != "application/json" and not (
                    media.startswith("application/") and media.endswith("+json")
                ):
                    return failure
                if (
                    response.headers.get("content-encoding", "identity").lower().strip()
                    != "identity"
                ):
                    return failure
                length = response.headers.get("content-length")
                if length is not None and (not length.isascii() or not length.isdecimal()):
                    return failure
                if length is not None and int(length) > MAX_BYTES:
                    return failure
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > MAX_BYTES:
                        return failure
                    raw.extend(chunk)
                if length is not None and len(raw) != int(length):
                    return failure
                data = json.loads(
                    raw.decode("utf-8", errors="strict"),
                    object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
                return _projection(data, doi, endpoint)


def lookup_doi(doi, *, timeout=5.0, transport=None) -> dict:
    """Resolve an exact DOI in a synchronous worker; failures contain fixed data only.

    ``transport`` is an injectable HTTPX test seam, not a configurable URL. Never
    invoke this synchronous boundary from a running asyncio loop.
    """
    normalized = normalize_doi(doi)
    failure = {"status": "unavailable", "doi": normalized}
    if (
        normalized is None
        or type(timeout) not in {int, float}
        or not math.isfinite(timeout)
        or not 0 < timeout <= MAX_TIMEOUT_SECONDS
    ):
        return failure
    try:
        # Do not create an unawaited coroutine if used from an async handler.
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        return failure
    try:
        return asyncio.run(_lookup(normalized, timeout, transport))
    except (httpx.HTTPError, TimeoutError, OSError, ValueError, UnicodeError, RecursionError):
        return failure
