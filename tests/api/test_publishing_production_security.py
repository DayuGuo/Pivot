"""Independent production security over real files, human approvals and local previews."""

import base64
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from apps.api.publishing.domain.models import Assignment, FileObject, HumanConfirmation
from apps.api.publishing.domain.production_models import (
    ProofPackage,
    ProofResponse,
    PublicationPreview,
)
from apps.api.publishing.models import Membership, User, now
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD
from tests.api.test_publishing_chat_security import call
from tests.api.test_publishing_chat_security import respond as model_respond
from tests.api.test_publishing_chat_security import scripted_provider as provider_fixture
from tests.api.test_publishing_decisions import (
    assess,
    closed_round,
    decide,
    recommend,
    submit_revision,
)
from tests.api.test_publishing_decisions import production as production_fixture
from tests.api.test_publishing_intake import URL, detail, request_id
from tests.api.test_publishing_peer_review import propose
from tests.api.test_publishing_production import (
    accepted,
    generate_preview,
    respond,
    send_proof,
    upload_proof,
)

pytestmark = pytest.mark.usefixtures("production")
SEND = {"declarations": {"metadata_reviewed": True, "proof_reviewed": True}}
PREVIEW = {"declarations": {"metadata_reviewed": True, "approved_proof_reviewed": True}}


@pytest.fixture
def production(db, world):
    return production_fixture.__wrapped__(db, world)


@pytest.fixture
def scripted_provider(monkeypatch):
    return provider_fixture.__wrapped__(monkeypatch)


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    root = tmp_path / "files"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


def count(db, model, mid):
    return db.scalar(select(func.count()).select_from(model).where(model.manuscript_id == mid))


def body_for_confirmation(before, proposal):
    return {
        "request_id": request_id(),
        "expected_revision": before["revision"],
        "digest": proposal["digest"],
        "acknowledged": True,
    }


def post_chat(client, mid, message="概述本人当前制作工作", rid=None):
    return client.post(
        URL + "/chat",
        json={
            "request_id": rid or request_id(),
            "message": message,
            "context": {"scope": "case", "manuscript_id": mid},
        },
    )


def change_producer_to_summary_only_chief(db, world, mid):
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == "production")
        .values(ends_at=now())
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(Membership)
        .where(Membership.user_id == world.users["production_editor"].id)
        .values(role="chief_editor")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.expire_all()


def test_private_proof_upload_receipt_cannot_restore_file_metadata_after_permission_loss(
    client, login, db, world
):
    mid = accepted(client, login, world)
    secret_name = "private-production-" + request_id() + ".txt"
    body = {
        "request_id": request_id(),
        "expected_revision": detail(client, mid)["revision"],
        "file": {
            "filename": secret_name,
            "purpose": "proof",
            "content_base64": base64.b64encode("尚未交给作者的私人校样草稿。".encode()).decode(),
        },
    }
    url = f"{URL}/manuscripts/{mid}/proof-files"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    assert client.post(url, json=body).json() == first.json()
    change_producer_to_summary_only_chief(db, world, mid)
    assert detail(client, mid)["production"] is None
    assert client.get(first.json()["draft_file"]["download_url"]).status_code == 404
    replay = client.post(url, json=body)
    assert replay.status_code in {403, 404}, replay.text
    assert secret_name not in replay.text


def test_production_dto_and_file_tools_only_expose_accepted_manuscript_not_old_sources(
    client, login, db, world, scripted_provider
):
    mid = closed_round(client, login, world)
    old = detail(client, mid)["version"]
    recommend(client, login, mid)
    decide(client, login, mid)
    submit_revision(client, login, mid)
    assess(client, login, mid)
    recommend(client, login, mid, "accept")
    decide(client, login, mid, "accept")
    login("author")
    author = detail(client, mid)
    accepted_files = author["version"]["files"]
    accepted_version = author["version"]["id"]
    login("production_editor")
    data = detail(client, mid)
    assert data["version"] is None and data["field_sources"] == {}
    assert data["review"] is data["editorial"] is data["staff_review"] is None
    assert [version["id"] for version in data["versions"]] == [accepted_version]
    encoded = json.dumps(data, ensure_ascii=False)
    assert old["id"] not in encoded and "declarations" not in encoded
    assert "linked_user_id" not in encoded and "author@synthetic.test" not in encoded
    materials = data["production"]["accepted_materials"]
    assert len(materials) == 1 and materials[0]["purpose"] == "manuscript"
    for file in [*old["files"], *accepted_files]:
        response = client.get(file["download_url"])
        assert response.status_code == (200 if file["id"] == materials[0]["id"] else 404)
    private_file = next(file for file in accepted_files if file["purpose"] == "response")
    provider = scripted_provider([[call("read_current_file", {"file_id": private_file["id"]})]])
    assert post_chat(client, mid, "读取当前稿件的源文件").status_code == 404
    assert len(provider.calls) == 1
    assert count(db, ProofPackage, mid) == 0


