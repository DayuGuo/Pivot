"""Private staff dossiers: real PostgreSQL, immutable snapshots and actual UTF8 CAS.

Every fixture is synthetic. A dossier is never a submission or an editorial decision.
"""

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import DBAPIError

from apps.api.publishing.db import engine
from apps.api.publishing.domain import chat
from apps.api.publishing.domain.decision_models import EditorialDecision
from apps.api.publishing.domain.dossiers import Dossier, DossierCheck, DossierTurn, DossierVersion
from apps.api.publishing.domain.models import ActionReceipt, FileObject, SubmissionWorkflow
from apps.api.publishing.models import AuditEvent, Base, Manuscript, Membership, User
from apps.api.publishing.security import hash_password
from tests.api.conftest import PASSWORD

URL = "/api/dossiers"
BODY = "# 合成全文\n这段正文独立于摘要保存，不含真实保密稿件。\n" * 60
ROOT = Path(__file__).resolve().parents[2]


def migrations():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "infrastructure/migrations"))
    return ScriptDirectory.from_config(config)


def rid():
    return str(uuid4())


def creation(**changes):
    return {
        "request_id": rid(),
        "title": "合成资料包测试",
        "source_kind": "synthetic",
        "source_note": "完全合成，仅用于本地权限与持久化测试。",
        "authorized_material": True,
        **changes,
    }


def metadata(**changes):
    return {
        "title": "合成研究资料包",
        "abstract": "这是一段独立的合成摘要，验证资料包保存、作者快照、全文及人工核对，不涉及真实研究参与者或保密材料。",
        "language": "zh",
        "keywords": ["合成资料", "版本核对"],
        "authors": [
            {
                "name": "合成作者甲",
                "email": "author@synthetic.test",
                "orcid": "0000-0002-1825-0097",
                "affiliations": ["合成研究机构"],
                "corresponding": True,
                "contributions": [],
                "source_note": "作者资料来自完全合成的测试记录。",
            },
            {
                "name": "合成作者乙",
                "email": "second@synthetic.test",
                "orcid": None,
                "affiliations": ["第二合成机构"],
                "corresponding": False,
                "contributions": [],
                "source_note": "第二作者亦为合成记录。",
            },
        ],
        "source_kind": "synthetic",
        "source_note": "完整元数据与全文均为本地授权合成资料。",
        **changes,
    }


def upload(filename="synthetic.md", raw=None):
    return {
        "filename": filename,
        "content_base64": base64.b64encode(BODY.encode() if raw is None else raw).decode(),
    }


def detail(client, dossier_id, version_id=None):
    path = f"{URL}/{dossier_id}"
    if version_id:
        path += f"/versions/{version_id}"
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def create(client, **changes):
    response = client.post(URL, json=creation(**changes))
    assert response.status_code == 200, response.text
    return detail(client, response.json()["dossier_id"])


def save_body(snapshot, data=None, file=None):
    return {
        "request_id": rid(),
        "expected_revision": snapshot["revision"],
        "data": metadata() if data is None else data,
        "file": file,
    }


def save(client, snapshot, data=None, file=None):
    response = client.post(f"{URL}/{snapshot['id']}/versions", json=save_body(snapshot, data, file))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["dossier_id"] == snapshot["id"]
    return detail(client, snapshot["id"], result["version_id"])


def confirm_body(snapshot, **changes):
    return {
        "request_id": rid(),
        "expected_revision": snapshot["revision"],
        "version_id": snapshot["version_id"],
        "digest": snapshot["content_digest"],
        "acknowledged": True,
        **changes,
    }


def confirm(client, snapshot, **changes):
    return client.post(f"{URL}/{snapshot['id']}/confirm", json=confirm_body(snapshot, **changes))


def count(db, model, **filters):
    return db.scalar(select(func.count()).select_from(model).filter_by(**filters))


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    root = tmp_path / "private-dossier-files"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


@pytest.fixture
def other_editor(db, world):
    user = User(
        email=f"other-editor-{rid()}@publishing.test",
        name="跨刊合成编辑",
        password_hash=hash_password(PASSWORD),
    )
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, journal_id=world.other_journal.id, role="editor"))
    db.commit()
    world.users["other_editor"] = user
    return user


