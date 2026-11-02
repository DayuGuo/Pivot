import hashlib
import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "infrastructure/migrations/versions"
url = sa.engine.make_url(os.environ["DATABASE_URL"])
if url.host not in {"localhost", "127.0.0.1"} or url.port != 55433:
    raise SystemExit(
        "Rehearsal requires isolated local PostgreSQL on port55433; main database refused"
    )
engine = sa.create_engine(url)
checks = []


def module(name):
    spec = importlib.util.spec_from_file_location("rehearsal_" + name, PATH / name)
    item = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(item)
    return item


def rejected(conn, name, fn):
    point = conn.begin_nested()
    try:
        fn()
    except DBAPIError:
        point.rollback()
        checks.append(name)
        return
    point.rollback()
    raise AssertionError(name + " did not reject")


with engine.connect() as conn:
    outer = conn.begin()
    schema = "rehearsal_" + uuid4().hex
    conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        for name in (
            "3984270ae78e_initial_editorial_intake.py",
            "0002_audit_guards.py",
            "a99d14733f66_conversation_sessions_and_mail_bindings.py",
            "c81b8c41b016_editorial_demo_workspace.py",
            "e7b24c91a603_contextual_editorial_chat.py",
        ):
            module(name).upgrade()
        journal, otherjournal, author, editor = [str(uuid4()) for _ in range(4)]
        conn.execute(
            sa.text("INSERT INTO journals(id,name) VALUES (:id,:name)"),
            [
                {"id": journal, "name": "Synthetic foundation validation"},
                {"id": otherjournal, "name": "Other synthetic journal"},
            ],
        )
        conn.execute(
            sa.text(
                "INSERT INTO users(id,email,name,password_hash) VALUES (:id,:email,:name,:password)"
            ),
            [
                {
                    "id": author,
                    "email": "author@foundation.test",
                    "name": "Known author",
                    "password": "not-used",
                },
                {
                    "id": editor,
                    "email": "editor@foundation.test",
                    "name": "Known editor",
                    "password": "not-used",
                },
            ],
        )
        old = str(uuid4())
        task = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO manuscripts(id,journal_id,author_id,editor_id,title,status,created_at) VALUES (:id,:j,:a,:e,'Preserved legacy title','screening',now())"
            ),
            {"id": old, "j": journal, "a": author, "e": editor},
        )
        conn.execute(
            sa.text(
                "INSERT INTO editorial_tasks(id,manuscript_id,assignee_id,kind,status) VALUES (:id,:m,:e,'initial_screening','pending')"
            ),
            {"id": task, "m": old, "e": editor},
        )
        conn.execute(
            sa.text(
                "INSERT INTO audit_events(id,journal_id,actor_id,action,entity_id,details,created_at) VALUES (:id,:j,:e,'manuscript.created',:m,'{}',now())"
            ),
            {"id": str(uuid4()), "j": journal, "e": editor, "m": old},
        )
        migration = module("f8a12d4c6e90_publishing_foundation.py")
        migration.upgrade()
        row = (
            conn.execute(
                sa.text("SELECT * FROM publishing_workflows WHERE manuscript_id=:m"), {"m": old}
            )
            .mappings()
            .one()
        )
        version = (
            conn.execute(
                sa.text("SELECT * FROM publishing_versions WHERE id=:v"),
                {"v": row["current_version_id"]},
            )
            .mappings()
            .one()
        )
        assert (
            row["number"] == "LEGACY-" + old
            and row["is_legacy"]
            and row["stage"] == "legacy_screening"
        )
        assert (
            version["language"] == "und"
            and version["title"] == "Preserved legacy title"
            and version["provenance"] == "legacy"
        )
        assert (
            version["metadata_json"]["original_status"] == "screening"
            and version["metadata_json"]["corresponding_author_known"] is False
        )
        assert conn.scalar(sa.text("SELECT count(*) FROM publishing_file_objects")) == 0
        assert conn.scalar(sa.text("SELECT count(*) FROM publishing_human_confirmations")) == 0
        assert conn.scalar(sa.text("SELECT count(*) FROM publishing_work_items")) == 1
        checks.append("truthful_legacy_uuid_title_author_editor_task_backfill")
        rejected(
            conn,
            "frozen_legacy_version_update",
            lambda: conn.execute(
                sa.text("UPDATE publishing_versions SET title='tampered' WHERE id=:v"),
                {"v": version["id"]},
            ),
        )
        rejected(
            conn,
            "frozen_author_insert",
            lambda: conn.execute(
                sa.text(
                    "INSERT INTO publishing_version_authors(id,manuscript_id,version_id,ordinal,name,email) VALUES (:id,:m,:v,1,'Not allowed','new@foundation.test')"
                ),
                {"id": str(uuid4()), "m": old, "v": version["id"]},
            ),
        )
        rejected(
            conn,
            "frozen_author_delete",
            lambda: conn.execute(
                sa.text("DELETE FROM publishing_version_authors WHERE version_id=:v"),
                {"v": version["id"]},
            ),
        )
        # All actual publishing test rows are inside this savepoint and rolled back
        # before the allowed legacy-only downgrade rehearsal.
        actual = conn.begin_nested()
        meta = sa.MetaData()
        names = [
            "manuscripts",
            "publishing_workflows",
            "publishing_versions",
            "publishing_version_authors",
            "publishing_file_objects",
            "publishing_version_files",
            "publishing_step_runs",
            "publishing_work_items",
            "publishing_action_proposals",
            "publishing_human_confirmations",
            "login_sessions",
        ]
        t = {n: sa.Table(n, meta, autoload_with=conn) for n in names}
        stamp = conn.scalar(sa.select(sa.func.now()))
        m1, m2, v1, v2, s1, s2, w1, w2 = [str(uuid4()) for _ in range(8)]
        for m in (m1, m2):
            conn.execute(
                t["manuscripts"]
                .insert()
                .values(
                    id=m,
                    journal_id=journal,
                    author_id=author,
                    editor_id=None,
                    title="x" * 480,
                    status="draft",
                    workflow_kind="publishing",
                    created_at=stamp,
                )
            )
        for m, v, s, w in ((m1, v1, s1, w1), (m2, v2, s2, w2)):
            conn.execute(
                t["publishing_versions"]
                .insert()
                .values(
                    id=v,
                    manuscript_id=m,
                    version_no=1,
                    created_by=author,
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
            conn.execute(
                t["publishing_step_runs"]
                .insert()
                .values(
                    id=s,
                    manuscript_id=m,
                    version_id=v,
                    step_key="author_draft",
                    cycle_no=1,
                    entered_at=stamp,
                )
            )
            conn.execute(
                t["publishing_work_items"]
                .insert()
                .values(
                    id=w,
                    manuscript_id=m,
                    journal_id=journal,
                    step_run_id=s,
                    version_id=v,
                    kind="confirm_submission",
                    assignee_id=author,
                    created_at=stamp,
                )
            )
            conn.execute(
                t["publishing_workflows"]
                .insert()
                .values(
                    manuscript_id=m,
                    journal_id=journal,
                    number="POS-2026-" + m[:8],
                    stage="author_draft",
                    draft_version_id=v,
                    current_step_id=s,
                    created_at=stamp,
                    updated_at=stamp,
                )
            )
        checks.append("nullable_editor_and_title500")
        rejected(
            conn,
            "cross_manuscript_current_version",
            lambda: conn.execute(
                t["publishing_workflows"]
                .update()
                .where(t["publishing_workflows"].c.manuscript_id == m1)
                .values(current_version_id=v2)
            ),
        )
        rejected(
            conn,
            "cross_journal_workflow",
            lambda: conn.execute(
                t["publishing_workflows"]
                .update()
                .where(t["publishing_workflows"].c.manuscript_id == m1)
                .values(journal_id=otherjournal)
            ),
        )
        rejected(
            conn,
            "unknown_stage_check",
            lambda: conn.execute(
                t["publishing_workflows"]
                .update()
                .where(t["publishing_workflows"].c.manuscript_id == m1)
                .values(stage="automatically_published")
            ),
        )
        rejected(
            conn,
            "cross_manuscript_work_item_step",
            lambda: conn.execute(
                t["publishing_work_items"]
                .update()
                .where(t["publishing_work_items"].c.id == w1)
                .values(step_run_id=s2)
            ),
        )
        aid = str(uuid4())
        conn.execute(
            t["publishing_version_authors"]
            .insert()
            .values(
                id=aid,
                manuscript_id=m1,
                version_id=v1,
                ordinal=0,
                name="Confirmed candidate",
                email="author@foundation.test",
                corresponding=True,
            )
        )
        rejected(
            conn,
            "single_corresponding_author",
            lambda: conn.execute(
                t["publishing_version_authors"]
                .insert()
                .values(
                    id=str(uuid4()),
                    manuscript_id=m1,
                    version_id=v1,
                    ordinal=1,
                    name="Second",
                    email="other@foundation.test",
                    corresponding=True,
                )
            ),
        )
        fid = str(uuid4())
        conn.execute(
            t["publishing_file_objects"]
            .insert()
            .values(
                id=fid,
                journal_id=journal,
                uploaded_by=author,
                sha256=hashlib.sha256(b"example").hexdigest(),
                byte_size=7,
                media_type="text/plain",
                storage_key="controlled-key",
                original_filename="synthetic.txt",
                created_at=stamp,
            )
        )
        rejected(
            conn,
            "immutable_file_object",
            lambda: conn.execute(
                t["publishing_file_objects"]
                .update()
                .where(t["publishing_file_objects"].c.id == fid)
                .values(storage_key="replacement")
            ),
        )
        rejected(
            conn,
            "file_size_check",
            lambda: conn.execute(
                t["publishing_file_objects"]
                .insert()
                .values(
                    id=str(uuid4()),
                    journal_id=journal,
                    uploaded_by=author,
                    sha256="b" * 64,
                    byte_size=1048577,
                    media_type="text/plain",
                    storage_key="invalid-key",
                    original_filename="large.txt",
                    created_at=stamp,
                )
            ),
        )
        rejected(
            conn,
            "cross_manuscript_version_file",
            lambda: conn.execute(
                t["publishing_version_files"]
                .insert()
                .values(
                    id=str(uuid4()),
                    manuscript_id=m2,
                    journal_id=journal,
                    version_id=v1,
                    file_object_id=fid,
                    purpose="manuscript",
                    visibility="author_editor",
                    display_name="synthetic.txt",
                    created_by=author,
                    created_at=stamp,
                )
            ),
        )
        vf = str(uuid4())
        conn.execute(
            t["publishing_version_files"]
            .insert()
            .values(
                id=vf,
                manuscript_id=m1,
                journal_id=journal,
                version_id=v1,
                file_object_id=fid,
                purpose="manuscript",
                visibility="author_editor",
                display_name="synthetic.txt",
                created_by=author,
                created_at=stamp,
            )
        )
        conn.execute(
            t["publishing_versions"]
            .update()
            .where(t["publishing_versions"].c.id == v1)
            .values(content_digest="a" * 64, frozen_at=stamp)
        )
        rejected(
            conn,
            "frozen_version_file_update",
            lambda: conn.execute(
                t["publishing_version_files"]
                .update()
                .where(t["publishing_version_files"].c.id == vf)
                .values(display_name="change.txt")
            ),
        )
        rejected(
            conn,
            "frozen_author_move",
            lambda: conn.execute(
                t["publishing_version_authors"]
                .update()
                .where(t["publishing_version_authors"].c.id == aid)
                .values(version_id=v2, manuscript_id=m2)
            ),
        )
        proposal = str(uuid4())
        conn.execute(
            t["publishing_action_proposals"]
            .insert()
            .values(
                id=proposal,
                manuscript_id=m1,
                journal_id=journal,
                work_item_id=w1,
                version_id=v1,
                action_type="submit",
                prepared_by=author,
                responsible_user_id=author,
                base_revision=0,
                policy_version=1,
                payload_snapshot={"title": "snapshot"},
                evidence_digests={"main": "a" * 64},
                digest="c" * 64,
                created_at=stamp,
                expires_at=stamp,
            )
        )
        rejected(
            conn,
            "proposal_snapshot_immutable",
            lambda: conn.execute(
                t["publishing_action_proposals"]
                .update()
                .where(t["publishing_action_proposals"].c.id == proposal)
                .values(payload_snapshot={"title": "changed"})
            ),
        )
        conn.execute(
            t["publishing_action_proposals"]
            .update()
            .where(t["publishing_action_proposals"].c.id == proposal)
            .values(superseded_at=stamp)
        )
        rejected(
            conn,
            "proposal_cannot_reactivate",
            lambda: conn.execute(
                t["publishing_action_proposals"]
                .update()
                .where(t["publishing_action_proposals"].c.id == proposal)
                .values(superseded_at=None)
            ),
        )
        confirmation = str(uuid4())
        token = "d" * 64
        conn.execute(
            t["login_sessions"]
            .insert()
            .values(token_hash=token, user_id=author, csrf_token="e" * 64, expires_at=stamp)
        )
        conn.execute(
            t["publishing_human_confirmations"]
            .insert()
            .values(
                id=confirmation,
                manuscript_id=m1,
                proposal_id=proposal,
                responsible_user_id=author,
                session_hash=token,
                digest="c" * 64,
                outcome="return",
                reason="test evidence only",
                confirmed_at=stamp,
            )
        )
        conn.execute(t["login_sessions"].delete().where(t["login_sessions"].c.token_hash == token))
        checks.append("logout_preserves_confirmation_session_digest")
        rejected(
            conn,
            "confirmation_immutable",
            lambda: conn.execute(
                t["publishing_human_confirmations"]
                .update()
                .where(t["publishing_human_confirmations"].c.id == confirmation)
                .values(reason="modified")
            ),
        )
        rejected(
            conn,
            "cross_manuscript_confirmation_pointer",
            lambda: conn.execute(
                t["publishing_work_items"]
                .update()
                .where(t["publishing_work_items"].c.id == w2)
                .values(confirmation_id=confirmation)
            ),
        )
        conn.execute(
            t["publishing_step_runs"]
            .update()
            .where(t["publishing_step_runs"].c.id == s1)
            .values(status="completed", completed_at=stamp, confirmation_id=confirmation)
        )
        rejected(
            conn,
            "completed_step_cannot_reset",
            lambda: conn.execute(
                t["publishing_step_runs"]
                .update()
                .where(t["publishing_step_runs"].c.id == s1)
                .values(status="pending")
            ),
        )
        rejected(conn, "publishing_data_downgrade_refused", migration.downgrade)
        actual.rollback()
        migration.downgrade()
        assert (
            conn.scalar(sa.text("SELECT title FROM manuscripts WHERE id=:m"), {"m": old})
            == "Preserved legacy title"
        )
        assert (
            conn.scalar(sa.text("SELECT count(*) FROM editorial_tasks WHERE id=:id"), {"id": task})
            == 1
        )
        checks.append("legacy_only_downgrade_preserves_original_data")
        migration.upgrade()
        assert conn.scalar(sa.text("SELECT count(*) FROM publishing_workflows")) == 1
        assert conn.scalar(sa.text("SELECT count(*) FROM publishing_work_items")) == 1
        checks.append("upgrade_after_legacy_downgrade_recreates_same_foundation")
    outer.rollback()
print(
    json.dumps(
        {
            "passed": len(checks),
            "checks": checks,
            "scope": "isolated55433 temporary schema transaction rolled back; no main database access",
        },
        indent=2,
    )
)