@pytest.mark.parametrize("gate", ["send", "author_approve", "preview"])
def test_same_length_cas_corruption_blocks_each_independent_proof_confirmation(
    client, login, db, world, storage, gate
):
    mid = accepted(client, login, world)
    uploaded = upload_proof(client, mid)
    file = uploaded["draft_file"]
    if gate == "send":
        before, proposal = propose(client, mid, "send_proof", SEND)
    else:
        sent = send_proof(client, mid)
        if gate == "author_approve":
            login("author")
            before, proposal = propose(
                client,
                mid,
                "confirm_proof",
                {
                    "package_id": sent["production"]["active_package_id"],
                    "outcome": "approve",
                    "declarations": {"proof_reviewed": True},
                },
            )
        else:
            respond(client, login, mid)
            login("production_editor")
            before, proposal = propose(client, mid, "prepare_local_preview", PREVIEW)
    original_counts = {
        model: count(db, model, mid)
        for model in (HumanConfirmation, ProofPackage, ProofResponse, PublicationPreview)
    }
    blob = db.get(FileObject, file["id"])
    Path(storage / blob.storage_key).write_bytes(b"x" * blob.byte_size)
    response = client.post(
        f"{URL}/proposals/{proposal['proposal_id']}/confirmations",
        json=body_for_confirmation(before, proposal),
    )
    assert response.status_code == 409, response.text
    for model, previous in original_counts.items():
        assert count(db, model, mid) == previous
    assert detail(client, mid)["stage"] == before["stage"]


def test_private_proof_binding_is_owner_and_manuscript_scoped_even_with_deduplicated_files(
    client, login, world
):
    first = accepted(client, login, world)
    uploaded = upload_proof(client, first)
    for role in ("author", "editor", "chief_editor", "reviewer"):
        login(role)
        assert client.get(uploaded["draft_file"]["download_url"]).status_code == 404
        assert "draft_file" not in (detail(client, first).get("production") or {})
    second = accepted(client, login, world)
    response = client.get(f"{URL}/manuscripts/{second}/proof-files/{uploaded['draft_file']['id']}")
    assert response.status_code == 404
    # Shared CAS bytes gain no cross-manuscript grant until explicitly bound there.
    same_bytes = upload_proof(client, second)
    assert same_bytes["draft_file"]["id"] == uploaded["draft_file"]["id"]
    assert client.get(same_bytes["draft_file"]["download_url"]).status_code == 200


def test_proof_response_is_only_by_current_author_and_cannot_target_other_manuscript_package(
    client, login, world
):
    first = accepted(client, login, world)
    upload_proof(client, first)
    one = send_proof(client, first)["production"]["active_package_id"]
    second = accepted(client, login, world)
    upload_proof(client, second, "另一篇稿件的实际校样正文。")
    two = send_proof(client, second)["production"]["active_package_id"]
    for role in ("production_editor", "editor", "chief_editor", "reviewer"):
        login(role)
        response = client.post(
            f"{URL}/manuscripts/{second}/proposals",
            json={
                "request_id": request_id(),
                "expected_revision": detail(client, second)["revision"],
                "action_type": "confirm_proof",
                "data": {
                    "package_id": two,
                    "outcome": "approve",
                    "declarations": {"proof_reviewed": True},
                },
            },
        )
        assert response.status_code in {403, 404}, response.text
    login("author")
    response = client.post(
        f"{URL}/manuscripts/{second}/proposals",
        json={
            "request_id": request_id(),
            "expected_revision": detail(client, second)["revision"],
            "action_type": "confirm_proof",
            "data": {
                "package_id": one,
                "outcome": "approve",
                "declarations": {"proof_reviewed": True},
            },
        },
    )
    assert response.status_code == 409, response.text