@pytest.mark.parametrize("role", ["editor", "chief_editor"])
def test_staff_create_save_confirm_persists_without_formal_workflow(
    client, login, db, world, storage, role
):
    login(role)
    before = {m: count(db, m) for m in (Manuscript, SubmissionWorkflow, EditorialDecision)}
    initial = create(client)
    assert initial["verified"] is False and initial["verification"] is None
    assert initial["file"] is None and initial["missing"]
    saved = save(client, initial, file=upload())
    assert saved["missing"] == [] and saved["data"] == metadata()
    assert saved["file"]["text"] == BODY
    assert saved["file"]["sha256"] == hashlib.sha256(BODY.encode()).hexdigest()
    assert saved["file"]["byte_size"] == len(BODY.encode())
    download = client.get(saved["file"]["download_url"])
    assert download.status_code == 200 and download.content == BODY.encode()
    assert "attachment" in download.headers["content-disposition"]
    assert confirm(client, saved).status_code == 200
    db.expire_all()
    checked = detail(client, initial["id"])
    assert checked["verified"] is True
    assert checked["verification"]["by"] == world.users[role].id
    assert checked["verification"]["id"] and checked["verification"]["at"]
    row = db.get(DossierVersion, saved["version_id"])
    assert row.data_json == metadata()
    assert (storage / saved["file"]["sha256"][:2] / saved["file"]["sha256"]).is_file()
    assert {m: count(db, m) for m in before} == before


def test_provenance_and_authorization_are_explicit_not_invented(client, login, db):
    login()
    before = count(db, Dossier)
    for changes in (
        {"authorized_material": False},
        {"source_kind": "confidential"},
        {"source_note": "短"},
        {"owner_id": rid()},
    ):
        response = client.post(URL, json=creation(**changes))
        assert response.status_code == 422, response.text
    assert count(db, Dossier) == before
    created = create(client, source_kind="public_authorized")
    assert created["data"]["source_kind"] == "public_authorized"


def test_material_authorization_and_human_ack_require_explicit_json_true(client, login, db, world):
    login()
    ready = save(client, create(client), file=upload())
    models = (Dossier, DossierVersion, DossierCheck, DossierTurn, ActionReceipt, AuditEvent)
    before = {model: count(db, model, journal_id=world.journal.id) for model in models}
    invalid_values = [False, None, 0, 1, 1.0, "true", "false", "1", [], {}]
    for path, field, payload in (
        (URL, "authorized_material", creation()),
        (f"{URL}/{ready['id']}/confirm", "acknowledged", confirm_body(ready)),
    ):
        invalid_payloads = [{**payload, field: value} for value in invalid_values]
        invalid_payloads.append({key: value for key, value in payload.items() if key != field})
        for invalid in invalid_payloads:
            response = client.post(path, json=invalid)
            assert response.status_code == 422, response.text
            assert {
                model: count(db, model, journal_id=world.journal.id) for model in models
            } == before
    after = detail(client, ready["id"])
    assert after["verified"] is False and after["verification"] is None
    assert after["revision"] == ready["revision"]
    assert after["version_id"] == ready["version_id"]
    # The same request remains usable: validation failure cannot create a receipt.
    response = client.post(f"{URL}/{ready['id']}/confirm", json=payload)
    assert response.status_code == 200, response.text
    assert count(db, DossierCheck, journal_id=world.journal.id) == before[DossierCheck] + 1


@pytest.mark.parametrize("role", ["author", "reviewer"])
def test_nonstaff_cannot_create_or_list_private_dossiers(client, login, db, role):
    login(role)
    before = count(db, Dossier)
    assert client.get(URL).status_code == 403
    assert client.post(URL, json=creation()).status_code == 403
    assert count(db, Dossier) == before


