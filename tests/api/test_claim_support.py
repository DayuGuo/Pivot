"""Exact quotation alone must not endorse the opposite or an unsupported claim."""

from copy import deepcopy

import pytest

from apps.api.publishing.domain import dossier_chat
from tests.api.test_dossier_chat import (
    BODY,
    body,
    completion,
    path,
    source,
    unchanged_business,
)
from tests.api.test_dossiers import create, metadata, save, upload


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))


@pytest.fixture
def ready(client, login):
    login()
    return save(client, create(client), data=metadata(), file=upload(raw=BODY.encode()))


def install(monkeypatch, verdict, *, invalid=False):
    class Supplier:
        name = "deepseek"
        model = "deepseek-flash"
        last_telemetry = None
        last_attempt_telemetry = []

        def __init__(self):
            self.primary_calls = 0
            self.support_calls = []

        def completion(self, messages, tools):
            if tools[0]["function"]["name"] == "assess_claims":
                self.support_calls.append(deepcopy(messages))
                if invalid:
                    return completion("assess_claims", {"checks": []})
                return completion(
                    "assess_claims",
                    {
                        "checks": [
                            {
                                "index": 0,
                                "status": verdict,
                                "reason": "direct_support"
                                if verdict == "supported"
                                else "contradiction",
                            }
                        ]
                    },
                )
            self.primary_calls += 1
            if self.primary_calls == 1:
                return completion("read_dossier", {})
            item = source(messages, contains="合成记录不能支持真实临床疗效推断")
            return completion(
                "respond",
                {
                    "claims": [
                        {
                            "text": "本研究证明对真实患者具有临床疗效。",
                            "citations": [
                                {
                                    "source_id": item["source_id"],
                                    "quote": "合成记录不能支持真实临床疗效推断",
                                }
                            ],
                        }
                    ],
                    "questions": [],
                    "external_dois": [],
                },
            )

    supplier = Supplier()
    monkeypatch.setattr(dossier_chat, "get_editorial_provider", lambda: supplier)
    return supplier


@pytest.mark.parametrize("verdict", ["insufficient", "contradicted"])
def test_exact_quote_cannot_be_presented_as_support_for_its_opposite(
    client, db, ready, monkeypatch, verdict
):
    supplier = install(monkeypatch, verdict)
    before = unchanged_business(db)
    response = client.post(path(ready), json=body(ready))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["claims"] == []
    assert result["withheld_claims"][0]["support"]["status"] == verdict
    assert len(supplier.support_calls) == 1
    assert unchanged_business(db) == before
    assert "本研究证明对真实患者具有临床疗效。" not in result["answer"]


def test_incomplete_semantic_verdict_does_not_commit_an_unchecked_answer(
    client, ready, monkeypatch
):
    install(monkeypatch, "supported", invalid=True)
    response = client.post(path(ready), json=body(ready))
    assert response.status_code == 503
    detail = client.get(f"/api/dossiers/{ready['id']}").json()
    assert detail["messages"] == []


def test_support_protocol_correction_does_not_rerun_primary_tools(client, ready, monkeypatch):
    supplier = install(monkeypatch, "insufficient")
    original = supplier.completion
    count = 0

    def completion_with_one_error(messages, tools):
        nonlocal count
        if tools[0]["function"]["name"] == "assess_claims":
            count += 1
            if count == 1:
                return completion("assess_claims", {"checks": []})
        return original(messages, tools)

    supplier.completion = completion_with_one_error
    response = client.post(path(ready), json=body(ready))
    assert response.status_code == 200
    assert response.json()["support_review"]["protocol_corrections"] == 1
    assert supplier.primary_calls == 2
    assert response.json()["claims"] == []


@pytest.mark.parametrize(
    "checks",
    [
        [{"index": 1, "status": "supported", "reason": "direct_support"}],
        [{"index": 0, "status": "supported", "reason": "direct_support"}] * 2,
        [{"index": False, "status": "supported", "reason": "direct_support"}],
        [{"index": 0, "status": "supported", "reason": "contradiction"}],
    ],
)
def test_unknown_duplicate_or_incoherent_verdicts_never_endorse_a_claim(
    client, ready, monkeypatch, checks
):
    supplier = install(monkeypatch, "supported")
    original = supplier.completion

    def malformed(messages, tools):
        if tools[0]["function"]["name"] == "assess_claims":
            return completion("assess_claims", {"checks": checks})
        return original(messages, tools)

    supplier.completion = malformed
    response = client.post(path(ready), json=body(ready))
    assert response.status_code == 503
    assert client.get(f"/api/dossiers/{ready['id']}").json()["messages"] == []


@pytest.mark.parametrize(
    "kind,document,scope",
    [
        ("text", None, "original_text"),
        ("metadata", None, "recorded_metadata"),
        ("metadata", {"source_quote": "Synthetic original byline"}, "original_metadata"),
    ],
)
def test_source_scope_and_original_attribution_are_explicit_in_support_context(
    kind, document, scope
):
    import json

    from apps.api.publishing.domain.claim_support import assess_support

    class Supplier:
        name = "deepseek"
        last_telemetry = None

        def completion(self, messages, tools):
            assert len(tools) == 1 and tools[0]["function"]["name"] == "assess_claims"
            context = json.loads(messages[1]["content"])["sources"]["S1"]
            assert context["evidence_scope"] == scope
            assert context["original_context"] == (document or {}).get("source_quote")
            assert "不能支持声称原件" in messages[0]["content"]
            return completion(
                "assess_claims",
                {"checks": [{"index": 0, "status": "supported", "reason": "direct_support"}]},
            )

    citation = {
        "source_id": "S1",
        "kind": kind,
        "field_path": "authors.0.name" if kind == "metadata" else None,
        "source_text": "Synthetic Author",
        "quote": "Synthetic Author",
    }
    if document:
        citation["document"] = document
    result = assess_support(
        {"claims": [{"text": "本版资料记载Synthetic Author。", "citations": [citation]}]},
        Supplier(),
        lambda: None,
        [],
    )
    assert result["claims"][0]["support"]["evidence_scope"] == scope