def test_authenticated_preview_and_package_bytes_are_not_public_or_reviewer_access(
    client, login, db, world, storage
):
    mid = accepted(client, login, world)
    uploaded = upload_proof(
        client, mid, "<script>window.shouldNeverRun=1</script>\n合成本地预览正文。"
    )
    package = send_proof(client, mid)["production"]["packages"][0]
    respond(client, login, mid)
    result = generate_preview(client, login, mid)
    url = f"{URL}/previews/{result['production']['preview']['id']}"
    assert client.get(url).json()["text"].startswith("<script>")
    assert client.get(url).json()["formally_published"] is False
    login("reviewer")
    for endpoint in (url, package["file"]["download_url"]):
        assert client.get(endpoint).status_code == 404
    outsider = User(
        email=f"other-chief-{request_id()}@synthetic.test",
        name="其他期刊主编",
        password_hash=hash_password(PASSWORD),
    )
    db.add(outsider)
    db.flush()
    db.add(Membership(user_id=outsider.id, journal_id=world.other_journal.id, role="chief_editor"))
    db.commit()
    world.users["outsider"] = outsider
    login("outsider")
    assert client.get(url).status_code == 404
    assert client.get(package["file"]["download_url"]).status_code == 404
    client.cookies.clear()
    for endpoint in (url, package["file"]["download_url"], uploaded["draft_file"]["download_url"]):
        assert client.get(endpoint).status_code == 401
    login("author")
    assert client.get(url).status_code == 200
    blob = db.get(FileObject, uploaded["draft_file"]["id"])
    Path(storage / blob.storage_key).unlink()
    assert client.get(url).status_code == 409
    assert client.get(package["file"]["download_url"]).status_code == 409


def test_production_snapshots_receipts_and_model_history_reauthorize_after_role_loss(
    client, login, db, world, scripted_provider
):
    mid = accepted(client, login, world)
    upload_proof(client, mid, name="unshared-private-proof.txt")
    rid = request_id()
    scripted_provider([[model_respond("PRIVATE-PROOF-HISTORY-CANARY")]])
    assert post_chat(client, mid, rid=rid).status_code == 200
    before, proposal = propose(client, mid, "send_proof", SEND)
    body = body_for_confirmation(before, proposal)
    confirm_url = f"{URL}/proposals/{proposal['proposal_id']}/confirmations"
    assert client.post(confirm_url, json=body).status_code == 200
    change_producer_to_summary_only_chief(db, world, mid)
    assert detail(client, mid)["production"] is None
    assert client.get(f"{URL}/proposals/{proposal['proposal_id']}").status_code == 404
    assert client.post(confirm_url, json=body).status_code == 404
    assert client.get(URL + "/chat?manuscript_id=" + mid).json()["messages"] == []
    assert post_chat(client, mid, rid=rid).status_code == 403


def test_model_tools_cannot_assert_proof_declarations_confirm_or_publish(
    client, login, db, world, scripted_provider
):
    mid = accepted(client, login, world)
    upload_proof(client, mid)
    before = count(db, HumanConfirmation, mid)

    def forbidden_call(messages, tools):
        names = {tool["function"]["name"] for tool in tools}
        assert names.isdisjoint(
            {"send_proof", "confirm_proof", "prepare_local_preview", "publish", "send_email"}
        )
        assert "declarations" not in json.dumps(tools)
        return [call("send_proof", SEND)]

    scripted_provider([forbidden_call])
    response = post_chat(client, mid, "替我确认已读校样并发布")
    assert response.status_code == 502, response.text
    assert count(db, HumanConfirmation, mid) == before
    assert count(db, ProofPackage, mid) == 0
    assert count(db, PublicationPreview, mid) == 0