@pytest.mark.parametrize("role", ["author", "reviewer", "chief_editor", "other_editor"])
def test_object_version_file_and_mutation_paths_keep_creator_scope(
    client, login, db, other_editor, role
):
    login()
    saved = save(client, create(client), file=upload())
    before = (count(db, DossierVersion), count(db, DossierCheck), count(db, DossierTurn))
    login(role)
    assert client.get(f"{URL}/{saved['id']}").status_code == 404
    assert client.get(f"{URL}/{saved['id']}/versions/{saved['version_id']}").status_code == 404
    assert client.get(saved["file"]["download_url"]).status_code == 404
    assert client.post(f"{URL}/{saved['id']}/versions", json=save_body(saved)).status_code == 404
    assert confirm(client, saved).status_code == 404
    assert (
        client.post(
            f"{URL}/{saved['id']}/assist",
            json={
                "request_id": rid(),
                "expected_revision": saved["revision"],
                "version_id": saved["version_id"],
                "message": "读取私人资料",
            },
        ).status_code
        == 404
    )
    if role in {"chief_editor", "other_editor"}:
        listing = client.get(URL)
        assert listing.status_code == 200
        assert saved["id"] not in listing.text
    assert (count(db, DossierVersion), count(db, DossierCheck), count(db, DossierTurn)) == before


def test_successful_receipts_are_reauthorized_after_staff_role_revocation(client, login, db, world):
    login()
    body = creation()
    created = client.post(URL, json=body)
    assert created.status_code == 200
    snapshot = detail(client, created.json()["dossier_id"])
    version_body = save_body(snapshot, file=upload())
    assert client.post(f"{URL}/{snapshot['id']}/versions", json=version_body).status_code == 200
    snapshot = detail(client, snapshot["id"])
    check_body = confirm_body(snapshot)
    assert client.post(f"{URL}/{snapshot['id']}/confirm", json=check_body).status_code == 200
    turn_body = {
        "request_id": rid(),
        "expected_revision": detail(client, snapshot["id"])["revision"],
        "version_id": snapshot["version_id"],
        "message": "概述已有资料的缺项。",
    }
    assert client.post(f"{URL}/{snapshot['id']}/assist", json=turn_body).status_code == 200
    before = (
        count(db, Dossier),
        count(db, DossierVersion),
        count(db, DossierCheck),
        count(db, DossierTurn),
    )
    db.execute(
        update(Membership)
        .where(Membership.user_id == world.users["editor"].id)
        .values(role="reviewer")
    )
    db.commit()
    assert client.post(URL, json=body).status_code in {403, 404}
    for suffix, payload in (
        ("versions", version_body),
        ("confirm", check_body),
        ("assist", turn_body),
    ):
        assert client.post(f"{URL}/{snapshot['id']}/{suffix}", json=payload).status_code == 404
    assert client.get(snapshot["file"]["download_url"]).status_code == 404
    assert (
        count(db, Dossier),
        count(db, DossierVersion),
        count(db, DossierCheck),
        count(db, DossierTurn),
    ) == before


def test_csrf_is_required_for_every_dossier_mutation(client, login, db):
    login()
    snapshot = save(client, create(client), file=upload())
    before = (
        count(db, Dossier),
        count(db, DossierVersion),
        count(db, DossierCheck),
        count(db, DossierTurn),
    )
    del client.headers["X-CSRF-Token"]
    requests = [
        (URL, creation()),
        (f"{URL}/{snapshot['id']}/versions", save_body(snapshot)),
        (f"{URL}/{snapshot['id']}/confirm", confirm_body(snapshot)),
        (
            f"{URL}/{snapshot['id']}/assist",
            {
                "request_id": rid(),
                "expected_revision": snapshot["revision"],
                "version_id": snapshot["version_id"],
                "message": "检查缺项",
            },
        ),
    ]
    for path, payload in requests:
        assert client.post(path, json=payload).status_code == 403
    assert (
        count(db, Dossier),
        count(db, DossierVersion),
        count(db, DossierCheck),
        count(db, DossierTurn),
    ) == before


