import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain import revision_compare
from apps.api.publishing.domain.models import ActionProposal, HumanConfirmation, PublishingChatTurn
from packages.model_gateway.gateway import GatewayError
from tests.api.test_publishing_chat import post
from tests.api.test_publishing_decisions import closed_round, decide, recommend, submit_revision


def synthetic_source():
    texts = {
        "base": "样本量为40，分组方法未说明。\n未提供数据链接。",
        "revised": "样本量更正为80，按预先规定规则分成两组。\n未提供数据链接。",
        "response": "已更正样本量和分组说明。\n数据链接将在后续提供，本次未补充。",
    }
    return {
        "manuscript_id": str(uuid4()),
        "request_id": str(uuid4()),
        "revision": 4,
        "base_version_id": "old",
        "revised_version_id": "new",
        "rereview_required": True,
        "source_fingerprint": "a" * 64,
        "files": {
            k: {
                "kind": k,
                "file_id": str(uuid4()),
                "version_id": "old" if k == "base" else "new",
                "version_no": 1 if k == "base" else 2,
                "sha256": "b" * 64,
                "text": t,
            }
            for k, t in texts.items()
        },
        "points": [
            {
                "id": "P01",
                "text": "请更正样本量并说明分组。",
                "label": "已分享意见1",
                "start": 0,
                "end": 13,
                "complete": True,
            },
            {
                "id": "P02",
                "text": "请提供公开数据链接。",
                "label": "已分享意见1",
                "start": 0,
                "end": 11,
                "complete": True,
            },
        ],
        "point_count": 2,
        "all_points_included": True,
    }


class Supplier:
    name = "deepseek"
    last_telemetry = None

    def __init__(self, rows, checks=None):
        self.rows = rows
        self.checks = checks
        self.calls = 0

    def completion(self, messages, tools):
        name = tools[0]["function"]["name"]
        self.calls += 1
        args = (
            {"findings": self.rows}
            if name == "compare_revision_items"
            else {
                "checks": self.checks
                or [{"point_id": r["point_id"], "supported": True} for r in self.rows]
            }
        )
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args, ensure_ascii=False),
                                }
                            }
                        ]
                    }
                }
            ]
        }


def findings():
    return [
        {
            "point_id": "P01",
            "status": "resolved",
            "reason": "回复与修订稿均载明新样本量和分组。",
            "response_quote": "已更正样本量和分组说明。",
            "revised_quote": "样本量更正为80，按预先规定规则分成两组。",
            "base_quote": "样本量为40，分组方法未说明。",
        },
        {
            "point_id": "P02",
            "status": "partial",
            "reason": "作者回应但未提供链接。",
            "response_quote": "数据链接将在后续提供，本次未补充。",
            "revised_quote": "未提供数据链接。",
            "base_quote": "未提供数据链接。",
        },
    ]


def test_real_protocol_checks_changes_and_each_exact_source_span():
    s = synthetic_source()
    provider = Supplier(findings())
    r = revision_compare.compare(s, provider, lambda: None, [])
    assert (
        provider.calls == 2
        and r["rows"][0]["status"] == "resolved"
        and r["rows"][1]["status"] == "partial"
    )
    for row in r["rows"]:
        for cite in row["citations"]:
            assert s["files"][cite["kind"]]["text"][cite["start"] : cite["end"]] == cite["quote"]
    assert r["rereview_required"] and "仍须" in revision_compare.reply(r)


def test_unchanged_quote_cannot_be_called_successful_revision():
    rows = findings()
    rows[1]["status"] = "resolved"
    r = revision_compare.compare(synthetic_source(), Supplier(rows), lambda: None, [])
    assert r["rows"][1]["status"] == "uncertain"


def test_adjacent_read_windows_allow_exact_cross_boundary_quote_but_not_unread_gap():
    source = synthetic_source()
    marker = "UNIQUE-CROSS-BOUNDARY-MARKER"
    source["files"]["revised"]["text"] = "a" * 990 + marker + "b" * 15000
    windows, coverage = revision_compare.material_windows(source)
    assert not coverage["revised"]["complete"]
    assert len(windows["revised"]) == 1 and windows["revised"][0]["end"] == 12000
    cite = revision_compare.citation(source, windows, "revised", marker)
    assert cite["start"] == 990 and cite["quote"] == marker
    # A real, unique substring spanning an unselected gap is still rejected.
    text = "left SELECTED-A gap SELECTED-B right"
    source["files"]["revised"]["text"] = text
    disjoint = {"revised": [{"start": 0, "end": 15}, {"start": 20, "end": len(text)}]}
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare.citation(source, disjoint, "revised", "SELECTED-A gap SELECTED-B")


