"""Same human confirmation retried on independent PostgreSQL connections."""

import base64
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.publishing.db import engine
from apps.api.publishing.domain import core
from apps.api.publishing.domain.models import HumanConfirmation, SubmissionWorkflow, WorkItem
from apps.api.publishing.domain.schemas import FileUpload, IntakeData
from apps.api.publishing.models import Journal, Membership, User
from apps.api.publishing.security import Actor, new_session
from tests.api.test_publishing_intake import complete_data


def test_concurrent_human_confirmation_commits_once(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))
    suffix = uuid4().hex
    with Session(engine, expire_on_commit=False) as db:
        journal = Journal(name="Pytest publishing concurrency " + suffix)
        db.add(journal)
        db.flush()
        owner = None
        for role in ("author", "editor", "chief_editor"):
            user = User(
                email=f"{role}-{suffix}@confirmation.test",
                name="Synthetic " + role,
                password_hash="not-a-login",
            )
            db.add(user)
            db.flush()
            member = Membership(journal_id=journal.id, user_id=user.id, role=role)
            db.add(member)
            if role == "author":
                owner, membership = user, member
        _, session = new_session(owner)
        db.add(session)
        db.commit()
        owner_id, membership_id, session_hash = owner.id, membership.id, session.token_hash
        actor = Actor(owner, membership, session)

        def action(name, fn):
            return core.run_action(db, actor, str(uuid4()), name, {}, fn)

        created = action("new_draft", lambda: core.new_draft(db, actor))
        mid = created["manuscript_id"]
        result = action(
            "save_intake",
            lambda: core.save_intake(db, actor, mid, 0, IntakeData.model_validate(complete_data())),
        )
        revision = result["revision"]
        for purpose in ("manuscript", "blinded_manuscript"):
            result = action(
                "upload_file",
                lambda revision=revision, purpose=purpose: core.upload_file(
                    db,
                    actor,
                    mid,
                    revision,
                    FileUpload(
                        filename=purpose + ".txt",
                        purpose=purpose,
                        content_base64=base64.b64encode(b"Synthetic immutable material.").decode(),
                    ),
                ),
            )
            revision = result["revision"]
        proposal = action(
            "prepare_proposal", lambda: core.prepare_proposal(db, actor, mid, revision, "submit")
        )
    request = str(uuid4())

    def confirm(_):
        with Session(engine, expire_on_commit=False) as db:
            actor = Actor(
                db.get(User, owner_id),
                db.get(Membership, membership_id),
                db.get(type(session), session_hash),
            )
            return core.run_action(
                db,
                actor,
                request,
                "confirm_proposal",
                {"proposal": proposal["proposal_id"]},
                lambda: core.confirm_proposal(
                    db,
                    actor,
                    proposal["proposal_id"],
                    revision,
                    proposal["digest"],
                    acknowledged=True,
                ),
            )

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(confirm, range(4)))
    assert all(result == results[0] for result in results)
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(HumanConfirmation)
                .where(HumanConfirmation.manuscript_id == mid)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkItem)
                .where(
                    WorkItem.manuscript_id == mid,
                    WorkItem.kind == "precheck_completeness",
                    WorkItem.status == "pending",
                )
            )
            == 1
        )
        assert db.get(SubmissionWorkflow, mid).revision == revision + 1