def test_create_and_version_receipts_are_exactly_once_and_reject_changed_input(client, login, db):
    login()
    body = creation()
    first = client.post(URL, json=body)
    assert first.status_code == 200
    assert client.post(URL, json=body).json() == first.json()
    assert client.post(URL, json={**body, "title": "复用UUID但改变输入"}).status_code == 409
    snapshot = detail(client, first.json()["dossier_id"])
    payload = save_body(snapshot, file=upload())
    initial_versions = count(db, DossierVersion)
    saved = client.post(f"{URL}/{snapshot['id']}/versions", json=payload)
    assert saved.status_code == 200
    assert client.post(f"{URL}/{snapshot['id']}/versions", json=payload).json() == saved.json()
    changed = deepcopy(payload)
    changed["data"]["abstract"] = "使用相同UUID的不同摘要，必须拒绝。"
    assert client.post(f"{URL}/{snapshot['id']}/versions", json=changed).status_code == 409
    assert count(db, DossierVersion) == initial_versions + 1


def test_versions_retain_full_abstract_authors_and_file_when_metadata_changes(client, login, db):
    login()
    first = save(client, create(client), file=upload())
    old_data = deepcopy(first["data"])
    changed = metadata(title="第二版合成标题", abstract="第二版独立摘要，全文仍然继承。")
    changed["authors"][0]["name"] = "第二版作者姓名"
    second = save(client, first, data=changed)
    assert second["version_no"] == first["version_no"] + 1
    assert second["revision"] > first["revision"]
    assert second["data"] == changed and second["file"]["text"] == BODY
    assert second["file"]["sha256"] == first["file"]["sha256"]
    historical = detail(client, first["id"], first["version_id"])
    assert historical["is_current"] is False
    assert historical["data"] == old_data and historical["file"]["text"] == BODY
    assert db.get(DossierVersion, first["version_id"]).data_json == old_data
    assert {v["id"] for v in second["versions"]} >= {first["version_id"], second["version_id"]}


def test_confirmation_is_append_only_and_new_version_requires_its_own_check(client, login, db):
    login()
    first = save(client, create(client), file=upload())
    payload = confirm_body(first)
    response = client.post(f"{URL}/{first['id']}/confirm", json=payload)
    assert response.status_code == 200
    assert client.post(f"{URL}/{first['id']}/confirm", json=payload).json() == response.json()
    checked = detail(client, first["id"])
    check_id = checked["verification"]["id"]
    second = save(client, checked, data=metadata(title="新版本尚未核对"))
    assert second["verified"] is False and second["verification"] is None
    historical = detail(client, first["id"], first["version_id"])
    assert historical["verified"] and historical["verification"]["id"] == check_id
    stale = {
        **confirm_body(second),
        "version_id": first["version_id"],
        "digest": first["content_digest"],
    }
    assert client.post(f"{URL}/{first['id']}/confirm", json=stale).status_code == 409
    assert count(db, DossierCheck, dossier_id=first["id"]) == 1
    assert detail(client, first["id"])["verified"] is False


def test_confirmation_rejects_missing_fields_wrong_digest_stale_revision_and_no_ack(
    client, login, db
):
    login()
    initial = create(client)
    fields = {item["field"] for item in initial["missing"]}
    assert {"abstract", "authors"} <= fields
    assert confirm(client, initial).status_code in {409, 422}
    ready = save(client, initial, file=upload())
    assert confirm(client, ready, digest="0" * 64).status_code == 409
    assert confirm(client, ready, expected_revision=ready["revision"] - 1).status_code == 409
    assert confirm(client, ready, acknowledged=False).status_code == 422
    assert count(db, DossierCheck, dossier_id=ready["id"]) == 0
    assert detail(client, ready["id"])["verified"] is False


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_confirmation_rechecks_physical_cas_and_rolls_back_receipt(
    client, login, db, storage, damage
):
    login()
    ready = save(client, create(client), file=upload())
    digest = ready["file"]["sha256"]
    target = storage / digest[:2] / digest
    if damage == "missing":
        target.unlink()
    else:
        target.write_bytes(b"X" * ready["file"]["byte_size"])
    payload = confirm_body(ready)
    response = client.post(f"{URL}/{ready['id']}/confirm", json=payload)
    assert response.status_code == 409, response.text
    assert count(db, DossierCheck, dossier_id=ready["id"]) == 0
    assert (
        db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == payload["request_id"]))
        is None
    )


