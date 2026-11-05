"""Licensed public version pairs through actual formal imports and human gates."""

import hashlib

import pytest
from fastapi import Request
from sqlalchemy import func, select

from apps.api.publishing.domain import revision_compare
from apps.api.publishing.domain.models import ActionProposal, HumanConfirmation, VersionFile
from apps.api.publishing.domain.revision_sources import (
    comparison_offset,
    load_revision,
    point_spans,
)
from apps.api.publishing.security import get_actor
from evals.public_revisions.workflow import ROOT, build_case, cases
from packages.document_ingest import extract_document
from tests.api.test_publishing_chat import post
from tests.api.test_revision_comparison import Supplier


@pytest.mark.parametrize("case", cases(), ids=lambda c: c["id"])
def test_public_pdf_and_word_originals_are_complete_licensed_and_unchanged(case):
    for version in case["versions"].values():
        for format in ("pdf", "docx"):
            info = version[format]
            raw = (ROOT / info["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == info["sha256"]
            parsed = extract_document((ROOT / info["path"]).name, raw)
            assert (
                len(parsed["segments"]) == version["article_page_count"]
                if format == "pdf"
                else len(parsed["segments"]) == info["paragraph_count"]
            )
            assert "Open Peer Review\nCurrent Peer Review Status" not in parsed["text"]
            if format == "docx":
                for guard in version["xml_body_guards"]:
                    assert guard in parsed["text"]
    assert case["response"]["scope"] == "published_author_revision_note_excerpt"
    assert all(
        "creativecommons.org/licenses/by/" in r["license_url"] for r in case["review_requirements"]
    )


@pytest.mark.parametrize(
    "case,base_format,revised_format",
    [
        (c, *formats)
        for c, formats in zip(
            cases(), [("pdf", "docx"), ("pdf", "pdf"), ("docx", "docx")], strict=True
        )
    ],
    ids=["oath-pdf-word", "guidelines-pdf-pdf", "survey-word-word"],
)
def test_public_versions_import_confirm_revision_compare_and_original_spans(
    client, login, db, world, monkeypatch, tmp_path, case, base_format, revised_format
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    mid = build_case(client, login, world, case, base_format, revised_format)
    before = client.get(f"/api/publishing/manuscripts/{mid}").json()
    counts = {
        m: db.scalar(select(func.count()).select_from(m))
        for m in [ActionProposal, HumanConfirmation]
    }
    result = post(client, "请逐条对照修回与作者回复。", mid)
    assert result.status_code == 200, result.text
    report = result.json()["messages"][1]["revision_comparison"]
    assert report["provider"] == "mock" and report["human_confirmation_required"]
    assert report["coverage"]["response"]["source_complete"] is False
    assert all(r["status"] == "uncertain" for r in report["rows"])
    assert client.get(f"/api/publishing/manuscripts/{mid}").json() == before
    assert counts == {m: db.scalar(select(func.count()).select_from(m)) for m in counts}
    # Obtain the same current actor from the real session dependency, not a made-up role.
    token = client.cookies.get("publishing_session")
    actor = get_actor(
        Request(
            {
                "type": "http",
                "method": "GET",
                "headers": [(b"cookie", f"publishing_session={token}".encode())],
            }
        ),
        db,
    )
    source = load_revision(db, actor, mid)
    for kind, file in source["files"].items():
        assert file["origin"] and db.get(VersionFile, file["file_id"])
        # Cite a unique middle-of-paragraph passage from each actual file.
        quote = next(
            s["text"][:120]
            for s in file["origin"]["segments"]
            if len(s["text"]) >= 120
            and file["text"].count(s["text"][:120]) == 1
            and s["text"][:120] in file["text"]
        )
        start = file["text"].index(quote)
        cite = revision_compare.citation(
            source, {kind: [{"start": 0, "end": len(file["text"])}]}, kind, quote
        )
        assert file["text"][cite["start"] : cite["end"]] == quote
        assert "".join(p["quote"] for p in cite["original"]["locations"]) == quote
        assert client.get(cite["original"]["download_url"]).status_code == 200
        assert start == cite["start"]
    login("reviewer")
    assert client.get(source["files"]["base"]["origin"]["download_url"]).status_code == 404


def test_long_requirements_have_no_lost_tail_and_never_certify_fragment():
    value = "First requirement " + "x" * 2450 + " THE-TAIL-MUST-NOT-DISAPPEAR"
    spans = list(point_spans(value))
    assert len(spans) == 3 and "".join(s[2] for s in spans) == value
    assert all(value[start:end] == text and not complete for start, end, text, complete in spans)


def test_real_author_note_cannot_make_unchanged_article_a_successful_revision():
    from tests.api.test_revision_comparison import synthetic_source

    case = cases()[0]
    source = synthetic_source()
    manuscript = ROOT / case["versions"]["1"]["docx"]["path"]
    response = ROOT / case["response"]["path"]
    text = extract_document(manuscript.name, manuscript.read_bytes())["text"]
    note = extract_document(response.name, response.read_bytes())["text"]
    source["files"]["base"]["text"] = source["files"]["revised"]["text"] = text
    source["files"]["response"]["text"] = note
    windows, _ = revision_compare.material_windows(source)
    quote = next(w["text"][:100] for w in windows["revised"] if text.count(w["text"][:100]) == 1)
    rows = [
        {
            "point_id": p["id"],
            "status": "resolved",
            "reason": "故意错误的模型结论：作者声称已经修订。",
            "response_quote": note[:100],
            "revised_quote": quote,
            "base_quote": "",
        }
        for p in source["points"]
    ]
    report = revision_compare.compare(source, Supplier(rows), lambda: None, [])
    assert all(r["status"] == "uncertain" for r in report["rows"])


def test_incomplete_public_response_cannot_prove_absence_or_whole_requirement_success():
    from tests.api.test_revision_comparison import findings, synthetic_source

    source = synthetic_source()
    source["files"]["response"]["origin"] = {"source_complete": False}
    rows = findings()
    rows[1].update(status="not_addressed", response_quote="", revised_quote="", base_quote="")
    # No original citation needed for this empty response quote; first row uses an ordinary file.
    source["files"]["response"]["origin"].update(
        selection_start=0,
        selection_end=len(source["files"]["response"]["text"]),
        filename="excerpt.docx",
        sha256="c" * 64,
        download_url="/api/publishing/files/test/original",
        segments=[
            {
                "kind": "docx_paragraph",
                "number": 1,
                "start": 0,
                "end": len(source["files"]["response"]["text"]),
                "text": source["files"]["response"]["text"],
            }
        ],
    )
    report = revision_compare.compare(source, Supplier(rows), lambda: None, [])
    assert report["rows"][1]["status"] == "uncertain"


def test_all_requirement_batches_are_reachable_and_replay_keeps_exact_batch(
    client, login, world, monkeypatch, tmp_path
):
    import copy
    from uuid import uuid4

    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    case = copy.deepcopy(cases()[0])
    case["review_requirements"] = [
        {"text": f"合成分页回归要求{i}：请核对当前版本的方法、实际证据和作者回复，保留不确定性。"}
        for i in range(11)
    ]
    mid = build_case(client, login, world, case, "docx", "docx")
    first = post(client, "请逐条对照修回与作者回复。", mid).json()["messages"][1][
        "revision_comparison"
    ]
    assert first["next_offset"] == 8 and first["point_count"] > 8
    rid = str(uuid4())
    message = "保留已有的未发送问题。\n\n请从第9项开始，逐条对照修回与作者回复。"
    second = post(client, message, mid, rid)
    assert second.status_code == 200, second.text
    report = second.json()["messages"][1]["revision_comparison"]
    assert post(client, message, mid, rid).json() == second.json()
    assert report["point_offset"] == 8 and report["next_offset"] is None
    ids = [r["point_id"] for r in first["rows"] + report["rows"]]
    assert len(ids) == len(set(ids)) == first["point_count"]
    assert first["source_fingerprint"] == report["source_fingerprint"]
    assert post(client, "请从第999项开始，逐条对照修回与作者回复。", mid).status_code == 422
    assert post(client, "请从第0项开始，逐条对照修回与作者回复。", mid).status_code == 422


def test_comparison_offset_handles_appended_user_prompt_and_rejects_huge_integer():
    from fastapi import HTTPException

    assert comparison_offset("普通修回问题") == 0
    assert comparison_offset("请从第1项开始。\n\n请从第9项开始，逐条对照修回。") == 8
    with pytest.raises(HTTPException) as error:
        comparison_offset("请从第" + "9" * 6000 + "项开始，逐条对照修回。")
    assert error.value.status_code == 422
