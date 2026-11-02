"""Real normalized author submission: permissions, snapshots, files and confirmation."""

import base64
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.models import (
    ActionReceipt,
    HumanConfirmation,
    ManuscriptVersion,
    SubmissionWorkflow,
)
from apps.api.publishing.models import Manuscript

URL = "/api/publishing"


def request_id():
    return str(uuid4())


def draft(client):
    response = client.post(
        URL + "/drafts", json={"request_id": request_id(), "title": "合成研究：开放科学投稿验证"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def complete_data():
    return {
        "title": "合成研究：开放科学投稿验证",
        "abstract": "本研究使用完全合成的测试数据验证科研出版工作流中的作者元数据、版本文件、责任确认与审计一致性，不涉及真实参与者或保密材料。",
        "language": "zh",
        "article_type": "research_article",
        "keywords": ["合成数据", "开放科学"],
        "authors": [
            {
                "name": "测试署名作者",
                "email": "author@synthetic.test",
                "orcid": None,
                "affiliations": ["合成研究机构"],
                "corresponding": True,
                "contributions": ["Writing – original draft"],
            }
        ],
        "funding_statement": "本合成研究无资助。",
        "declarations": {
            "originality": True,
            "copyright": True,
            "competing_interests": "none",
            "competing_interests_text": "",
            "ethics": "not_applicable",
            "ethics_reference": "",
        },
    }


def detail(client, mid):
    response = client.get(f"{URL}/manuscripts/{mid}")
    assert response.status_code == 200, response.text
    return response.json()


def fill(client, created):
    mid = created["manuscript_id"]
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={
            "request_id": request_id(),
            "expected_revision": created["revision"],
            "data": complete_data(),
        },
    )
    assert response.status_code == 200, response.text
    revision = response.json()["revision"]
    for purpose in ("manuscript", "blinded_manuscript"):
        response = client.post(
            f"{URL}/manuscripts/{mid}/files",
            json={
                "request_id": request_id(),
                "expected_revision": revision,
                "file": {
                    "filename": purpose + ".txt",
                    "purpose": purpose,
                    "content_base64": base64.b64encode(
                        ("合成无身份研究材料。\n" + purpose).encode()
                    ).decode(),
                },
            },
        )
        assert response.status_code == 200, response.text
        revision = response.json()["revision"]
    return detail(client, mid)


def prepare(client, data):
    mid = data["id"]
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "action_type": "submit",
            "data": {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "private-files"))


def test_author_real_draft_files_review_confirm_persist_and_editor_task(client, login, db, world):
    login("author")
    created = draft(client)
    mid = created["manuscript_id"]
    original = detail(client, mid)
    assert original["stage"] == "author_draft" and original["is_owner"]
    assert original["missing"] and not original["version"]["data"]["declarations"]["originality"]
    data = fill(client, created)
    assert data["missing"] == []
    assert len(data["version"]["files"]) == 2
    file = data["version"]["files"][0]
    response = client.get(file["download_url"])
    assert response.status_code == 200 and response.content.startswith("合成".encode())
    proposal = prepare(client, data)
    # Preparing the complete snapshot cannot submit a manuscript.
    assert detail(client, mid)["stage"] == "author_draft"
    review = client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()
    assert review["status"] == "pending" and len(review["payload"]["version"]["files"]) == 2
    confirm = {
        "request_id": request_id(),
        "expected_revision": data["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }
    response = client.post(f"{URL}/proposals/{proposal['proposal_id']}/confirmations", json=confirm)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["stage"] == "precheck_completeness"
    assert (
        client.post(f"{URL}/proposals/{proposal['proposal_id']}/confirmations", json=confirm).json()
        == saved
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 1
    )
    version = db.get(ManuscriptVersion, data["version"]["id"])
    assert version.frozen_at and version.content_digest
    assert db.get(Manuscript, mid).workflow_kind == "publishing"
    assert db.get(Manuscript, mid).editor_id is None
    # The old broad editor API must not become a permissions bypass.
    assert client.get(f"/api/manuscripts/{mid}").status_code == 404
    assert mid not in str(client.get("/api/workspace").json()["manuscripts"])
    assert detail(client, mid)["version"]["data"]["authors"][0]["name"] == "测试署名作者"
    login("editor")
    work = client.get(URL + "/workspace").json()
    assert any(
        t["manuscript_id"] == mid and t["kind"] == "precheck_completeness" for t in work["tasks"]
    )
    assert detail(client, mid)["stage"] == "precheck_completeness"


def test_missing_data_cannot_prepare_confirmation_and_other_roles_cannot_see_draft(client, login):
    login("author")
    created = draft(client)
    mid = created["manuscript_id"]
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": 0,
            "action_type": "submit",
            "data": {},
        },
    )
    assert response.status_code == 422
    for role in ("editor", "chief_editor", "reviewer"):
        login(role)
        assert client.get(f"{URL}/manuscripts/{mid}").status_code == 404
        assert mid not in str(client.get(URL + "/workspace").json())


def test_changed_form_or_file_expires_snapshot_and_no_actor_can_substitute(client, login, db):
    login("author")
    data = fill(client, draft(client))
    mid = data["id"]
    proposal = prepare(client, data)
    login("editor")
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 404
    assert (
        client.post(
            f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
            json={
                "request_id": request_id(),
                "expected_revision": data["revision"],
                "digest": proposal["digest"],
                "acknowledged": True,
            },
        ).status_code
        == 404
    )
    login("author")
    update = complete_data()
    update["title"] = "人工更改后的合成标题"
    response = client.patch(
        f"{URL}/manuscripts/{mid}/intake",
        json={"request_id": request_id(), "expected_revision": data["revision"], "data": update},
    )
    assert response.status_code == 200, response.text
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").json()["status"] == "expired"
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json={
            "request_id": request_id(),
            "expected_revision": response.json()["revision"],
            "digest": proposal["digest"],
            "acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(HumanConfirmation)
            .where(HumanConfirmation.manuscript_id == mid)
        )
        == 0
    )
    assert detail(client, mid)["stage"] == "author_draft"


def test_draft_idempotence_and_role_membership_change_cannot_reuse_permissions(
    client, login, db, world
):
    login("author")
    body = {"request_id": request_id(), "title": "稳定请求的合成标题"}
    first = client.post(URL + "/drafts", json=body)
    assert first.status_code == 200
    assert client.post(URL + "/drafts", json=body).json() == first.json()
    assert client.post(URL + "/drafts", json={**body, "title": "其他标题"}).status_code == 409
    mid = first.json()["manuscript_id"]
    assert (
        db.scalar(
            select(func.count())
            .select_from(SubmissionWorkflow)
            .where(SubmissionWorkflow.manuscript_id == mid)
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(ActionReceipt)
            .where(ActionReceipt.user_id == world.users["author"].id)
        )
        == 1
    )
    del client.headers["X-CSRF-Token"]
    assert client.post(URL + "/drafts", json={"request_id": request_id()}).status_code == 403


def test_explicit_acknowledgment_and_stale_revision_required(client, login):
    login("author")
    data = fill(client, draft(client))
    p = prepare(client, data)
    body = {
        "request_id": request_id(),
        "expected_revision": data["revision"],
        "digest": p["digest"],
        "acknowledged": False,
    }
    assert (
        client.post(f"{URL}/proposals/{p['proposal_id']}/confirmations", json=body).status_code
        == 422
    )
    body["acknowledged"] = True
    body["expected_revision"] -= 1
    assert (
        client.post(f"{URL}/proposals/{p['proposal_id']}/confirmations", json=body).status_code
        == 409
    )
