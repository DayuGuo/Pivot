"""Actual proof packages, author correction cycles and private local previews."""

import base64

import pytest
from sqlalchemy import func, select

from apps.api.publishing.domain.models import SubmissionWorkflow, VersionFile
from apps.api.publishing.domain.production_models import (
    ProofPackage,
    ProofResponse,
    PublicationPreview,
)
from apps.api.publishing.models import Manuscript
from tests.api.test_publishing_decisions import closed_round, decide, recommend
from tests.api.test_publishing_decisions import production as production
from tests.api.test_publishing_intake import URL, detail, request_id
from tests.api.test_publishing_peer_review import propose
from tests.api.test_publishing_screening import confirm

pytestmark = pytest.mark.usefixtures("production")


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def accepted(client, login, world):
    mid = closed_round(client, login, world)
    recommend(client, login, mid, "accept")
    decide(client, login, mid, "accept")
    login("production_editor")
    return mid


def upload_proof(client, mid, text="合成校样正文。仅用于本地出版操作系统验收。", name="proof.txt"):
    data = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proof-files",
        json={
            "request_id": request_id(),
            "expected_revision": data["revision"],
            "file": {
                "filename": name,
                "purpose": "proof",
                "content_base64": base64.b64encode(text.encode()).decode(),
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def send_proof(client, mid):
    before, proposal = propose(
        client,
        mid,
        "send_proof",
        {
            "declarations": {"metadata_reviewed": True, "proof_reviewed": True},
        },
    )
    confirm(client, before, proposal)
    return detail(client, mid)


def respond(client, login, mid, outcome="approve"):
    login("author")
    data = detail(client, mid)
    before, proposal = propose(
        client,
        mid,
        "confirm_proof",
        {
            "package_id": data["production"]["active_package_id"],
            "outcome": outcome,
            "notes": "请更正正文第二段中的合成测试说明，保留录用时的结构化元数据。"
            if outcome == "request_corrections"
            else "作者本人已阅读并核对本包实际校样。",
            "declarations": {"proof_reviewed": True},
        },
    )
    confirm(client, before, proposal)
    return detail(client, mid)


def generate_preview(client, login, mid):
    login("production_editor")
    before, proposal = propose(
        client,
        mid,
        "prepare_local_preview",
        {
            "declarations": {"metadata_reviewed": True, "approved_proof_reviewed": True},
        },
    )
    confirm(client, before, proposal)
    return detail(client, mid)


def test_actual_private_proof_author_approval_and_authenticated_local_preview(
    client, login, db, world
):
    mid = accepted(client, login, world)
    current = detail(client, mid)
    assert current["version"] is None and current["editorial"] is None
    metadata = current["production"]["metadata_snapshot"]
    assert "email" not in str(metadata) and "declarations" not in metadata
    assert len(current["production"]["accepted_materials"]) == 1
    count = db.scalar(
        select(func.count()).select_from(VersionFile).where(VersionFile.manuscript_id == mid)
    )
    text = "<script>window.fakePublication=true</script>\n合成校样只作为安全文本，不执行HTML。"
    uploaded = upload_proof(client, mid, text)
    assert client.get(uploaded["draft_file"]["download_url"]).content.decode() == text
    assert not db.scalar(select(ProofPackage).where(ProofPackage.manuscript_id == mid))
    login("author")
    assert "draft_file" not in detail(client, mid)["production"]
    assert client.get(uploaded["draft_file"]["download_url"]).status_code == 404
    login("production_editor")
    delivered = send_proof(client, mid)
    assert delivered["stage"] == "author_proof"
    assert (
        db.scalar(
            select(func.count()).select_from(VersionFile).where(VersionFile.manuscript_id == mid)
        )
        == count
    )
    login("author")
    package = detail(client, mid)["production"]["packages"][0]
    assert client.get(package["file"]["download_url"]).content.decode() == text
    approved = respond(client, login, mid)
    assert approved["stage"] == "preview_confirmation"
    assert not db.scalar(select(PublicationPreview).where(PublicationPreview.manuscript_id == mid))
    result = generate_preview(client, login, mid)
    assert result["stage"] == "preview_ready"
    preview_id = result["production"]["preview"]["id"]
    preview = client.get(f"{URL}/previews/{preview_id}").json()
    assert preview["text"] == text and preview["metadata_snapshot"] == metadata
    assert preview["local_only"] and not preview["formally_published"]
    assert preview["manuscript_status"] == db.get(Manuscript, mid).status == "accepted"
    assert db.get(SubmissionWorkflow, mid).accepted_version_id == preview["accepted_version_id"]
    assert "PRIVATE" not in str(preview)
    login("reviewer")
    assert client.get(f"{URL}/previews/{preview_id}").status_code == 404
    assert client.get(package["file"]["download_url"]).status_code == 404
    login("author")
    assert client.get(f"{URL}/previews/{preview_id}").status_code == 200


def test_author_corrections_preserve_first_package_and_require_new_actual_bytes(
    client, login, db, world
):
    mid = accepted(client, login, world)
    upload_proof(client, mid, "第一版合成校样，需要更正的测试说明。")
    first = send_proof(client, mid)["production"]["active_package_id"]
    respond(client, login, mid, "request_corrections")
    login("production_editor")
    current = detail(client, mid)
    response = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "action_type": "send_proof",
            "data": {"declarations": {"metadata_reviewed": True, "proof_reviewed": True}},
        },
    )
    assert response.status_code == 422
    upload_proof(client, mid, "第二版合成校样，已更正测试说明而不改冻结元数据。", "corrected.txt")
    delivered = send_proof(client, mid)
    second = delivered["production"]["active_package_id"]
    assert first != second
    assert [p["package_no"] for p in delivered["production"]["packages"]] == [1, 2]
    assert delivered["production"]["packages"][0]["response"]["outcome"] == "request_corrections"
    login("author")
    current = detail(client, mid)
    wrong = client.post(
        f"{URL}/manuscripts/{mid}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": current["revision"],
            "action_type": "confirm_proof",
            "data": {
                "package_id": first,
                "outcome": "approve",
                "notes": "",
                "declarations": {"proof_reviewed": True},
            },
        },
    )
    assert wrong.status_code == 409
    respond(client, login, mid)
    preview = generate_preview(client, login, mid)
    assert (
        db.scalar(
            select(func.count()).select_from(ProofPackage).where(ProofPackage.manuscript_id == mid)
        )
        == 2
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(ProofResponse)
            .where(ProofResponse.manuscript_id == mid)
        )
        == 2
    )
    actual = client.get(f"{URL}/previews/{preview['production']['preview']['id']}").json()
    assert actual["package_id"] == second and actual["file"]["filename"] == "corrected.txt"