def test_long_exact_quotes_are_bounded_without_losing_sentence_context():
    row = findings()[0]
    row["revised_quote"] = "x" * 400
    assert len(revision_compare.Finding.model_validate(row).revised_quote) == 400
    row["revised_quote"] = "x" * 513
    with pytest.raises(ValueError):
        revision_compare.Finding.model_validate(row)


def test_catalog_ids_bind_exact_source_without_model_transcribing_pdf_line_breaks():
    source = synthetic_source()
    source["files"]["revised"]["text"] = "已更正样本量为80，\n按预先规定规则分成两组。"

    class Referenced(Supplier):
        def completion(self, messages, tools):
            if self.calls == 0:
                payload = json.loads(messages[1]["content"])
                catalog = payload["evidence_catalog"]
                schema = tools[0]["function"]["parameters"]["properties"]["findings"]["items"][
                    "properties"
                ]
                assert "revised_quote" not in schema
                assert catalog["revised"][0]["id"] in schema["revised_evidence_id"]["enum"]
                self.rows = [
                    {
                        "point_id": p["id"],
                        "status": "uncertain",
                        "reason": "选择实际原文片段，不能据此直接认定全部修改完成。",
                        **{
                            kind + "_evidence_id": catalog[kind][0]["id"]
                            for kind in ["base", "revised", "response"]
                        },
                    }
                    for p in source["points"]
                ]
            return super().completion(messages, tools)

    provider = Referenced([])
    result = revision_compare.compare(source, provider, lambda: None, [])
    assert provider.calls == 2
    assert any(
        "\n" in c["quote"] for r in result["rows"] for c in r["citations"] if c["kind"] == "revised"
    )
    for row in result["rows"]:
        for cite in row["citations"]:
            assert (
                source["files"][cite["kind"]]["text"][cite["start"] : cite["end"]] == cite["quote"]
            )


def test_catalog_does_not_drop_read_text_or_allow_cross_kind_or_repeated_reference():
    source = synthetic_source()
    source["files"]["base"]["text"] = ("read original text " * 400) + " unique-tail"
    windows, _ = revision_compare.material_windows(source)
    catalog = revision_compare.evidence_catalog(source, windows)
    all_ids = [c["id"] for entries in catalog.values() for c in entries]
    assert len(all_ids) == len(set(all_ids))
    for kind, entries in catalog.items():
        assert "".join("".join(c["text"].split()) for c in entries) == "".join(
            "".join(w["text"].split()) for w in windows[kind]
        )
        for c in entries:
            assert source["files"][kind]["text"][c["start"] : c["end"]] == c["text"]
            assert len(c["text"]) <= 480
    wrong = revision_compare.Finding.model_validate(
        {
            "point_id": "P01",
            "status": "resolved",
            "reason": "故意串用证据编号",
            "base_evidence_id": catalog["revised"][0]["id"],
        }
    )
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare._resolve_evidence(wrong, catalog)
    repeated = next(c for c in catalog["base"] if not c["citable"])
    wrong = wrong.model_copy(update={"base_evidence_id": repeated["id"]})
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare._resolve_evidence(wrong, catalog)


def test_overlapping_repeated_quote_is_ambiguous():
    source = synthetic_source()
    source["files"]["base"]["text"] = "ABABA"
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare.citation(source, {"base": [{"start": 0, "end": 5}]}, "base", "ABA")


def test_independent_support_check_downgrades_unjustified_judgement():
    rows = findings()
    checks = [{"point_id": r["point_id"], "supported": False} for r in rows]
    r = revision_compare.compare(synthetic_source(), Supplier(rows, checks), lambda: None, [])
    assert all(row["status"] == "uncertain" for row in r["rows"])


@pytest.mark.parametrize("kind", ["forged", "duplicate", "omitted"])
def test_model_cannot_fabricate_citations_or_skip_points(kind):
    s = synthetic_source()
    rows = findings()
    if kind == "forged":
        rows[0]["revised_quote"] = "不存在的修订原文。"
    elif kind == "duplicate":
        rows[1]["point_id"] = "P01"
    else:
        rows.pop()
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare.compare(s, Supplier(rows), lambda: None, [])


