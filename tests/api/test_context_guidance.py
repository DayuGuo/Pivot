from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.guidance_rules import publishing_rules
from apps.api.publishing.domain.models import ActionReceipt
from tests.api.test_dossier_chat import BODY
from tests.api.test_dossiers import create, metadata, save, upload


def test_library_empty_context_prioritizes_real_missing_fields_without_writes(client, login):
    login()
    item = create(client)
    response = client.get(f"/api/dossiers/{item['id']}/guidance")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["version_id"] == item["version_id"] and data["suggestions"][0]["id"] == "complete"
    assert "摘要" in data["suggestions"][0]["reason"] or "全文" in data["suggestions"][0]["reason"]


def test_library_guidance_updates_version_and_does_not_mutate(
    client, login, db, monkeypatch, tmp_path
):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    item = create(client)
    updated = save(client, item, data=metadata(), file=upload(raw=BODY.encode()))
    before = client.get(f"/api/dossiers/{item['id']}").json()
    count = db.scalar(select(func.count()).select_from(ActionReceipt))
    response = client.get(f"/api/dossiers/{item['id']}/guidance")
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["version_id"] == updated["version_id"] != item["version_id"]
    assert any(h["id"] == "methods" for h in out["suggestions"])
    assert all(h["id"] != "complete" for h in out["suggestions"])
    assert client.get(f"/api/dossiers/{item['id']}").json() == before
    assert db.scalar(select(func.count()).select_from(ActionReceipt)) == count


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_private_library_hints_do_not_grant_access(client, login, role):
    login()
    item = create(client)
    login(role)
    assert client.get(f"/api/dossiers/{item['id']}/guidance").status_code == 404


def test_role_rules_never_offer_staff_access_to_author_draft():
    state = {
        "stage": "author_revision",
        "is_owner": False,
        "missing": [],
        "editorial": {"mode": "staff"},
        "own_tasks": [],
    }
    assert publishing_rules("editor", state)[0]["id"] == "await-revision"
    state["is_owner"] = True
    state["missing"] = [{"field": "files.response", "message": "missing"}]
    assert publishing_rules("author", state)[0]["id"] == "revision-missing"
    state["missing"] = []
    assert publishing_rules("author", state)[0]["id"] == "revision"


def test_reviewer_rules_use_own_authorized_task_only():
    detail = {
        "stage": "peer_review",
        "is_owner": False,
        "review": {"mode": "reviewer", "can_edit_report": True},
    }
    assert publishing_rules("reviewer", detail)[0]["id"] == "review"
    detail["review"]["can_edit_report"] = False
    assert publishing_rules("reviewer", detail)[0]["id"] == "invitation"


def test_journal_hint_uses_actual_session_not_requested_role(client, login):
    login("author")
    out = client.get("/api/publishing/guidance").json()
    assert out["role"] == "author" and out["object_id"] is None
    assert client.get(f"/api/publishing/manuscripts/{uuid4()}/guidance").status_code == 404


def test_quality_hints_use_recorded_uncertainty_without_inventing_quality():
    from apps.api.publishing.domain.guidance_rules import dossier_rules

    detail = {
        "missing": [],
        "file": {"text": "合成全文"},
        "data": {"authors": []},
        "verified": False,
    }
    suggestions = dossier_rules(
        detail, withheld=[{"text": "原文不能支持该因果结论。"}], human_flagged=True
    )
    assert any(h["id"] == "human-evidence" for h in suggestions)
    assert any(h["id"] == "withheld" and "原文不能支持" in h["prompt"] for h in suggestions)
    clean = dossier_rules(detail, withheld=[], human_flagged=False)
    assert all(h["id"] not in {"withheld", "human-evidence"} for h in clean)