def test_proof_human_confirmation_uuid_retry_creates_one_package(client, login, db, world):
    mid = accepted(client, login, world)
    upload_proof(client, mid)
    before, proposal = propose(
        client,
        mid,
        "send_proof",
        {"declarations": {"metadata_reviewed": True, "proof_reviewed": True}},
    )
    body = {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }
    url = f"{URL}/proposals/{proposal['proposal_id']}/confirmations"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    assert client.post(url, json=body).json() == first.json()
    assert (
        db.scalar(
            select(func.count()).select_from(ProofPackage).where(ProofPackage.manuscript_id == mid)
        )
        == 1
    )


def test_upload_receipt_restores_only_current_authorized_private_binding(client, login, world):
    mid = accepted(client, login, world)
    current = detail(client, mid)
    body = {
        "request_id": request_id(),
        "expected_revision": current["revision"],
        "file": {
            "filename": "private-proof.txt",
            "purpose": "proof",
            "content_base64": base64.b64encode("第一份私有校样。".encode()).decode(),
        },
    }
    url = f"{URL}/manuscripts/{mid}/proof-files"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    assert client.post(url, json=body).json() == first.json()
    upload_proof(client, mid, "第二份私有校样替换当前待审核草稿。", "current.txt")
    assert client.post(url, json=body).status_code == 404
