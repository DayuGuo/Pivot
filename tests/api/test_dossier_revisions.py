"""Internal revision checks never invent a formal submission, consent or decision."""

import base64
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.domain import dossier_revisions
from apps.api.publishing.domain.decision_models import EditorialDecision
from apps.api.publishing.domain.dossier_revision_models import (
    DossierRevisionCheck,
    DossierRevisionReview,
)
from apps.api.publishing.domain.dossier_revision_schemas import DossierRevisionInput
from apps.api.publishing.domain.models import ActionReceipt, HumanConfirmation
from apps.api.publishing.models import AuditEvent, EmailDraft, Manuscript, Membership
from packages.model_gateway.gateway import GatewayError
from tests.api.test_dossiers import create, detail, metadata, save, upload
from tests.api.test_revision_comparison import Supplier

BASE = "样本量为40，分组方法未说明。\n未提供数据链接。\n没有新增附录。\n个体数据不公开。"
REVISED = "样本量更正为80，按预先规定规则分成两组。\n数据链接将在后续提供。\n没有新增附录。\n个体数据不公开。"
RESPONSE = "已更正样本量和分组说明。\n数据链接将在后续提供，本次未补充。\n我们已经增加附录。\n我们不采纳公开个体数据的建议，原因是参与者隐私。"


def rid():
    return str(uuid4())


def endpoint(item, check=None, suffix=""):
    return f"/api/dossiers/{item['id']}/revision-checks" + (f"/{check}" if check else "") + suffix


def body(base, revised, **changes):
    return {
        "request_id": rid(),
        "expected_revision": revised["revision"],
        "base_version_id": base["version_id"],
        "revised_version_id": revised["version_id"],
        "base_complete": True,
        "revised_complete": True,
        "requirements": [
            {"text": item, "original_context": "这是一组完全合成的编辑意见：" + item}
            for item in (
                "请更正样本量并说明分组。",
                "请提供公开数据链接。",
                "请增加附录。",
                "建议公开个体数据，可以解释不公开的理由。",
            )
        ],
        "requirements_complete": True,
        "response_text": RESPONSE,
        "response_complete": True,
        "source_note": "完全合成材料，编辑独立粘贴意见和作者回复，不构成正式投稿。",
        "authorized_material": True,
        **changes,
    }


def checked(client, base, revised, **changes):
    data = body(base, revised, **changes)
    response = client.post(endpoint(revised), json=data)
    assert response.status_code == 200, response.text
    check_id = response.json()["check_id"]
    read = client.get(endpoint(revised, check_id))
    assert read.status_code == 200, read.text
    return data, read.json()


def judgement(check, **changes):
    return {
        "request_id": rid(),
        "check_digest": check["digest"],
        "expected_review_id": None,
        "response_verdict": "addressed",
        "implementation_verdict": "unchanged",
        "editor_verdict": "sufficient",
        "reason": "本人核对了回复和原文，认为隐私解释足以处理这条建议。",
        "acknowledged": True,
        **changes,
    }