def test_missing_point_gets_one_bounded_repair_with_exact_schema_and_snapshot():
    class Recovering(Supplier):
        def completion(self, messages, tools):
            schema = tools[0]["function"]["parameters"]["properties"]
            if "findings" in schema:
                assert schema["findings"]["minItems"] == schema["findings"]["maxItems"] == 2
                assert schema["findings"]["items"]["properties"]["point_id"]["enum"] == [
                    "P01",
                    "P02",
                ]
            payload = json.loads(messages[1]["content"])
            if self.calls == 0:
                self.rows = findings()[:1]
                assert "validation_feedback" not in payload
            elif self.calls == 1:
                self.rows = findings()
                assert payload["validation_feedback"]["code"] == "schema_or_point_coverage"
                assert payload["expected_point_ids"] == ["P01", "P02"]
            return super().completion(messages, tools)

    provider = Recovering(findings())
    result = revision_compare.compare(synthetic_source(), provider, lambda: None, [])
    assert provider.calls == 3 and len(result["rows"]) == 2
    assert all(r["support_checked"] for r in result["rows"])


def test_format_repair_stops_after_two_attempts_without_support_pass():
    provider = Supplier(findings()[:1])
    with pytest.raises(GatewayError, match="revision_comparison_invalid"):
        revision_compare.compare(synthetic_source(), provider, lambda: None, [])
    assert provider.calls == 2


def test_schema_repair_feedback_does_not_echo_untrusted_property_names_or_values():
    marker = "untrusted-private-property-and-value"

    class InvalidThenFixed(Supplier):
        def completion(self, messages, tools):
            result = super().completion(messages, tools)
            if self.calls == 1:
                args = json.loads(
                    result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
                )
                args["findings"][0][marker] = marker
                result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = (
                    json.dumps(args)
                )
            elif self.calls == 2:
                payload = json.loads(messages[1]["content"])
                assert marker not in json.dumps(payload)
                errors = payload["validation_feedback"]["errors"]
                assert errors[0]["path"] == ["findings", 0, "unknown_field"]
                assert errors[0]["code"] == "extra_forbidden"
            return result

    provider = InvalidThenFixed(findings())
    assert (
        len(revision_compare.compare(synthetic_source(), provider, lambda: None, [])["rows"]) == 2
    )
    assert provider.calls == 3


def test_format_repair_reports_all_bad_quotes_and_only_reuses_verified_source_text():
    class MultipleInvalidThenFixed(Supplier):
        def completion(self, messages, tools):
            if self.calls == 0:
                self.rows = findings()
                self.rows[0]["revised_quote"] = "虚构新稿引文"
                self.rows[1]["base_quote"] = "虚构旧稿引文"
            elif self.calls == 1:
                payload = json.loads(messages[1]["content"])
                errors = payload["validation_feedback"]["errors"]
                assert {(e["point_id"], e["kind"]) for e in errors} == {
                    ("P01", "revised"),
                    ("P02", "base"),
                }
                for evidence in payload["verified_source_quotes"]:
                    assert (
                        evidence["quote"] in synthetic_source()["files"][evidence["kind"]]["text"]
                    )
                assert "虚构" not in json.dumps(payload, ensure_ascii=False)
                self.rows = findings()
            return super().completion(messages, tools)

    provider = MultipleInvalidThenFixed(findings())
    assert (
        len(revision_compare.compare(synthetic_source(), provider, lambda: None, [])["rows"]) == 2
    )
    assert provider.calls == 3


def test_partial_retrieval_cannot_prove_absence_and_mock_cannot_claim_resolution():
    s = synthetic_source()
    s["files"]["revised"]["text"] += "\n额外长稿。" * 4000
    rows = findings()
    rows[1]["status"] = "not_addressed"
    rows[1]["revised_quote"] = ""
    rows[1]["base_quote"] = ""
    r = revision_compare.compare(s, Supplier(rows), lambda: None, [])
    assert r["coverage"]["revised"]["complete"] is False and r["rows"][1]["status"] == "uncertain"
    mock = type("Mock", (), {"name": "mock"})()
    out = revision_compare.compare(s, mock, lambda: None, [])
    assert all(row["status"] == "uncertain" for row in out["rows"])