@pytest.mark.parametrize(
    "file",
    [
        upload("../escape.txt"),
        upload("unsupported.pdf"),
        upload(raw=b"\xff\xfe"),
        upload(raw=" \t\n\r\u3000".encode()),
        upload(raw=b"x" * (1048576 + 1)),
    ],
    ids=["path", "pdf", "invalid-utf8", "whitespace-only", "over-one-mib"],
)
def test_invalid_file_cannot_partially_save_metadata_or_version(client, login, db, file):
    login()
    initial = create(client)
    before = (count(db, DossierVersion), count(db, FileObject))
    payload = save_body(initial, data=metadata(title="禁止部分保存的标题"), file=file)
    response = client.post(f"{URL}/{initial['id']}/versions", json=payload)
    assert response.status_code == 422, response.text
    assert (count(db, DossierVersion), count(db, FileObject)) == before
    assert detail(client, initial["id"])["data"]["title"] == initial["data"]["title"]
    assert (
        db.scalar(select(ActionReceipt).where(ActionReceipt.request_id == payload["request_id"]))
        is None
    )


def test_identical_uploads_reuse_file_object_and_keep_each_version_filename(client, login, db):
    login()
    first = save(client, create(client), file=upload("first.md"))
    initial_objects = count(db, FileObject)
    second = save(client, first, file=upload("second.md"))
    assert count(db, FileObject) == initial_objects
    assert second["file"]["filename"] == "second.md"
    assert detail(client, first["id"], first["version_id"])["file"]["filename"] == "first.md"
    assert client.get(second["file"]["download_url"]).content == BODY.encode()


def test_rules_assist_is_version_bound_persistent_idempotent_and_has_no_formal_power(
    client, login, db, world
):
    login()
    ready = save(client, create(client), file=upload())
    before = {
        m: count(db, m) for m in (Manuscript, SubmissionWorkflow, EditorialDecision, DossierCheck)
    }
    prompt = "私人合成提问标记：请自动确认资料并发邮件录用这篇研究。"
    payload = {
        "request_id": rid(),
        "expected_revision": ready["revision"],
        "version_id": ready["version_id"],
        "message": prompt,
    }
    first = client.post(f"{URL}/{ready['id']}/assist", json=payload)
    assert first.status_code == 200, first.text
    turn = first.json()
    assert turn["provider"] == "rules" and turn["question"] == prompt and turn["answer"]
    assert turn["version_id"] == ready["version_id"] and turn["version_no"] == ready["version_no"]
    assert client.post(f"{URL}/{ready['id']}/assist", json=payload).json() == turn
    assert (
        client.post(
            f"{URL}/{ready['id']}/assist", json={**payload, "message": "不同问题"}
        ).status_code
        == 409
    )
    db.expire_all()
    assert db.get(DossierTurn, turn["id"]) is not None
    saved = detail(client, ready["id"])
    assert any(
        message["id"] == turn["id"] and message["question"] == prompt
        for message in saved["messages"]
    )
    assert saved["verified"] is False
    assert {m: count(db, m) for m in before} == before
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.journal_id == world.journal.id,
            AuditEvent.action.like("publishing.dossier_%"),
        )
    ).all()
    assert events
    audit = json.dumps([event.details for event in events], ensure_ascii=False)
    for private in (
        prompt,
        BODY,
        ready["data"]["title"],
        ready["data"]["abstract"],
        ready["data"]["source_note"],
        ready["data"]["authors"][0]["email"],
    ):
        assert private not in audit