@pytest.fixture
def versions(client, login, monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    base = save(client, create(client), file=upload(raw=BASE.encode()))
    revised = save(client, base, file=upload(raw=REVISED.encode()))
    return base, revised


def number(db, model, **filters):
    return db.scalar(select(func.count()).select_from(model).filter_by(**filters))


def test_mock_packet_is_version_bound_exportable_and_never_creates_formal_business(
    client, db, versions
):
    base, revised = versions
    before = {
        m: number(db, m) for m in (Manuscript, EditorialDecision, HumanConfirmation, EmailDraft)
    }
    sent, result = checked(client, base, revised)
    assert result["schema"] == "dossier-revision-check.v1" and result["is_current"]
    assert result["base_version_no"] == base["version_no"]
    assert result["revised_version_no"] == revised["version_no"]
    assert result["report"]["schema"] == "dossier-revision-comparison.v1"
    assert all(r["status"] == "uncertain" for r in result["report"]["rows"])
    assert result["materials"]["requirements"] == sent["requirements"]
    assert result["reviews"] == {}
    exported = client.get(endpoint(revised, result["id"], "/export"))
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    packet = exported.json()
    assert packet["sources"]["base"]["text"] == BASE
    assert packet["sources"]["revised"]["text"] == REVISED
    assert packet["sources"]["response"]["text"] == RESPONSE
    assert packet["sources"]["response"]["download_url"] is None
    assert packet["human_feedback_is_not_publication_approval"] is True
    assert detail(client, revised["id"]) == revised
    assert {m: number(db, m) for m in before} == before


def test_protocol_keeps_change_partial_claim_and_reasoned_non_adoption_separate(
    client, versions, monkeypatch
):
    base, revised = versions
    rows = [
        {
            "point_id": "P01",
            "status": "resolved",
            "reason": "已找到样本量和分组的对应修改。",
            "response_quote": "已更正样本量和分组说明。",
            "revised_quote": "样本量更正为80，按预先规定规则分成两组。",
            "base_quote": "样本量为40，分组方法未说明。",
        },
        {
            "point_id": "P02",
            "status": "partial",
            "reason": "作者承诺后续提供，但本次尚未提供链接。",
            "response_quote": "数据链接将在后续提供，本次未补充。",
            "revised_quote": "数据链接将在后续提供。",
            "base_quote": "未提供数据链接。",
        },
        {
            "point_id": "P03",
            "status": "uncertain",
            "reason": "作者声称增加附录，尚未定位到落实依据。",
            "response_quote": "我们已经增加附录。",
            "revised_quote": "",
            "base_quote": "",
        },
        {
            "point_id": "P04",
            "status": "explained",
            "reason": "作者解释了不公开的理由，不自动评价理由是否充分。",
            "response_quote": "我们不采纳公开个体数据的建议，原因是参与者隐私。",
            "revised_quote": "个体数据不公开。",
            "base_quote": "个体数据不公开。",
        },
    ]
    provider = Supplier(rows)
    monkeypatch.setattr(dossier_revisions, "get_editorial_provider", lambda: provider)
    _, result = checked(client, base, revised, response_complete=False)
    assert provider.calls == 2
    assert [r["status"] for r in result["report"]["rows"]] == [
        "resolved",
        "partial",
        "uncertain",
        "explained",
    ]
    assert result["report"]["coverage"]["response"]["source_complete"] is False
    files = {"base": BASE, "revised": REVISED, "response": RESPONSE}
    for row in result["report"]["rows"]:
        assert row["point"]["original_context"]
        for cite in row["citations"]:
            assert files[cite["kind"]][cite["start"] : cite["end"]] == cite["quote"]
            assert "/api/publishing/files" not in (cite["download_url"] or "")
            if cite["kind"] == "response":
                assert cite["source_type"] == "pasted_text" and not cite.get("original")
            else:
                assert f"/api/dossiers/{revised['id']}/versions/" in cite["download_url"]


def test_retry_is_idempotent_and_reusing_uuid_for_changed_packet_conflicts(client, db, versions):
    base, revised = versions
    sent, result = checked(client, base, revised)
    original = number(db, DossierRevisionCheck, dossier_id=revised["id"])
    assert client.post(endpoint(revised), json=sent).json()["check_id"] == result["id"]
    changed = {**sent, "response_text": "这是不同回复，不得借用已成功的请求编号。"}
    assert client.post(endpoint(revised), json=changed).status_code == 409
    assert number(db, DossierRevisionCheck, dossier_id=revised["id"]) == original


def test_manual_three_layers_are_append_only_and_have_independent_compare_and_swap(
    client, db, versions
):
    base, revised = versions
    _, result = checked(client, base, revised)
    url = endpoint(revised, result["id"], "/points/P04/reviews")
    data = judgement(result)
    one = client.post(url, json=data)
    assert one.status_code == 200, one.text
    assert client.post(url, json=data).json() == one.json()
    assert client.post(url, json=judgement(result)).status_code == 409
    two = client.post(
        url,
        json=judgement(
            result,
            expected_review_id=one.json()["id"],
            editor_verdict="needs_judgment",
            reason="补充核对后保留分歧，不覆盖第一次人工判断。",
        ),
    )
    assert two.status_code == 200, two.text
    assert number(db, DossierRevisionReview, check_id=result["id"]) == 2
    page = client.get(url + "?limit=1").json()
    assert page["next_cursor"] == 2 and page["items"][0]["review_no"] == 2
    assert client.get(url + "?limit=1&before=2").json()["items"][0]["review_no"] == 1
    loaded = client.get(endpoint(revised, result["id"])).json()
    assert loaded["report"] == result["report"]
    assert loaded["reviews"]["P04"]["editor_verdict"] == "needs_judgment"
    assert detail(client, revised["id"]) == revised


@pytest.mark.parametrize("ack", [False, 1, "true", None])
def test_manual_ack_is_explicit_boolean(client, versions, ack):
    base, revised = versions
    _, result = checked(client, base, revised)
    assert (
        client.post(
            endpoint(revised, result["id"], "/points/P01/reviews"),
            json=judgement(result, acknowledged=ack),
        ).status_code
        == 422
    )


def test_old_packet_replay_and_human_feedback_do_not_retarget_new_version(client, versions):
    base, revised = versions
    sent, result = checked(client, base, revised)
    latest = save(client, revised, data=metadata(title="后续新版本，旧核对不能变成当前结论"))
    loaded = client.get(endpoint(revised, result["id"]))
    assert loaded.status_code == 200 and loaded.json()["is_current"] is False
    assert client.post(endpoint(revised), json=sent).json()["check_id"] == result["id"]
    assert (
        client.post(
            endpoint(revised, result["id"], "/points/P04/reviews"), json=judgement(result)
        ).status_code
        == 200
    )
    assert detail(client, revised["id"])["version_id"] == latest["version_id"]


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_other_roles_and_other_owner_cannot_read_export_or_replay(client, login, versions, role):
    base, revised = versions
    sent, result = checked(client, base, revised)
    login(role)
    assert client.get(endpoint(revised)).status_code == 404
    assert client.get(endpoint(revised, result["id"])).status_code == 404
    assert client.get(endpoint(revised, result["id"], "/export")).status_code == 404
    assert client.post(endpoint(revised), json=sent).status_code == 404
    assert (
        client.post(
            endpoint(revised, result["id"], "/points/P04/reviews"), json=judgement(result)
        ).status_code
        == 404
    )


def test_cross_dossier_versions_wrong_order_and_stale_current_are_rejected(client, versions):
    base, revised = versions
    assert client.post(endpoint(revised), json=body(revised, revised)).status_code == 422
    other = save(client, create(client), file=upload(raw=BASE.encode()))
    assert (
        client.post(
            endpoint(revised), json=body(base, revised, base_version_id=other["version_id"])
        ).status_code
        == 404
    )
    save(client, revised, data=metadata(title="后续版本使生成请求失效"))
    assert client.post(endpoint(revised), json=body(base, revised)).status_code == 409


@pytest.mark.parametrize("field", ["response_text", "source_note"])
def test_material_credentials_never_reach_model(client, versions, monkeypatch, field):
    base, revised = versions

    def forbidden():
        raise AssertionError("Secret-bearing input must be blocked before provider creation")

    monkeypatch.setattr(dossier_revisions, "get_editorial_provider", forbidden)
    marker = "sk-" + "synthetic-private-placeholder" * 3
    assert (
        client.post(endpoint(revised), json=body(base, revised, **{field: marker})).status_code
        == 422
    )


def test_provider_failure_and_authority_change_leave_no_success_record(
    client, db, world, versions, monkeypatch
):
    base, revised = versions

    def unavailable(*args):
        args[-1].append(
            {"provider": "deepseek", "input_tokens": 123, "output_tokens": 7, "cost_usd": None}
        )
        raise GatewayError("never log arbitrary supplier details")

    monkeypatch.setattr(dossier_revisions, "compare", unavailable)
    data = body(base, revised)
    failed = client.post(endpoint(revised), json=data)
    assert failed.status_code == 503 and "supplier" not in failed.text
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == revised["id"],
            AuditEvent.action == "publishing.dossier_revision_check_failed",
        )
    )
    assert audit.details["error_code"] == "publishing_turn_failed"
    assert audit.details["telemetry"][0]["input_tokens"] == 123
    assert "supplier" not in str(audit.details)
    assert number(db, DossierRevisionCheck, dossier_id=revised["id"]) == 0
    assert (
        db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == data["request_id"]))
        is None
    )

    original_compare = __import__(
        "apps.api.publishing.domain.revision_compare", fromlist=["compare"]
    ).compare

    def revoked(*args):
        report = original_compare(*args)
        db.execute(
            update(Membership)
            .where(
                Membership.user_id == world.users["editor"].id,
                Membership.journal_id == world.journal.id,
            )
            .values(role="author")
        )
        return report

    monkeypatch.setattr(dossier_revisions, "compare", revoked)
    assert client.post(endpoint(revised), json=body(base, revised)).status_code == 403
    assert number(db, DossierRevisionCheck, dossier_id=revised["id"]) == 0


