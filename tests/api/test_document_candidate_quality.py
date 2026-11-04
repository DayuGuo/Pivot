"""Regressions discovered with licensed public papers; no network or real papers required."""

import json

import httpx
import pytest

from apps.api.publishing.domain.document_candidates import labelled_abstract, local_candidate
from packages.model_gateway.editorial import EditorialDeepSeekProvider
from packages.model_gateway.gateway import GatewayError


def test_structured_multiline_abstract_is_not_truncated_at_background_methods_or_first_paragraph():
    body = (
        "Background: This wholly synthetic paper evaluates a manuscript ingestion tool.\n\n"
        "Methods: We tested eight fictional records across two input formats.\n\n"
        "Results: Every synthetic record was preserved without a factual medical claim.\n\n"
        "Conclusion: Independent human checking remains necessary."
    )
    text = "Synthetic title\nAbstract\n" + body + "\nKeywords: synthetic; ingestion\nMain body."
    abstract = labelled_abstract(text)
    assert abstract.value == body and abstract.quote == body
    assert local_candidate(text).abstract == abstract
    assert text.count(abstract.quote) == 1


def test_labelled_inline_abstract_preserves_the_whole_span_before_numbered_introduction():
    body = "A synthetic abstract long enough for independent review.\nIt has a second line and complete final sentence."
    abstract = labelled_abstract(
        "Abstract: " + body + "\n1. Introduction\nBody is not an abstract."
    )
    assert abstract.value == body


@pytest.mark.parametrize(
    "text",
    [
        "A title\nThis introductory paragraph is not a labelled abstract and must not be relabelled.",
        "Abstract\nAn apparently labelled abstract with no reliable ending boundary must stay unknown.",
        "Abstract\nToo short.\nKeywords: short",
    ],
)
def test_unbounded_unlabelled_or_too_short_abstract_is_unknown_not_a_prefix(text):
    assert labelled_abstract(text) is None
    assert local_candidate(text).abstract is None


def test_document_output_budget_is_bounded_and_does_not_change_default_chat_requests(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "synthetic-unit-budget" * 2)
    seen = []

    def handle(request):
        seen.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "synthetic"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    provider = EditorialDeepSeekProvider(live_enabled=True, transport=httpx.MockTransport(handle))
    provider.completion([{"role": "user", "content": "synthetic"}], [])
    provider.set_output_budget(6144)
    provider.completion([{"role": "user", "content": "synthetic"}], [])
    assert seen == [2048, 6144]
    for invalid in [0, 255, 6145, -1, True, 6144.0, "6144", None]:
        with pytest.raises(GatewayError):
            provider.set_output_budget(invalid)
    other = EditorialDeepSeekProvider(live_enabled=True, transport=httpx.MockTransport(handle))
    other.completion([{"role": "user", "content": "synthetic"}], [])
    assert seen[-1] == 2048


def evidence_case(text):
    return {
        "text": text,
        "segments": [{"kind": "pdf_page", "number": 1, "start": 0, "end": len(text), "text": text}],
    }


def test_metadata_whitespace_alignment_stores_the_exact_raw_unicode_quote_and_offsets():
    from apps.api.publishing.domain.document_candidates import (
        MetadataCandidate,
        Quoted,
        merge_candidate,
    )

    text = "🙂 Prefix.\nUniversity of\nOslo,\u00a0Norway\nA different paragraph."
    candidate = MetadataCandidate(
        title=Quoted(value="University of Oslo, Norway", quote="University of Oslo, Norway")
    )
    data, sources = merge_candidate(
        candidate,
        evidence_case(text),
        {"source_kind": "synthetic", "source_note": "Synthetic unit source only."},
    )
    assert data["title"] == "University of\nOslo,\u00a0Norway"
    assert sources[0]["quote"] == "University of\nOslo,\u00a0Norway"
    assert text[sources[0]["start"] : sources[0]["end"]] == sources[0]["quote"]
    assert sources[0]["start"] == text.index("University")