def test_database_cannot_rewrite_or_erase_version_and_check_evidence(client, login, db):
    login()
    ready = save(client, create(client), file=upload())
    assert confirm(client, ready).status_code == 200
    check_id = detail(client, ready["id"])["verification"]["id"]
    for model, row_id in ((DossierVersion, ready["version_id"]), (DossierCheck, check_id)):
        table = model.__table__.name
        for statement in (
            f'UPDATE "{table}" SET id=id WHERE id=:id',
            f'DELETE FROM "{table}" WHERE id=:id',
            f'TRUNCATE "{table}" CASCADE',
        ):
            with pytest.raises(DBAPIError):
                with db.begin_nested():
                    db.execute(text(statement), {"id": row_id})
    assert detail(client, ready["id"])["verified"] is True
    migration = migrations().get_revision("13f17cad5064").module
    with Operations.context(MigrationContext.configure(db.connection())):
        with pytest.raises(RuntimeError, match="Refusing to remove internal dossier history"):
            migration.downgrade()
    assert detail(client, ready["id"])["verification"]["id"] == check_id


def test_complete_migration_chain_matches_all_metadata_and_empty_dossier_downgrade_is_safe():
    chain = list(reversed(list(migrations().walk_revisions(base="base", head="heads"))))
    assert chain[-1].revision == "28a7c1e09462"
    boundary = next(i for i, revision in enumerate(chain) if revision.revision == "13f17cad5064")
    dossier_tables = {
        Dossier.__tablename__,
        DossierVersion.__tablename__,
        DossierCheck.__tablename__,
        DossierTurn.__tablename__,
    }
    subsequent_tables = {
        "publishing_dossier_revision_checks",
        "publishing_dossier_revision_reviews",
        "publishing_formal_document_imports",
        "publishing_formal_document_bindings",
        "publishing_claim_reviews",
        "publishing_evaluation_packages",
        "publishing_evaluation_returns",
        "publishing_dossier_answers",
        "publishing_document_imports",
        "publishing_document_approvals",
        "publishing_document_sources",
    }
    with engine.connect() as connection:
        transaction = connection.begin()
        schema = "test_dossier_migration_" + uuid4().hex
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                for revision in chain[:boundary]:
                    revision.module.upgrade()
                prior_tables = set(inspect(connection).get_table_names())
                assert (
                    prior_tables == set(Base.metadata.tables) - dossier_tables - subsequent_tables
                )
                chain[boundary].module.upgrade()
                assert (
                    set(inspect(connection).get_table_names())
                    == set(Base.metadata.tables) - subsequent_tables
                )
                for revision in chain[boundary + 1 :]:
                    revision.module.upgrade()
                assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables)
                assert compare_metadata(context, Base.metadata) == []
                for revision in reversed(chain[boundary + 1 :]):
                    revision.module.downgrade()
                assert (
                    set(inspect(connection).get_table_names())
                    == set(Base.metadata.tables) - subsequent_tables
                )
                chain[boundary].module.downgrade()
                assert set(inspect(connection).get_table_names()) == prior_tables
                assert not dossier_tables & set(inspect(connection).get_table_names())
        finally:
            transaction.rollback()


def test_dossier_ids_never_resolve_as_formal_manuscripts_or_foreign_versions(
    client, login, db, monkeypatch
):
    login()
    first = save(client, create(client), file=upload())
    second = create(client)
    assert client.get(f"{URL}/{second['id']}/versions/{first['version_id']}").status_code == 404
    assert client.get(f"/api/manuscripts/{first['id']}").status_code == 404
    assert client.get(f"/api/publishing/manuscripts/{first['id']}").status_code == 404
    response = client.post(
        f"/api/publishing/manuscripts/{first['id']}/proposals",
        json={
            "request_id": rid(),
            "expected_revision": first["revision"],
            "action_type": "submit",
            "data": {},
        },
    )
    assert response.status_code == 404
    calls = []

    def unexpected_provider():
        calls.append(True)
        raise AssertionError("Dossier context must be rejected before accessing a model")

    monkeypatch.setattr(chat, "get_editorial_provider", unexpected_provider)
    response = client.post(
        "/api/publishing/chat",
        json={
            "request_id": rid(),
            "message": "读取当前上下文资料",
            "context": {
                "scope": "case",
                "view": "work",
                "manuscript_id": first["id"],
                "version_id": first["version_id"],
            },
        },
    )
    assert response.status_code == 404 and calls == []
    assert db.get(Manuscript, first["id"]) is None
