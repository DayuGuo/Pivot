"""Human evidence feedback is separate from model output and publication authority."""

from uuid import uuid4

import pytest

from tests.api.test_dossier_chat import BODY, body, path
from tests.api.test_dossiers import create, metadata, save, upload


@pytest.fixture
def reviewed_answer(client, login, monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "mock")
    login()
    item = save(client, create(client), data=metadata(), file=upload(raw=BODY.encode()))
    answer = client.post(path(item), json=body(item))
    assert answer.status_code == 200, answer.text
    return item, answer.json()


def target(item, answer):
    return f"/api/dossiers/{item['id']}/answers/{answer['id']}/claims/claims/0/reviews"


def payload(state, **changes):
    return {
        "request_id": str(uuid4()),
        "content_digest": state["content_digest"],
        "claim_digest": state["claim_digest"],
        "expected_review_id": state["latest_id"],
        "verdict": "unsupported",
        "note": "原句不能支持此结论，需人工重新核对。",
        "acknowledged": True,
        **changes,
    }


def test_human_feedback_persists_without_rewriting_answer_or_confirming_dossier(
    client, reviewed_answer
):
    item, answer = reviewed_answer
    url = target(item, answer)
    before = client.get(f"/api/dossiers/{item['id']}").json()
    read = client.get(url)
    assert read.status_code == 200, read.text
    state = read.json()
    assert state["items"] == []
    data = payload(state)
    saved = client.post(url, json=data)
    assert saved.status_code == 200, saved.text
    assert client.post(url, json=data).json() == saved.json()
    history = client.get(url).json()
    assert len(history["items"]) == 1 and history["items"][0]["verdict"] == "unsupported"
    after = client.get(f"/api/dossiers/{item['id']}").json()
    assert after == before
    assert after["verified"] is False


def test_human_feedback_conflict_and_explicit_acknowledgement(client, reviewed_answer):
    item, answer = reviewed_answer
    url = target(item, answer)
    state = client.get(url).json()
    assert client.post(url, json=payload(state, acknowledged=False)).status_code == 422
    one = client.post(url, json=payload(state))
    assert one.status_code == 200
    assert client.post(url, json=payload(state, verdict="supported")).status_code == 409
    latest = client.get(url).json()
    two = client.post(url, json=payload(latest, verdict="uncertain"))
    assert two.status_code == 200
    assert [r["review_no"] for r in client.get(url).json()["items"]] == [2, 1]


@pytest.mark.parametrize(
    "changes",
    [
        {"claim_digest": "f" * 64},
        {"content_digest": "e" * 64},
        {"expected_review_id": str(uuid4())},
    ],
)
def test_wrong_snapshot_or_prior_review_cannot_be_saved(client, reviewed_answer, changes):
    item, answer = reviewed_answer
    url = target(item, answer)
    state = client.get(url).json()
    assert client.post(url, json=payload(state, **changes)).status_code == 409
    assert client.get(url).json()["items"] == []


@pytest.mark.parametrize("ack", [False, 1, "true", None])
def test_feedback_requires_real_boolean_acknowledgement(client, reviewed_answer, ack):
    item, answer = reviewed_answer
    url = target(item, answer)
    state = client.get(url).json()
    assert client.post(url, json=payload(state, acknowledged=ack)).status_code == 422


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_other_roles_and_owners_cannot_read_or_replay_feedback(
    client, login, reviewed_answer, role
):
    item, answer = reviewed_answer
    url = target(item, answer)
    state = client.get(url).json()
    data = payload(state)
    assert client.post(url, json=data).status_code == 200
    login(role)
    assert client.get(url).status_code == 404
    assert client.post(url, json=data).status_code == 404


