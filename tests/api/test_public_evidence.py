"""Always run licensed bundled PDF/Word cases offline; real semantic scoring is separate."""

from copy import deepcopy

import pytest

from apps.api.publishing.domain.document_candidates import (
    AuthorCandidate,
    MetadataCandidate,
    Quoted,
    merge_candidate,
)
from evals.public_documents.corpus import corpus, support_cases
from packages.model_gateway.gateway import GatewayError
from packages.text_evidence import raw_whitespace_span


@pytest.mark.parametrize("case", list(support_cases()), ids=lambda v: v["id"])
def test_public_contrastive_gold_has_real_exact_sources_and_counterfactual_pairs(case):
    assert case["quote_exact"]
    assert len(case["original_sha256"]) == 64
    assert case["expected"] in {"supported", "withheld"}
    citation = case["result"]["claims"][0]["citations"][0]
    assert citation["quote"] in citation["source_text"]
    assert len(citation["quote"]) >= 8


def raw_field(text, value):
    span = raw_whitespace_span(text, value)
    if span is None:
        # Existing extraction policy permits identical non-whitespace code points
        # in metadata glyph spacing, never changed spelling/punctuation.
        positions = [i for i, c in enumerate(text) if not c.isspace()]
        full = "".join(text[i] for i in positions)
        compact = "".join(value.split())
        start = full.find(compact)
        assert start >= 0, value
        span = positions[start], positions[start + len(compact) - 1] + 1
    raw = text[span[0] : span[1]]
    return Quoted(value=raw, quote=raw)


@pytest.mark.parametrize("sample", list(corpus()), ids=lambda v: v[1]["case"])
def test_public_author_institutions_stay_attached_to_their_original_names(sample):
    paper, _, extraction = sample
    text = extraction["text"]
    authors = [
        AuthorCandidate(
            name=raw_field(text, a["name"]),
            affiliations=[raw_field(text, v) for v in a["affiliations"]],
            email=raw_field(text, a["email"]) if a["email"] else None,
        )
        for a in paper["review_data"]["authors"]
    ]
    base = {"source_kind": "public_authorized", "source_note": "Licensed corpus author regression."}
    data, sources = merge_candidate(MetadataCandidate(authors=authors), extraction, base)
    assert len(data["authors"]) == len(authors)
    for actual, expected in zip(data["authors"], paper["review_data"]["authors"], strict=True):
        assert "".join(actual["name"].split()) == "".join(expected["name"].split())
        assert {"".join(v.split()) for v in actual["affiliations"]} == {
            "".join(v.split()) for v in expected["affiliations"]
        }
        assert actual["email"] == expected["email"]
    for source in sources:
        assert text[source["start"] : source["end"]] == source["quote"]
        for evidence in source.get("association", {}).get("evidence", []):
            assert text[evidence["start"] : evidence["end"]] == evidence["quote"]
    if len(authors) > 1:
        bad = deepcopy(authors)
        bad[0] = bad[0].model_copy(update={"affiliations": bad[-1].affiliations})
        try:
            changed, _ = merge_candidate(MetadataCandidate(authors=bad), extraction, base)
        except GatewayError:
            return
        # Shared institutions can be legitimate, but a distinct foreign one cannot leak.
        permitted = {"".join(v.split()) for v in paper["review_data"]["authors"][0]["affiliations"]}
        assert all("".join(v.split()) in permitted for v in changed["authors"][0]["affiliations"])
