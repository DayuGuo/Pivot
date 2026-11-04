"""Association evidence is stronger than finding a value somewhere in a paper."""

import pytest

from apps.api.publishing.domain.document_candidates import (
    AuthorCandidate,
    MetadataCandidate,
    Quoted,
    merge_candidate,
)
from tests.api.test_document_candidate_quality import evidence_case

BASE = {"source_kind": "synthetic", "source_note": "Synthetic author association regression."}


@pytest.mark.parametrize(
    "field,value", [("email", "beta@synthetic.test"), ("orcid", "0000-0002-1825-0097")]
)
def test_foreign_authors_real_value_is_not_attached_to_another_name(field, value):
    text = "Alpha Author; Beta Author\nBeta Author: email: beta@synthetic.test ORCID: 0000-0002-1825-0097\n"
    person = AuthorCandidate(
        name=Quoted(value="Alpha Author", quote="Alpha Author"),
        **{field: Quoted(value=value, quote=text)},
    )
    data, sources = merge_candidate(
        MetadataCandidate(
            authors=[person, AuthorCandidate(name=Quoted(value="Beta Author", quote="Beta Author"))]
        ),
        evidence_case(text),
        BASE,
    )
    assert not data["authors"][0][field]
    assert not any(s["field_path"] == f"authors.0.{field}" for s in sources)


def test_unmarked_two_author_institution_is_not_assumed_shared():
    text = "Alpha Author; Beta Author\nDepartment Alpha, University Alpha\nDepartment Beta, University Beta\n"
    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(
                name=Quoted(value=n, quote=n),
                affiliations=[
                    Quoted(
                        value="Department Alpha, University Alpha",
                        quote="Department Alpha, University Alpha",
                    )
                ],
            )
            for n in ("Alpha Author", "Beta Author")
        ]
    )
    data, sources = merge_candidate(candidate, evidence_case(text), BASE)
    assert all(not a["affiliations"] for a in data["authors"])
    assert not any("affiliations" in s["field_path"] for s in sources)


def test_broad_correspondence_quote_does_not_make_all_byline_authors_corresponding():
    text = "Alpha Author; Beta Author\nCorresponding author: Beta Author\n"
    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(name=Quoted(value=n, quote=n), corresponding_quote=text)
            for n in ("Alpha Author", "Beta Author")
        ]
    )
    data, _ = merge_candidate(candidate, evidence_case(text), BASE)
    assert [a["corresponding"] for a in data["authors"]] == [False, True]


def test_duplicate_names_do_not_resolve_an_orcid_by_first_occurrence():
    text = "Alex Lee1; Alex Lee2\nORCID: 0000-0002-1825-0097\n"
    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(
                name=Quoted(value="Alex Lee", quote="Alex Lee"),
                orcid=Quoted(value="0000-0002-1825-0097", quote=text),
            )
            for _ in range(2)
        ]
    )
    data, _ = merge_candidate(candidate, evidence_case(text), BASE)
    assert all(a["orcid"] is None for a in data["authors"])


def test_email_footnote_links_one_marker_without_asserting_corresponding_role():
    text = "Alpha Author1*; Beta Author2\n1 Department Alpha\n2 Department Beta\n* E-mail: alpha@synthetic.test\n"
    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(
                name=Quoted(value="Alpha Author", quote="Alpha Author"),
                email=Quoted(value="alpha@synthetic.test", quote="* E-mail: alpha@synthetic.test"),
            ),
            AuthorCandidate(
                name=Quoted(value="Beta Author", quote="Beta Author"),
                email=Quoted(value="alpha@synthetic.test", quote="* E-mail: alpha@synthetic.test"),
            ),
        ]
    )
    issues = []
    data, sources = merge_candidate(candidate, evidence_case(text), BASE, uncertainties=issues)
    assert data["authors"][0]["email"] == "alpha@synthetic.test"
    assert data["authors"][1]["email"] == ""
    assert not any(a["corresponding"] for a in data["authors"])
    accepted = next(s for s in sources if s["field_path"] == "authors.0.email")
    assert accepted["association"]["method"] == "email_footnote"
    assert accepted["association"]["identity_authenticated"] is False
    assert any(
        issue["field_path"] == "authors.1.email" and issue["reason"] == "author_link_unresolved"
        for issue in issues
    )


def test_duplicate_orcid_can_be_saved_as_draft_but_cannot_be_human_confirmed(
    client, login, tmp_path, monkeypatch
):
    from uuid import uuid4

    from tests.api.test_dossiers import create, metadata, save, upload

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login("editor")
    data = metadata()
    data["authors"][1]["orcid"] = data["authors"][0]["orcid"]
    item = save(client, create(client), data=data, file=upload())
    assert any(v["reason"] == "duplicate_orcid" for v in item["author_issues"])
    assert item["verified"] is False
    response = client.post(
        f"/api/dossiers/{item['id']}/confirm",
        json={
            "request_id": str(uuid4()),
            "expected_revision": item["revision"],
            "version_id": item["version_id"],
            "digest": item["content_digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert any("orcid" in v["field"] for v in response.json()["detail"]["missing"])
    assert client.get(f"/api/dossiers/{item['id']}").json()["verified"] is False


def test_only_named_marker_owner_gets_a_missing_footnote_email():
    from apps.api.publishing.domain.document_candidates import supplement_contact_emails

    text = "Alpha Author1*; Beta Author2\n1 Department Alpha\n2 Department Beta\n* E-mail: alpha@synthetic.test\n"
    candidate = MetadataCandidate(
        authors=[
            AuthorCandidate(name=Quoted(value=n, quote=n)) for n in ("Alpha Author", "Beta Author")
        ]
    )
    result = supplement_contact_emails(candidate, text)
    assert result.authors[0].email.value == "alpha@synthetic.test"
    assert result.authors[1].email is None
    assert result.authors[0].corresponding_quote is None