def test_same_request_id_cannot_be_replayed_for_identical_claim_in_different_answer(
    client, reviewed_answer
):
    item, answer = reviewed_answer
    url = target(item, answer)
    data = payload(client.get(url).json())
    assert client.post(url, json=data).status_code == 200
    second = client.post(path(item), json=body(item)).json()
    other = target(item, second)
    assert client.post(other, json=data).status_code == 409
    assert client.get(other).json()["items"] == []


def test_history_is_bounded_and_feedback_is_valid_for_exact_historical_version(
    client, reviewed_answer
):
    item, answer = reviewed_answer
    url = target(item, answer)
    for _ in range(3):
        assert client.post(url, json=payload(client.get(url).json())).status_code == 200
    first = client.get(url + "?limit=1").json()
    assert first["items"][0]["review_no"] == 3 and first["next_cursor"] == 3
    second = client.get(url + "?limit=1&before=3").json()
    assert second["items"][0]["review_no"] == 2
    changed = metadata()
    changed["title"] = "New immutable dossier version"
    newer = save(client, item, data=changed)
    assert newer["version_id"] != item["version_id"]
    assert (
        client.post(url, json=payload(client.get(url).json(), verdict="supported")).status_code
        == 200
    )
    assert client.get(f"/api/dossiers/{item['id']}").json()["version_id"] == newer["version_id"]


def test_feedback_rows_are_immutable_and_reject_source_forgery(db, client, reviewed_answer):
    from copy import deepcopy

    from sqlalchemy import delete, select, text, update
    from sqlalchemy.exc import DBAPIError

    from apps.api.publishing.domain.claim_review_models import ClaimReview

    item, answer = reviewed_answer
    url = target(item, answer)
    response = client.post(url, json=payload(client.get(url).json()))
    assert response.status_code == 200
    row = db.get(ClaimReview, response.json()["id"])
    values = {c.name: deepcopy(getattr(row, c.name)) for c in ClaimReview.__table__.columns}
    for command in [
        update(ClaimReview).where(ClaimReview.id == row.id).values(verdict="supported"),
        delete(ClaimReview).where(ClaimReview.id == row.id),
        text("TRUNCATE publishing_claim_reviews"),
    ]:
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(command)
            db.flush()
    values.update(id=str(uuid4()), review_no=2, claim_json={"text": "forged source"})
    with pytest.raises(DBAPIError), db.begin_nested():
        db.add(ClaimReview(**values))
        db.flush()
    assert db.scalar(select(ClaimReview.id).where(ClaimReview.id == row.id)) == row.id


def test_summary_uses_latest_feedback_and_never_scores_mock_as_real_model(client, reviewed_answer):
    item, answer = reviewed_answer
    url = target(item, answer)
    for verdict in ["supported", "unsupported"]:
        assert (
            client.post(url, json=payload(client.get(url).json(), verdict=verdict)).status_code
            == 200
        )
    out = client.get(f"/api/dossiers/{item['id']}/answers/{answer['id']}/review-summary").json()
    assert out["metrics"]["reviewed_claims"] == 1 and out["metrics"]["model_unchecked"] == 1
    assert out["metrics"]["comparable"] == 0 and out["metrics"]["agreement_rate"] is None
    assert out["reviews"][0]["review_no"] == 2 and out["human_feedback_is_not_publication_approval"]


def test_feedback_metrics_keep_unknown_and_uncertain_out_of_denominator():
    from types import SimpleNamespace

    from apps.api.publishing.domain.claim_review_metrics import summarize

    values = [
        ("supported", "unsupported"),
        ("insufficient", "supported"),
        ("contradicted", "unsupported"),
        ("supported", "uncertain"),
        ("not_checked", "supported"),
    ]
    rows = [
        SimpleNamespace(
            claim_json={
                "support": {
                    "status": m,
                    "method": "mock" if m == "not_checked" else "ai_context_check",
                }
            },
            verdict=h,
        )
        for m, h in values
    ]
    result = summarize(rows)
    assert (
        result["comparable"] == 3 and result["agreement"] == 1 and result["agreement_rate"] == 1 / 3
    )
    assert (
        result["model_adopted_human_unsupported"] == 1
        and result["model_withheld_human_supported"] == 1
    )
    assert result["model_unchecked"] == 1 and result["human_uncertain"] == 1


