"""Real DB/CAS tests of manual preview, immutable returns and scoped disagreement."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.domain.evaluation_models import EvaluationPackage, EvaluationReturn
from apps.api.publishing.domain.models import ActionReceipt
from apps.api.publishing.models import AuditEvent
from tests.api.test_dossier_chat import BODY, body, path
from tests.api.test_dossiers import create, metadata, save, upload


@pytest.fixture
def sample(client, login, monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path))
    login()
    item = save(client, create(client), data=metadata(), file=upload(raw=BODY.encode()))
    response = client.post(path(item), json=body(item))
    assert response.status_code == 200
    return item, response.json()


def root(item, answer):
    return f"/api/dossiers/{item['id']}/answers/{answer['id']}/evaluations"


def endpoint(item, pk):
    return f"/api/dossiers/{item['id']}/evaluations/{pk}"


def issue(client, item, answer, code="reader-a"):
    response = client.post(
        root(item, answer),
        json={
            "request_id": str(uuid4()),
            "content_digest": item["content_digest"],
            "evaluator_code": code,
        },
    )
    assert response.status_code == 200, response.text
    pk = response.json()["id"]
    packet = client.get(endpoint(item, pk) + "/file").json()
    return pk, packet


def evaluated(packet, verdict="supported"):
    result = deepcopy(packet)
    for claim in result["claims"]:
        claim["assessment"] = {
            "verdict": verdict,
            "note": "测试驱动模拟核对：已对照本版引文，记录实际评价。",
        }
    return result


def confirm_body(client, item, pk, packet, **changes):
    response = client.post(endpoint(item, pk) + "/preview", json={"packet": packet})
    assert response.status_code == 200, response.text
    detail = client.get(endpoint(item, pk)).json()
    return {
        "request_id": str(uuid4()),
        "packet": packet,
        "preview_digest": response.json()["digest"],
        "expected_return_id": detail["latest"]["id"] if detail["latest"] else None,
        "acknowledged": True,
        "acknowledged_claims": [c["id"] for c in packet["claims"]],
        **changes,
    }


def test_registered_package_return_replay_is_separate_from_source_and_decisions(client, db, sample):
    item, answer = sample
    before = client.get(f"/api/dossiers/{item['id']}").json()
    pk, packet = issue(client, item, answer)
    assert packet["schema"] == "claim-evaluation-package.v2" and packet["package_id"] == pk
    assert packet["evaluator_code"] == "reader-a"
    counts = {
        m: db.scalar(select(func.count()).select_from(m))
        for m in (EvaluationReturn, ActionReceipt, AuditEvent)
    }
    returned = evaluated(packet)
    data = confirm_body(client, item, pk, returned)
    assert counts == {m: db.scalar(select(func.count()).select_from(m)) for m in counts}
    saved = client.post(endpoint(item, pk) + "/confirm", json=data)
    assert saved.status_code == 200, saved.text
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "publishing.dossier_evaluation_returned",
            AuditEvent.entity_id == item["id"],
        )
    )
    assert audit.details["evidence_id"] == saved.json()["id"]
    assert client.post(endpoint(item, pk) + "/confirm", json=data).json() == saved.json()
    assert (
        db.scalar(
            select(func.count())
            .select_from(EvaluationReturn)
            .where(EvaluationReturn.package_id == pk)
        )
        == 1
    )
    assert client.get(f"/api/dossiers/{item['id']}").json() == before
    assert client.get(endpoint(item, pk) + "/file").json() == packet
    history = client.get(endpoint(item, pk) + "/returns?limit=1").json()
    assert history["items"][0]["assessments"] == {
        c["id"]: c["assessment"] for c in returned["claims"]
    }


@pytest.mark.parametrize("ack", [False, 1, "true", None])
def test_owner_must_explicitly_acknowledge(client, sample, ack):
    item, answer = sample
    pk, p = issue(client, item, answer)
    data = confirm_body(client, item, pk, evaluated(p), acknowledged=ack)
    assert client.post(endpoint(item, pk) + "/confirm", json=data).status_code == 422
    assert client.get(endpoint(item, pk)).json()["latest"] is None


@pytest.mark.parametrize(
    "change",
    [
        "text",
        "source",
        "quote",
        "id",
        "duplicate",
        "missing",
        "version_bool",
        "version_float",
        "assessment_extra",
        "note_null",
        "note_nul",
        "empty",
        "v1",
    ],
)
def test_untrusted_return_cannot_rewrite_material_or_identity(client, sample, change):
    item, answer = sample
    pk, p = issue(client, item, answer)
    r = evaluated(p)
    if change == "text":
        r["claims"][0]["text"] = "Forged assertion"
    elif change == "source":
        r["source"]["data"]["authors"][0]["name"] = "Another person"
    elif change == "quote":
        r["claims"][0]["citations"][0]["quote"] = "Made up quote"
    elif change == "id":
        r["package_id"] = str(uuid4())
    elif change == "duplicate":
        r["claims"].append(r["claims"][0])
    elif change == "missing":
        r["claims"].pop()
    elif change == "version_float":
        r["source"]["version_no"] = float(r["source"]["version_no"])
    elif change == "version_bool":
        r["source"]["version_no"] = True
    elif change == "assessment_extra":
        r["claims"][0]["assessment"]["actor"] = "forged"
    elif change == "note_null":
        r["claims"][0]["assessment"]["note"] = None
    elif change == "note_nul":
        r["claims"][0]["assessment"]["note"] = "实际核对理由\x00不允许"
    elif change == "empty":
        r = deepcopy(p)
    elif change == "v1":
        r["schema"] = "claim-evaluation-package.v1"
    response = client.post(endpoint(item, pk) + "/preview", json={"packet": r})
    assert response.status_code == 422, response.text
    assert client.get(endpoint(item, pk)).json()["latest"] is None


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor"])
def test_other_role_owner_cannot_read_preview_confirm_or_issue(client, login, sample, role):
    item, answer = sample
    pk, p = issue(client, item, answer)
    data = confirm_body(client, item, pk, evaluated(p))
    login(role)
    assert client.get(endpoint(item, pk)).status_code == 404
    assert client.get(endpoint(item, pk) + "/file").status_code == 404
    assert client.get(endpoint(item, pk) + "/returns").status_code == 404
    assert client.get(root(item, answer)).status_code == 404
    assert (
        client.post(endpoint(item, pk) + "/preview", json={"packet": evaluated(p)}).status_code
        == 404
    )
    assert client.post(endpoint(item, pk) + "/confirm", json=data).status_code == 404
    assert (
        client.post(
            root(item, answer),
            json={
                "request_id": str(uuid4()),
                "evaluator_code": "another",
                "content_digest": item["content_digest"],
            },
        ).status_code
        == 404
    )


def test_same_slot_not_double_counted_and_latest_return_replaces_only_its_vote(client, sample):
    item, answer = sample
    pa, a = issue(client, item, answer, "reader-a")
    pb, b = issue(client, item, answer, "reader-b")
    for pk, p, verdict in [(pa, a, "supported"), (pb, b, "unsupported")]:
        response = client.post(
            endpoint(item, pk) + "/confirm",
            json=confirm_body(client, item, pk, evaluated(p, verdict)),
        )
        assert response.status_code == 200, response.text
    summary = client.get(root(item, answer)).json()["summary"]
    assert summary["registered_slots"] == summary["confirmed_slots"] == 2
    assert summary["disputed_claims"] == len(a["claims"])
    assert all(c["supported"] == c["unsupported"] == 1 for c in summary["claims"])
    changed = evaluated(a, "uncertain")
    if len(changed["claims"]) > 1:
        changed["claims"][0]["assessment"] = {"verdict": None, "note": ""}
    response = client.post(
        endpoint(item, pa) + "/confirm", json=confirm_body(client, item, pa, changed)
    )
    assert response.status_code == 200, response.text
    summary = client.get(root(item, answer)).json()["summary"]
    assert summary["disputed_claims"] == 0 and summary["confirmed_slots"] == 2
    assert all(c["supported"] == 0 for c in summary["claims"])
    assert any(c["uncertain"] > 0 for c in summary["claims"])
    history = client.get(endpoint(item, pa) + "/returns?limit=1").json()
    assert history["next_cursor"] == 2
    assert (
        client.get(endpoint(item, pa) + "/returns?before=2&limit=1").json()["items"][0]["return_no"]
        == 1
    )


def test_digest_conflict_and_same_request_different_package_are_rejected(client, sample):
    item, answer = sample
    pk, p = issue(client, item, answer)
    data = confirm_body(client, item, pk, evaluated(p))
    url = endpoint(item, pk) + "/confirm"
    assert client.post(url, json={**data, "preview_digest": "f" * 64}).status_code == 409
    first = client.post(url, json=data)
    assert first.status_code == 200, first.text
    assert client.post(url, json={**data, "request_id": str(uuid4())}).status_code == 409
    other, packet = issue(client, item, answer, "reader-b")
    body = confirm_body(client, item, other, evaluated(packet))
    body["request_id"] = data["request_id"]
    assert client.post(endpoint(item, other) + "/confirm", json=body).status_code == 409


def test_historical_version_and_cross_dossier_binding(client, sample):
    item, answer = sample
    pk, p = issue(client, item, answer)
    changed = metadata()
    changed["title"] = "New version after package issued"
    newer = save(client, item, data=changed)
    assert newer["version_id"] != item["version_id"]
    detail = client.get(endpoint(item, pk)).json()
    assert detail["is_current"] is False and detail["version_id"] == item["version_id"]
    result = client.post(
        endpoint(item, pk) + "/confirm", json=confirm_body(client, item, pk, evaluated(p))
    )
    assert result.status_code == 200, result.text
    assert result.json()["version_id"] == item["version_id"]
    assert client.get(endpoint(create(client), pk)).status_code == 404
    assert client.get(f"/api/dossiers/{item['id']}").json()["version_id"] == newer["version_id"]


def test_issue_idempotency_and_duplicate_slot(client, sample):
    item, answer = sample
    data = {
        "request_id": str(uuid4()),
        "content_digest": item["content_digest"],
        "evaluator_code": "reader-a",
    }
    first = client.post(root(item, answer), json=data)
    assert first.status_code == 200, first.text
    assert client.post(root(item, answer), json=data).json() == first.json()
    assert (
        client.post(root(item, answer), json={**data, "request_id": str(uuid4())}).status_code
        == 409
    )
    second = client.post(path(item), json=body(item)).json()
    assert client.post(root(item, second), json=data).status_code == 409


def test_database_history_immutable_and_wrong_return_scope_refused(db, client, sample):
    item, answer = sample
    pk, p = issue(client, item, answer)
    saved = client.post(
        endpoint(item, pk) + "/confirm", json=confirm_body(client, item, pk, evaluated(p))
    )
    assert saved.status_code == 200, saved.text
    for model, identifier in [(EvaluationPackage, pk), (EvaluationReturn, saved.json()["id"])]:
        for statement in [
            update(model).where(model.id == identifier).values(content_digest="f" * 64),
            delete(model).where(model.id == identifier),
            text(f"TRUNCATE {model.__tablename__} CASCADE"),
        ]:
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(statement)
    row = db.get(EvaluationReturn, saved.json()["id"])
    values = {c.name: deepcopy(getattr(row, c.name)) for c in row.__table__.columns}
    values.update(id=str(uuid4()), version_id=str(uuid4()), return_no=2)
    with pytest.raises(DBAPIError), db.begin_nested():
        db.add(EvaluationReturn(**values))
        db.flush()


def test_corrupt_source_denies_replay(client, sample, monkeypatch):
    from fastapi import HTTPException

    from apps.api.publishing.domain import dossier_access

    item, answer = sample
    pk, p = issue(client, item, answer)
    data = confirm_body(client, item, pk, evaluated(p))
    assert client.post(endpoint(item, pk) + "/confirm", json=data).status_code == 200

    def bad(*a):
        raise HTTPException(409, "synthetic corrupt CAS")

    monkeypatch.setattr(dossier_access, "file_content", bad)
    assert client.post(endpoint(item, pk) + "/confirm", json=data).status_code == 409
    assert client.get(endpoint(item, pk) + "/file").status_code == 409


@pytest.mark.parametrize("case", ["missing", "duplicate", "foreign"])
def test_every_claim_must_be_explicitly_checked(client, sample, case):
    item, answer = sample
    pk, p = issue(client, item, answer)
    data = confirm_body(client, item, pk, evaluated(p))
    if case == "missing":
        data["acknowledged_claims"] = []
    elif case == "duplicate":
        data["acknowledged_claims"] = [p["claims"][0]["id"]] * (len(p["claims"]) + 1)
    else:
        data["acknowledged_claims"] = [str(uuid4())]
    response = client.post(endpoint(item, pk) + "/confirm", json=data)
    assert response.status_code == 422, response.text


def test_package_source_and_return_cannot_be_forged_in_database(db, client, sample):
    item, answer = sample
    pk, p = issue(client, item, answer)
    package = db.get(EvaluationPackage, pk)
    values = {c.name: deepcopy(getattr(package, c.name)) for c in package.__table__.columns}
    values.update(id=str(uuid4()), evaluator_code="forged-slot", claim_map={})
    values["packet_json"]["package_id"] = values["id"]
    values["packet_json"]["evaluator_code"] = "forged-slot"
    with pytest.raises(DBAPIError), db.begin_nested():
        db.add(EvaluationPackage(**values))
        db.flush()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from tests.api.test_dossiers import migrations

    with Operations.context(MigrationContext.configure(db.connection())):
        with pytest.raises(RuntimeError, match="Refusing to remove independent evaluation history"):
            migrations().get_revision("17d51aeb9408").module.downgrade()


def test_package_quota_and_same_code_cannot_inflate_summary(client, sample):
    item, answer = sample
    for i in range(10):
        issue(client, item, answer, f"reader-{i}")
    data = {
        "request_id": str(uuid4()),
        "evaluator_code": "reader-extra",
        "content_digest": item["content_digest"],
    }
    response = client.post(root(item, answer), json=data)
    assert response.status_code == 409, response.text
    summary = client.get(root(item, answer)).json()["summary"]
    assert (
        summary["registered_slots"] == 10
        and summary["confirmed_slots"] == 0
        and summary["disputed_claims"] == 0
    )
    assert all(c["unanswered"] == 10 for c in summary["claims"])
