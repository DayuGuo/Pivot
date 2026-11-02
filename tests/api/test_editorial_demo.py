"""Synthetic workspace: real PostgreSQL persistence, scoped permissions, safe drafts."""

from copy import deepcopy

import pytest
from sqlalchemy import func, select

from apps.api.publishing.editorial_demo import DemoSavedViews, DemoWorkspaceState
from apps.api.publishing.models import AuditEvent, EditorialTask, Manuscript, Membership
from packages.editorial_demo import load_cases

URL = "/api/editorial-demo"
STATE = f"{URL}/cases/demo-001/state"


def patch(client, value, revision=0):
    return client.patch(STATE, json={"expected_revision": revision, "patch": value})


def test_fixture_integrity_and_long_originals():
    cases = load_cases()
    assert len(cases) >= 6
    assert len({c["stage_key"] for c in cases}) >= 6
    first = cases[0]
    assert first["id"] == "demo-001"
    assert len(first["versions"]) == 3 and len(first["rounds"]) == 2
    assert len(first["history"]) >= 12
    assert len(first["candidates"]) >= 3
    for case in cases:
        versions = {v["id"]: v for v in case["versions"]}
        attachments = {a["id"]: a for a in case["attachments"]}
        for v in versions.values():
            original = attachments[v["original"]]
            assert original["version"] == v["id"]
            for section in v["sections"]:
                assert len(section["paragraphs"]) >= 2
                assert all(p in original["content"] for p in section["paragraphs"])
        for issue in case["issues"]:
            for anchor in [issue["before"], issue["after"]]:
                section = next(
                    s
                    for s in versions[anchor["version"]]["sections"]
                    if s["id"] == anchor["section"]
                )
                assert anchor["quote"] in section["paragraphs"]
                assert anchor["quote"] in attachments[anchor["file"]]["content"]
                assert anchor["location"]
        for candidate in case["candidates"]:
            assert candidate["email"].endswith(".test")
            assert all(s.startswith("fixture://") for s in candidate["sources"])
    assert sum(len(p) for s in first["versions"][-1]["sections"] for p in s["paragraphs"]) > 12000


def test_dataset_get_is_pure_read_and_defaults_are_private(client, login, db, world):
    login()
    before = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.actor_id == world.users["editor"].id)
    )
    for _ in range(2):
        response = client.get(URL)
        assert response.status_code == 200
        data = response.json()
        assert data["demo"] is True
        assert data["states"]["demo-001"]["revision"] == 0
        assert data["states"]["demo-001"]["reading"]["version"] == "v3"
        assert data["saved_views"] == []
    assert (
        db.scalar(
            select(func.count())
            .select_from(DemoWorkspaceState)
            .where(
                DemoWorkspaceState.user_id == world.users["editor"].id,
                DemoWorkspaceState.journal_id == world.journal.id,
            )
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(DemoSavedViews)
            .where(
                DemoSavedViews.user_id == world.users["editor"].id,
                DemoSavedViews.journal_id == world.journal.id,
            )
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.actor_id == world.users["editor"].id)
        )
        == before
    )


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_non_editors_cannot_read_write_or_download(client, login, role):
    login(role)
    for method, url, body in [
        ("get", URL, None),
        ("get", f"{URL}/cases/demo-001/files/demo-001-v1-original", None),
        ("patch", STATE, {"expected_revision": 0, "patch": {"notes": "denied"}}),
        ("put", f"{URL}/views", {"views": []}),
    ]:
        response = getattr(client, method)(url, **({"json": body} if body is not None else {}))
        assert response.status_code == 403
        assert "cases" not in response.json()


def test_authentication_and_csrf_are_required(client, login):
    assert client.get(URL).status_code == 401
    login()
    del client.headers["X-CSRF-Token"]
    assert patch(client, {"notes": "denied"}).status_code == 403
    assert client.put(f"{URL}/views", json={"views": []}).status_code == 403
    assert client.get(URL).status_code == 200


def test_cross_site_mutations_denied(client, login):
    login()
    response = client.patch(
        STATE,
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"expected_revision": 0, "patch": {"notes": "denied"}},
    )
    assert response.status_code == 403


def test_state_persists_audits_and_never_changes_publishing(client, login, db, world):
    login()
    counts = [
        db.scalar(select(func.count()).select_from(model)) for model in (Manuscript, EditorialTask)
    ]
    body = {
        "selected_reviewers": ["candidate-1", "candidate-3"],
        "notes": "Private review note",
        "version_notes": {"v2": "第二版批注", "v3": "第三版批注"},
        "issue_statuses": {"issue-1": "resolved", "issue-2": "unverified"},
        "invitation": {
            "to": "reviewer1@editorial-demo.test",
            "subject": "合成邀请草稿",
            "body": "仅保留草稿",
            "due": "2026-11-15",
        },
        "decision": {"outcome": "major_revision", "body": "内部决定草稿；未发布"},
    }
    saved = patch(client, body)
    assert saved.status_code == 200, saved.text
    state = saved.json()
    assert state["revision"] == 1
    assert all(state[k] == v for k, v in body.items())
    assert client.get(URL).json()["states"]["demo-001"] == state
    assert [
        db.scalar(select(func.count()).select_from(model)) for model in (Manuscript, EditorialTask)
    ] == counts
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "editorial_demo.workspace_saved",
            AuditEvent.actor_id == world.users["editor"].id,
        )
    )
    assert event.details["revision"] == 1
    assert event.details["fields"] == sorted(body)
    assert "Private review note" not in str(event.details)
    assert patch(client, {"notes": "stale"}, revision=0).status_code == 409
    assert client.get(URL).json()["states"]["demo-001"]["notes"] == body["notes"]
    assert patch(client, {"notes": "second"}, revision=1).json()["revision"] == 2