@pytest.fixture
def revision_case(client, login, world, monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    decide(client, login, mid)
    submit_revision(client, login, mid)
    login("editor")
    return mid


def test_actual_revision_comparison_persists_and_does_not_confirm_or_decide(
    client, login, db, revision_case
):
    mid = revision_case
    counts = {
        m: db.scalar(select(func.count()).select_from(m))
        for m in [ActionProposal, HumanConfirmation]
    }
    result = post(client, "请逐条对照修回：核查作者回复与修订原文。", mid)
    assert result.status_code == 200, result.text
    message = result.json()["messages"][1]
    report = message["revision_comparison"]
    assert (
        report["provider"] == "mock"
        and report["rows"]
        and all(r["status"] == "uncertain" for r in report["rows"])
    )
    assert result.json()["state_changed"] is False and message["action"] is None
    assert counts == {m: db.scalar(select(func.count()).select_from(m)) for m in counts}
    history = client.get("/api/publishing/chat", params={"manuscript_id": mid}).json()["messages"]
    assert history[-1]["revision_comparison"] == report
    hints = client.get(f"/api/publishing/manuscripts/{mid}/guidance").json()
    assert hints["suggestions"][0]["id"] == "revision-followup"
    login("reviewer")
    denied = post(client, "逐条对照修回和作者回复。", mid)
    assert denied.status_code in {403, 404}, denied.text


def test_comparison_request_without_formal_revision_never_invents_a_stage(client, login):
    from tests.api.test_publishing_intake import draft

    login("author")
    mid = draft(client)["manuscript_id"]
    response = post(client, "请逐条对照修回与审稿意见。", mid)
    assert response.status_code == 409, response.text


def test_corrupt_revision_bytes_block_replay_and_never_reinterpret_same_request(
    client, db, revision_case, monkeypatch
):
    from apps.api.publishing.domain import revision_sources

    mid = revision_case
    rid = str(uuid4())
    response = post(client, "请逐条对照修回与作者回复。", mid, rid)
    assert response.status_code == 200, response.text
    count = db.scalar(select(func.count()).select_from(PublishingChatTurn))

    def corrupt(*args):
        raise revision_sources.FileValidationError("synthetic corrupt bytes")

    monkeypatch.setattr(revision_sources, "read_bytes", corrupt)
    assert post(client, "请逐条对照修回与作者回复。", mid, rid).status_code == 409
    assert db.scalar(select(func.count()).select_from(PublishingChatTurn)) == count


def test_author_cannot_receive_private_reviewer_or_editor_fields(client, login, revision_case):
    mid = revision_case
    login("author")
    response = post(client, "请逐条对照修回与作者回复。", mid)
    assert response.status_code == 200, response.text
    encoded = response.text
    assert (
        "CHIEF-PRIVATE" not in encoded
        and "EDITOR-PRIVATE" not in encoded
        and "reviewer_name" not in encoded
    )
    assert response.json()["messages"][1]["revision_comparison"]["point_count"] > 0


def test_non_actionable_text_and_whitespace_changes_are_not_success():
    source = synthetic_source()
    source["files"]["revised"]["text"] = source["files"]["base"]["text"].replace("，", "， ")
    rows = findings()
    rows[0]["revised_quote"] = "样本量为40， 分组方法未说明。"
    rows[0]["status"] = "resolved"
    report = revision_compare.compare(source, Supplier(rows), lambda: None, [])
    assert report["rows"][0]["status"] == "uncertain"


def test_narrative_point_can_be_marked_non_actionable_without_becoming_resolution():
    source = synthetic_source()
    source["points"][0]["text"] = "感谢作者对本次工作的投入。"
    rows = findings()
    rows[0].update(
        status="not_applicable",
        reason="该句为致谢，不含修改要求。",
        response_quote="",
        revised_quote="",
        base_quote="",
    )
    report = revision_compare.compare(source, Supplier(rows), lambda: None, [])
    assert report["rows"][0]["status"] == "not_applicable"
    assert report["rows"][0]["citations"] == []
    assert report["human_confirmation_required"] is True


def test_staff_cannot_compare_unsubmitted_author_revision(
    client, login, world, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    mid = closed_round(client, login, world)
    recommend(client, login, mid)
    decide(client, login, mid)
    login("editor")
    out = post(client, "请逐条对照修回与作者回复。", mid)
    assert out.status_code == 409, out.text
    hints = client.get(f"/api/publishing/manuscripts/{mid}/guidance").json()
    assert hints["suggestions"][0]["id"] == "await-revision"


def test_changed_source_during_comparison_is_not_saved(client, db, revision_case, monkeypatch):
    from apps.api.publishing.domain import chat

    original = chat.load_revision
    calls = 0

    def changed(*args, **kwargs):
        nonlocal calls
        source = original(*args, **kwargs)
        calls += 1
        if calls > 1:
            source["source_fingerprint"] = "f" * 64
        return source

    monkeypatch.setattr(chat, "load_revision", changed)
    before = db.scalar(select(func.count()).select_from(PublishingChatTurn))
    response = post(client, "请逐条对照修回与作者回复。", revision_case)
    assert response.status_code == 409, response.text
    assert db.scalar(select(func.count()).select_from(PublishingChatTurn)) == before


def test_quoted_author_reply_cannot_be_called_no_response_even_if_model_check_agrees():
    rows = findings()
    rows[1]["status"] = "not_addressed"
    report = revision_compare.compare(synthetic_source(), Supplier(rows), lambda: None, [])
    assert report["rows"][1]["status"] == "uncertain"
    assert "初步结论" in report["rows"][1]["reason"]