def test_json_snapshot_hash_and_original_bytes_are_rechecked_for_export_and_replay(
    client, db, versions, monkeypatch
):
    base, revised = versions
    sent, result = checked(client, base, revised)
    from apps.api.publishing.domain import dossier_access

    original = dossier_access.file_content

    def corrupt(db, item):
        if item.id == base["version_id"]:
            from fastapi import HTTPException

            raise HTTPException(409, "合成CAS损坏")
        return original(db, item)

    monkeypatch.setattr(dossier_access, "file_content", corrupt)
    assert client.get(endpoint(revised, result["id"])).status_code == 409
    assert client.get(endpoint(revised, result["id"], "/export")).status_code == 409
    assert client.post(endpoint(revised), json=sent).status_code == 409
    assert (
        client.post(
            endpoint(revised, result["id"], "/points/P01/reviews"), json=judgement(result)
        ).status_code
        == 409
    )


def test_packet_listing_is_bounded_and_cursor_is_not_cross_dossier_authority(client, versions):
    base, revised = versions
    _, first = checked(client, base, revised)
    _, second = checked(client, base, revised)
    page = client.get(endpoint(revised) + "?limit=1").json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    next_page = client.get(endpoint(revised) + "?limit=1&cursor=" + page["next_cursor"]).json()
    assert {page["items"][0]["id"], next_page["items"][0]["id"]} == {first["id"], second["id"]}
    other = create(client)
    assert client.get(endpoint(other) + "?cursor=" + page["next_cursor"]).status_code == 422


