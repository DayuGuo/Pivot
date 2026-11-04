"""Whitespace-only alignment back to unchanged Unicode source spans; no fuzzy matching."""

import re
from array import array


def whitespace_evidence(text):
    """Canonicalize whitespace only and retain a map to every original code point."""
    pieces, starts, ends = [], array("I"), array("I")
    for match in re.finditer(r"\s+|\S+", text):
        token = match[0]
        if token.isspace():
            pieces.append(" ")
            starts.append(match.start())
            ends.append(match.end())
        else:
            pieces.append(token)
            starts.extend(range(match.start(), match.end()))
            ends.extend(range(match.start() + 1, match.end() + 1))
    return "".join(pieces), starts, ends


def raw_whitespace_span(text, quote):
    if not quote.strip():
        return None
    if quote in text:
        start = text.index(quote)
        return start, start + len(quote)
    normalized, starts, ends = whitespace_evidence(text)
    needle = " ".join(quote.split())
    start = normalized.find(needle)
    if start < 0:
        return None
    return starts[start], ends[start + len(needle) - 1]