@pytest.mark.parametrize(
    "value",
    [
        "University of Oslo Norway",
        "university of Oslo, Norway",
        "University of Oslo, Sweden",
        "University of Oslo, Norway 42",
    ],
)
def test_whitespace_alignment_does_not_accept_changed_punctuation_case_place_or_number(value):
    from apps.api.publishing.domain.document_candidates import (
        CandidateEvidenceError,
        MetadataCandidate,
        Quoted,
        merge_candidate,
    )

    text = "University of\nOslo,\u00a0Norway"
    with pytest.raises(CandidateEvidenceError):
        merge_candidate(
            MetadataCandidate(title=Quoted(value=value, quote="University of Oslo, Norway")),
            evidence_case(text),
            {"source_kind": "synthetic", "source_note": "Synthetic unit source only."},
        )


def test_invalid_metadata_protocol_can_be_corrected_once_without_confirming_or_hiding_usage(
    monkeypatch,
):
    import time

    from apps.api.publishing.domain import document_candidates

    class Supplier:
        name = "deepseek"
        last_telemetry = None
        last_attempt_telemetry = []

        def __init__(self):
            self.calls = 0

        def set_output_budget(self, tokens):
            assert tokens == 6144

        def completion(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                raise GatewayError("invalid_editorial_model_response")
            assert "propose_metadata" in messages[-1]["content"]
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "propose_metadata",
                                        "arguments": json.dumps(
                                            {
                                                "title": {
                                                    "value": "A synthetic title",
                                                    "quote": "A synthetic title",
                                                }
                                            }
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

    supplier = Supplier()
    monkeypatch.setattr(document_candidates, "get_editorial_provider", lambda: supplier)
    diagnostics = []
    data, _, provider, _, _ = document_candidates.identify(
        evidence_case("A synthetic title"),
        {"source_kind": "synthetic", "source_note": "Synthetic unit source only."},
        lambda: None,
        time.monotonic() + 60,
        diagnostics=diagnostics,
    )
    assert data["title"] == "A synthetic title" and provider == "deepseek"
    assert supplier.calls == 2
    assert diagnostics == [
        {"attempt": 1, "reason": "metadata_protocol_invalid", "field": "candidate"}
    ]


def test_glyph_spacing_recovery_keeps_original_name_and_country_spelling_instead_of_model_rewrite():
    from apps.api.publishing.domain.document_candidates import (
        MetadataCandidate,
        Quoted,
        merge_candidate,
    )

    raw = "John P.A. Ioannidis\nUnited Sta tes of America"
    candidate = MetadataCandidate(title=Quoted(value="John P. A. Ioannidis", quote=raw))
    data, sources = merge_candidate(
        candidate,
        evidence_case(raw),
        {"source_kind": "synthetic", "source_note": "Synthetic unit source only."},
    )
    assert data["title"] == sources[0]["value"] == "John P.A. Ioannidis"
    assert sources[0]["quote"] == raw


def test_numbered_byline_prevents_a_real_institution_being_grafted_to_the_wrong_author():
    from apps.api.publishing.domain.document_candidates import (
        AuthorCandidate,
        CandidateEvidenceError,
        MetadataCandidate,
        Quoted,
        merge_candidate,
    )

    text = "Alpha Author1, Beta Author2\n1 Department Alpha, University A, 9th Floor, 15 Road\n2Department Beta, University B\nAbstract\nA synthetic source only."

    def person(name, affiliation):
        return AuthorCandidate(
            name=Quoted(value=name, quote=name),
            affiliations=[Quoted(value=affiliation, quote=affiliation)],
        )

    base = {"source_kind": "synthetic", "source_note": "Synthetic source only."}
    bad = MetadataCandidate(
        authors=[
            person("Alpha Author", "Department Alpha, University A, 9th Floor, 15 Road"),
            person("Beta Author", "Department Alpha, University A"),
        ]
    )
    with pytest.raises(CandidateEvidenceError) as error:
        merge_candidate(bad, evidence_case(text), base)
    assert error.value.reason == "affiliation_assignment_invalid"
    assert error.value.field == "authors.1.affiliations.0"
    good = MetadataCandidate(
        authors=[
            person("Alpha Author", "Department Alpha, University A, 9th Floor, 15 Road"),
            person("Beta Author", "Department Beta, University B"),
        ]
    )
    data, sources = merge_candidate(good, evidence_case(text), base)
    assert data["authors"][1]["affiliations"] == ["Department Beta, University B"]
    assert all(text[s["start"] : s["end"]] == s["quote"] for s in sources)


def test_named_contact_email_completion_does_not_borrow_the_following_authors_address():
    from apps.api.publishing.domain.document_candidates import (
        AuthorCandidate,
        MetadataCandidate,
        Quoted,
        supplement_contact_emails,
    )

    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(name=Quoted(value=n, quote=n)) for n in ["Alpha Author", "Beta Author"]
        ]
    )
    text = (
        "Alpha Author: University Alpha\n\nBeta Author: University Beta\nemail: beta@synthetic.test"
    )
    result = supplement_contact_emails(candidate, text)
    assert result.authors[0].email is None
    assert result.authors[1].email.value == "beta@synthetic.test"
    assert result.authors[1].email.quote in text
    full = (
        "Alpha Author: University Alpha\nemail: alpha@synthetic.test\n\n"
        + text[text.index("Beta Author:") :]
    )
    result = supplement_contact_emails(candidate, full)
    assert [author.email.value for author in result.authors] == [
        "alpha@synthetic.test",
        "beta@synthetic.test",
    ]
    assert all(author.email.quote in full for author in result.authors)