def test_sql_guards_reject_history_mutation_and_tenant_or_requirement_forgery(client, db, versions):
    base, revised = versions
    _, result = checked(client, base, revised)
    for statement in (
        "UPDATE publishing_dossier_revision_checks SET digest=repeat('a',64) WHERE id=:id",
        "DELETE FROM publishing_dossier_revision_checks WHERE id=:id",
        "TRUNCATE publishing_dossier_revision_checks CASCADE",
    ):
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(text(statement), {"id": result["id"]})
    existing = db.get(DossierRevisionCheck, result["id"])
    values = {column.name: getattr(existing, column.name) for column in existing.__table__.columns}
    for changes in (
        {"base_version_id": existing.revised_version_id},
        {"created_by": str(uuid4())},
        {"report_json": {**existing.report_json, "rows": []}},
    ):
        with pytest.raises(DBAPIError), db.begin_nested():
            db.add(DossierRevisionCheck(**{**values, "id": rid(), **changes}))
            db.flush()


def test_shape_preserves_context_and_rejects_duplicate_or_unbounded_requirements(versions):
    base, revised = versions
    values = body(base, revised)
    for changes in (
        {"requirements": values["requirements"] * 3},
        {"requirements": [values["requirements"][0]] * 2},
        {"requirements": [{"text": "请核对", "original_context": ""}]},
        {"response_complete": "false"},
    ):
        with pytest.raises(ValueError):
            DossierRevisionInput.model_validate({**deepcopy(values), **changes})
    assert len(base64.b64decode(upload(raw=BASE.encode())["content_base64"])) > 0