def test_users_and_journals_have_independent_state_and_views(client, login, db, world):
    login()
    assert patch(client, {"notes": "editor only"}).status_code == 200
    view = {"query": "城市", "stage": "screening", "sort": "due", "name": "我的核验"}
    assert client.put(f"{URL}/views", json={"views": [view]}).status_code == 200
    login("chief_editor")
    dataset = client.get(URL).json()
    assert dataset["states"]["demo-001"]["revision"] == 0
    assert dataset["states"]["demo-001"]["notes"] == ""
    assert dataset["saved_views"] == []
    assert patch(client, {"notes": "chief only"}).json()["revision"] == 1
    login()
    assert client.get(URL).json()["states"]["demo-001"]["notes"] == "editor only"
    membership = db.scalar(select(Membership).where(Membership.user_id == world.users["editor"].id))
    membership.journal_id = world.other_journal.id
    db.commit()
    other = client.get(URL).json()
    assert other["states"]["demo-001"]["revision"] == 0
    assert other["saved_views"] == []
    assert patch(client, {"notes": "other journal"}).json()["revision"] == 1


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"notes": None},
        {"notes": "x" * 12001},
        {"status": "accepted"},
        {"send": True},
        {"task_status": "cancelled"},
        {"revision": 100},
        {"selected_reviewers": ["candidate-does-not-exist"]},
        {"selected_reviewers": ["candidate-1", "candidate-1"]},
        {"issue_statuses": {"unknown": "resolved"}},
        {"issue_statuses": {"issue-1": "published"}},
        {"reading": {"version": "v8", "section": "methods"}},
        {"reading": {"version": "v3", "section": "unknown"}},
        {"version_notes": {"v9": "stale note"}},
        {"version_notes": {"v3": "x" * 10001}},
        {"decision": {"outcome": "publish_now", "body": "no"}},
        {"decision": {"outcome": "accept", "body": "draft", "approved": True}},
        {"invitation": {"to": "person@example.com", "subject": "x", "body": "x", "due": ""}},
        {"invitation": {"to": "", "subject": "x", "body": "x", "due": "2026-99-01"}},
        {
            "ai_results": [
                {
                    "id": "a1",
                    "issue_id": "issue-1",
                    "status": "pending",
                    "text": "x",
                    "version": "v2",
                }
            ]
        },
        {
            "ai_results": [
                {
                    "id": "a1",
                    "issue_id": "unknown",
                    "status": "pending",
                    "text": "x",
                    "version": "v3",
                }
            ]
        },
        {
            "ai_results": [
                {
                    "id": "a1",
                    "issue_id": "issue-1",
                    "status": "approved",
                    "text": "x",
                    "version": "v3",
                }
            ]
        },
    ],
)
def test_rejects_unknown_or_unsafe_state(client, login, value):
    login()
    response = patch(client, value)
    assert response.status_code == 422, response.text
    assert client.get(URL).json()["states"]["demo-001"]["revision"] == 0


def test_read_navigation_preserves_version_bound_evidence(client, login):
    login()
    result = {
        "id": "mock-result-1",
        "issue_id": "issue-3",
        "status": "pending",
        "text": "Synthetic proposal",
        "version": "v3",
    }
    assert (
        patch(
            client, {"ai_results": [result], "issue_statuses": {"issue-1": "ignored"}}
        ).status_code
        == 200
    )
    changed = patch(client, {"reading": {"version": "v1", "section": "methods"}}, revision=1)
    assert changed.status_code == 200
    assert changed.json()["ai_results"] == [result]
    assert changed.json()["issue_statuses"]["issue-1"] == "ignored"
    # A result cannot claim a version where its issue has no supporting anchor.
    invalid = {**result, "version": "v1"}
    assert patch(client, {"ai_results": [invalid]}, revision=2).status_code == 422


def test_mixed_real_recipient_rejected_even_with_test_suffix(client, login):
    login()
    assert (
        patch(
            client,
            {
                "invitation": {
                    "to": "person@gmail.com, editor@example.test",
                    "subject": "Synthetic",
                    "body": "No sending",
                    "due": "",
                }
            },
        ).status_code
        == 422
    )