def test_contact_completion_stops_at_an_author_missing_from_the_model_roster():
    from apps.api.publishing.domain.document_candidates import (
        AuthorCandidate,
        MetadataCandidate,
        Quoted,
        supplement_contact_emails,
    )

    candidate = MetadataCandidate(
        authors=[AuthorCandidate(name=Quoted(value="Alpha Author", quote="Alpha Author"))]
    )
    text = (
        "Alpha Author: University Alpha\nBeta Author: University Beta\nemail: beta@synthetic.test"
    )
    assert supplement_contact_emails(candidate, text).authors[0].email is None


def test_grounded_quote_alignment_returns_original_nbsp_and_newlines_only_from_issued_source():
    from apps.api.publishing.domain.dossier_evidence import EvidenceIndex

    text = "🙂 Original text. Division of Medicine, Gower Street,\u00a0London.\nNext paragraph."
    index = EvidenceIndex({}, text, "synthetic")
    source = next(iter(index.sources.values()))
    kwargs = {
        "version_id": "v",
        "version_no": 1,
        "content_digest": "a" * 64,
        "file_sha256": "b" * 64,
    }
    with pytest.raises(GatewayError):
        index.citation(source.source_id, "Division of Medicine, Gower Street, London.", **kwargs)
    index.issue([source])
    citation = index.citation(
        source.source_id, "Division of Medicine, Gower Street, London.", **kwargs
    )
    assert citation["quote"] == "Division of Medicine, Gower Street,\u00a0London."
    assert text[citation["start"] : citation["end"]] == citation["quote"]
    for forged in [
        "Division of Surgery, Gower Street, London.",
        "Division of Medicine, Gower Street, London, 42.",
    ]:
        with pytest.raises(GatewayError):
            index.citation(source.source_id, forged, **kwargs)


def test_author_name_guard_rejects_an_invented_given_name_but_allows_exact_and_short_names():
    from apps.api.publishing.domain.dossier_evidence import check_claim_terms

    data = {"authors": [{"name": "John P. A. Ioannidis"}]}
    citations = [{"quote": "John P. A. Ioannidis is the author."}]
    for claim in ["作者 John P. A. Ioannidis。", "作者 John Ioannidis。", "作者 Ioannidis。"]:
        check_claim_terms(claim, citations, data)
    with pytest.raises(GatewayError) as error:
        check_claim_terms("作者 Johnson P. A. Ioannidis。", citations, data)
    assert error.value.args == ("dossier_author_name_invalid",)


def test_smaller_studies_are_not_rewritten_as_fewer_studies_without_count_evidence():
    from apps.api.publishing.domain.dossier_evidence import check_claim_terms

    citations = [{"quote": "the studies conducted in a field are smaller"}]
    check_claim_terms("研究规模较小。", citations, {})
    with pytest.raises(GatewayError) as error:
        check_claim_terms("领域内研究越少（样本越小）。", citations, {})
    assert error.value.args == ("dossier_comparison_invalid",)
    check_claim_terms("领域内研究数量较少。", [{"quote": "a smaller number of studies"}], {})