def test_feedback_cannot_be_moved_to_another_dossier_or_missing_claim(client, reviewed_answer):
    item, answer = reviewed_answer
    state = client.get(target(item, answer)).json()
    other = create(client)
    assert client.get(target(other, answer)).status_code == 404
    assert client.post(target(other, answer), json=payload(state)).status_code == 404
    assert client.get(target(item, answer).replace("/claims/0/", "/claims/5/")).status_code == 404
    assert (
        client.get(
            target(item, answer).replace("/claims/claims/", "/claims/untrusted/")
        ).status_code
        == 422
    )


def test_feedback_replay_rechecks_current_source_and_refuses_destructive_downgrade(
    client, db, reviewed_answer, monkeypatch
):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from fastapi import HTTPException

    from apps.api.publishing.domain import claim_reviews
    from tests.api.test_dossiers import migrations

    item, answer = reviewed_answer
    url = target(item, answer)
    data = payload(client.get(url).json())
    assert client.post(url, json=data).status_code == 200
    with Operations.context(MigrationContext.configure(db.connection())):
        with pytest.raises(RuntimeError, match="Refusing to remove human claim review history"):
            migrations().get_revision("16c40fda8397").module.downgrade()

    def corrupt(*args):
        raise HTTPException(409, "测试原件已损坏")

    monkeypatch.setattr(claim_reviews.access, "file_content", corrupt)
    assert client.get(url).status_code == 409
    assert client.post(url, json=data).status_code == 409


def test_large_archival_evidence_is_rejected_clearly_before_database_snapshot_limit(
    client, db, reviewed_answer
):
    from copy import deepcopy

    from apps.api.publishing.domain.dossier_chat_models import DossierAnswer
    from apps.api.publishing.domain.dossier_models import DossierTurn

    item, _ = reviewed_answer
    original_text = BODY * 90
    latest = save(client, item, data=metadata(), file=upload(raw=original_text.encode()))
    response = client.post(path(latest), json=body(latest))
    assert response.status_code == 200
    message = response.json()
    payload_json = deepcopy(db.get(DossierAnswer, message["id"]).result_json)
    payload_json["claims"][0]["citations"][0]["source_text"] = original_text
    turn = db.get(DossierTurn, message["id"])
    archived_id = str(uuid4())
    db.add(
        DossierTurn(
            id=archived_id,
            dossier_id=turn.dossier_id,
            journal_id=turn.journal_id,
            version_id=turn.version_id,
            user_id=turn.user_id,
            question="Synthetic archived full-context evidence; not a live model result.",
            answer="Synthetic archived answer for capacity regression.",
        )
    )
    db.flush()
    db.add(
        DossierAnswer(
            id=archived_id,
            dossier_id=turn.dossier_id,
            journal_id=turn.journal_id,
            version_id=turn.version_id,
            result_json=payload_json,
        )
    )
    db.flush()
    url = target(latest, {"id": archived_id})
    # Seal the test fixture's savepoint; the API's rejected action rolls back
    # its own transaction while the outer fixture still rolls everything back.
    db.commit()
    state = client.get(url)
    assert state.status_code == 200
    refused = client.post(url, json=payload(state.json()))
    assert refused.status_code == 413, refused.text
    assert client.get(url).json()["items"] == []


@pytest.mark.parametrize("note", ["     ", "abc\x00def"])
def test_invalid_review_notes_fail_before_database_write(client, reviewed_answer, note):
    item, answer = reviewed_answer
    url = target(item, answer)
    assert client.post(url, json=payload(client.get(url).json(), note=note)).status_code == 422
    assert client.get(url).json()["items"] == []