def test_strict_revision_unknown_case_and_invalid_body(client, login):
    login()
    assert (
        client.patch(STATE, json={"expected_revision": "0", "patch": {"notes": "x"}}).status_code
        == 422
    )
    assert (
        client.patch(STATE, json={"expected_revision": True, "patch": {"notes": "x"}}).status_code
        == 422
    )
    assert (
        client.patch(STATE, json={"expected_revision": -1, "patch": {"notes": "x"}}).status_code
        == 422
    )
    assert (
        client.patch(
            f"{URL}/cases/unknown/state", json={"expected_revision": 0, "patch": {"notes": "x"}}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            STATE, json={"expected_revision": 0, "patch": {"notes": "x"}, "user_id": "other"}
        ).status_code
        == 422
    )


def test_views_validate_persist_and_audit(client, login, db, world):
    login()
    views = [
        {"query": "", "stage": "all", "sort": "due", "name": "全部", "today_only": True},
        {"query": "城市", "stage": "screening", "sort": "priority"},
    ]
    response = client.put(f"{URL}/views", json={"views": views})
    assert response.status_code == 200, response.text
    assert response.json()["saved_views"] == views
    assert client.get(URL).json()["saved_views"] == views
    assert (
        db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "editorial_demo.views_saved",
                AuditEvent.actor_id == world.users["editor"].id,
            )
        ).details["count"]
        == 2
    )
    for invalid in [
        views * 7,
        [{"query": "", "stage": "secret", "sort": "due"}],
        [{"query": "", "stage": "all", "sort": "sql"}],
        [{"query": "", "stage": "all", "sort": "due", "user_id": "other"}],
        [views[0], deepcopy(views[0])],
        [{"query": "", "stage": "all", "sort": "due", "name": " "}],
    ]:
        assert client.put(f"{URL}/views", json={"views": invalid}).status_code == 422
    assert client.get(URL).json()["saved_views"] == views
    assert client.put(f"{URL}/views", json={"views": []}).status_code == 200


def test_original_files_remain_accessible_without_state_write(client, login, db, world):
    login()
    for v in load_cases()[0]["versions"]:
        response = client.get(f"{URL}/cases/demo-001/files/{v['original']}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "attachment;" in response.headers["content-disposition"]
        assert f"版本：{v['id']}" in response.text
        assert v["sections"][0]["paragraphs"][0] in response.text
    for path in [
        "demo-001/files/unknown",
        "unknown/files/demo-001-v1-original",
        "demo-002/files/demo-001-v1-original",
        "demo-001/files/..%2F..%2Fetc%2Fpasswd",
    ]:
        assert client.get(f"{URL}/cases/{path}").status_code == 404
    assert (
        db.scalar(
            select(func.count())
            .select_from(DemoWorkspaceState)
            .where(
                DemoWorkspaceState.user_id == world.users["editor"].id,
                DemoWorkspaceState.journal_id == world.journal.id,
            )
        )
        == 0
    )


def test_fixture_phases_and_manuscript_contents_are_coherent():
    cases = {case["id"]: case for case in load_cases()}
    assert cases["demo-001"]["stage_key"] == "decision"
    assert cases["demo-001"]["stage"] == "修回核验"
    assert all("v" in r["label"] for r in cases["demo-001"]["rounds"])
    for case_id in ("demo-002", "demo-005"):
        assert cases[case_id]["rounds"] == []
        assert cases[case_id]["issues"] == []
        assert len(cases[case_id]["versions"]) == 1
    assert cases["demo-005"]["stage_key"] == "screening"
    reviewer_round = cases["demo-003"]["rounds"]
    assert len(reviewer_round) == 1 and reviewer_round[0]["number"] == 1
    assert reviewer_round[0]["tasks"] == []
    assert "尚未邀请" in reviewer_round[0]["label"]
    active = cases["demo-004"]
    assert len(active["rounds"]) == len(active["versions"]) == 1
    assert "v1" in active["rounds"][0]["label"]
    assert all(task["status"] == "评审中" for task in active["rounds"][0]["tasks"])
    production = cases["demo-006"]
    assert production["stage_key"] == "production"
    assert any(
        "预设历史背景" in h["text"] and "并非本系统执行" in h["text"] for h in production["history"]
    )
    method_texts = set()
    for case in cases.values():
        version = case["versions"][0]
        method_texts.add(
            next(s["paragraphs"][0] for s in version["sections"] if s["id"] == "methods")
        )
        original = next(a for a in case["attachments"] if a["id"] == version["original"])
        assert case["title"] in original["content"]
        assert case["title_en"] in original["content"]
        dates = [event["date"] for event in case["history"]]
        assert dates == sorted(dates)
        if case["id"] != "demo-001":
            assert "绿地组" not in original["content"]
            assert "站点重采样" not in original["content"]
            assert not any(a["id"].endswith("-response") for a in case["attachments"])
    assert len(method_texts) == len(cases)


def test_reading_position_persists_paragraph_and_rejects_invalid_index(client, login):
    login()
    value = {"version": "v3", "section": "methods", "paragraph": 2}
    saved = patch(client, {"reading": value})
    assert saved.status_code == 200
    assert client.get("/api/editorial-demo").json()["states"]["demo-001"]["reading"] == value
    assert patch(client, {"reading": {**value, "paragraph": 9999}}, revision=1).status_code == 422
    assert patch(client, {"reading": {**value, "paragraph": -1}}, revision=1).status_code == 422
