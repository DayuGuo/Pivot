"""Literal metadata discovery must not become a hidden-material search oracle."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update

from apps.api.publishing import search as search_module
from apps.api.publishing.domain.models import (
    Assignment,
    ManuscriptVersion,
    SubmissionWorkflow,
    VersionAuthor,
)
from apps.api.publishing.models import (
    AuditEvent,
    Conversation,
    LoginSession,
    Manuscript,
    Membership,
    Message,
    now,
)
from apps.api.publishing.security import token_digest
from tests.api.test_dossiers import create as create_dossier
from tests.api.test_dossiers import metadata as dossier_metadata
from tests.api.test_dossiers import save as save_dossier
from tests.api.test_publishing_decisions import production as production
from tests.api.test_publishing_peer_review import open_round, reviewer_selection
from tests.api.test_publishing_production import accepted

URL = "/api/search"


@pytest.fixture(autouse=True)
def private_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(tmp_path / "files"))


def results(client, query, limit=8):
    response = client.get(URL, params={"q": query, "limit": limit})
    assert response.status_code == 200, response.text
    return response.json()


def group(response, kind):
    return next(item for item in response["groups"] if item["kind"] == kind)


def ids(response, kind):
    return {item["id"] for item in group(response, kind)["items"]}


def conversation(db, world, title, *, user="editor", journal=None, at=None):
    row = Conversation(
        user_id=world.users[user].id,
        journal_id=(journal or world.journal).id,
        title=title,
        updated_at=at or now(),
    )
    db.add(row)
    db.flush()
    return row


def formal(
    db,
    world,
    title,
    *,
    draft_title=None,
    stage="precheck_completeness",
    assignee="editor",
    journal=None,
    at=None,
):
    """Synthetic persisted read fixtures; no simulated human confirmations."""
    journal = journal or world.journal
    manuscript = Manuscript(
        journal_id=journal.id,
        author_id=world.users["author"].id,
        editor_id=None,
        workflow_kind="publishing",
        title=draft_title or title,
        status="draft" if stage == "author_draft" else "screening",
    )
    db.add(manuscript)
    db.flush()
    current = ManuscriptVersion(
        manuscript_id=manuscript.id,
        version_no=1,
        title=title,
        abstract="全文摘要不参与搜索：HiddenAbstractNeedle",
        metadata_json={"keywords": ["HiddenKeywordNeedle"]},
        created_by=world.users["author"].id,
        frozen_at=now() if stage != "author_draft" else None,
    )
    db.add(current)
    db.flush()
    draft = None
    if draft_title is not None:
        draft = ManuscriptVersion(
            manuscript_id=manuscript.id,
            version_no=2,
            title=draft_title,
            created_by=world.users["author"].id,
        )
        db.add(draft)
        db.flush()
    workflow = SubmissionWorkflow(
        manuscript_id=manuscript.id,
        journal_id=journal.id,
        number="POS-SEARCH-" + uuid4().hex,
        stage=stage,
        current_version_id=current.id if stage != "author_draft" else None,
        draft_version_id=draft.id if draft else current.id if stage == "author_draft" else None,
        updated_at=at or now(),
    )
    db.add(workflow)
    if assignee:
        db.add(
            Assignment(
                manuscript_id=manuscript.id,
                journal_id=journal.id,
                user_id=world.users[assignee].id,
                capability="precheck",
            )
        )
    db.flush()
    return manuscript, workflow, current, draft


def legacy(db, world, title, *, journal=None):
    row = Manuscript(
        journal_id=(journal or world.journal).id,
        author_id=world.users["author"].id,
        editor_id=world.users["editor"].id,
        title=title,
        status="screening",
        workflow_kind="legacy",
    )
    db.add(row)
    db.flush()
    return row


def test_search_requires_authentication(client):
    assert client.get(URL, params={"q": "synthetic"}).status_code == 401


@pytest.mark.parametrize(
    "parameters",
    [{"q": "a" * 161}, {"q": "bad\x00query"}, {"q": "a", "limit": 0}, {"q": "a", "limit": 21}],
)
def test_invalid_query_bounds_are_rejected(client, login, parameters):
    login()
    assert client.get(URL, params=parameters).status_code == 422


def test_normalized_tokens_are_literal_case_insensitive_and_combined_with_and(
    client, login, db, world
):
    first = conversation(db, world, "Alpha 中间 BETA")
    conversation(db, world, "Alpha only")
    conversation(db, world, "Beta only")
    db.commit()
    login()
    value = results(client, " \talpha\n  beta  ")
    assert value["query"] == "alpha beta"
    assert ids(value, "conversation") == {first.id}
    assert all(
        not item["items"] and not item["has_more"] for item in results(client, " \t ")["groups"]
    )


@pytest.mark.parametrize("literal", ["%", "_", "\\"])
def test_sql_wildcards_and_escape_characters_are_literal(client, login, db, world, literal):
    needle = conversation(db, world, f"literal {literal} target")
    conversation(db, world, "literal ordinary target")
    db.commit()
    login()
    assert ids(results(client, literal), "conversation") == {needle.id}


def test_conversation_owner_journal_scope_and_no_message_body_search(client, login, db, world):
    own = conversation(db, world, "FindConversation unique")
    conversation(db, world, "FindConversation other", user="chief_editor")
    conversation(db, world, "FindConversation foreign", journal=world.other_journal)
    db.add(
        Message(
            user_id=world.users["editor"].id,
            conversation_id=own.id,
            role="user",
            content="PrivateMessageNeedle",
            provider="mock",
        )
    )
    db.commit()
    login()
    assert ids(results(client, "FindConversation"), "conversation") == {own.id}
    item = group(results(client, own.id[:12]), "conversation")["items"][0]
    assert item == {"id": own.id, "title": own.title, "href": f"/?conversation={own.id}"}
    assert not ids(results(client, "PrivateMessageNeedle"), "conversation")


@pytest.mark.parametrize("role", ["author", "editor", "chief_editor", "reviewer"])
def test_formal_scope_is_current_role_and_drafts_remain_owner_only(client, login, db, world, role):
    assigned, workflow, _, _ = formal(db, world, "FormalScope assigned")
    unassigned, _, _, _ = formal(db, world, "FormalScope unassigned", assignee=None)
    private, _, _, _ = formal(
        db, world, "FormalScope author draft", stage="author_draft", assignee=None
    )
    formal(db, world, "FormalScope foreign", journal=world.other_journal)
    db.commit()
    login(role)
    expected = {
        "author": {assigned.id, unassigned.id, private.id},
        "editor": {assigned.id},
        "chief_editor": {assigned.id, unassigned.id},
        "reviewer": set(),
    }[role]
    assert ids(results(client, "FormalScope"), "manuscript") == expected
    if role != "reviewer":
        number = results(client, workflow.number)
        assert ids(number, "manuscript") == {assigned.id}
        assert ids(results(client, "#" + assigned.id[:12]), "manuscript") == {assigned.id}
        assert ids(results(client, assigned.id[:12]), "manuscript") == {assigned.id}
        item = group(number, "manuscript")["items"][0]
        assert item["href"] == f"/publishing?manuscript={assigned.id}"


def test_staff_cannot_match_unsubmitted_revision_title_or_other_private_fields(
    client, login, db, world
):
    manuscript, _, _, draft = formal(
        db,
        world,
        "SubmittedCurrentNeedle",
        draft_title="UnsubmittedDraftNeedle",
        stage="author_revision",
    )
    db.add(
        VersionAuthor(
            manuscript_id=manuscript.id,
            version_id=draft.id,
            ordinal=0,
            name="HiddenAuthorNeedle",
            email="synthetic@example.test",
        )
    )
    db.commit()
    login()
    assert ids(results(client, "SubmittedCurrentNeedle"), "manuscript") == {manuscript.id}
    for query in (
        "UnsubmittedDraftNeedle",
        "HiddenAuthorNeedle",
        "HiddenAbstractNeedle",
        "HiddenKeywordNeedle",
    ):
        assert not ids(results(client, query), "manuscript")
    login("author")
    assert ids(results(client, "UnsubmittedDraftNeedle"), "manuscript") == {manuscript.id}
    assert not ids(results(client, "SubmittedCurrentNeedle"), "manuscript")


def test_inactive_chief_grant_does_not_expand_reviewer_search(client, login, db, world):
    manuscript, _, _, _ = formal(db, world, "InactiveChiefGrantNeedle", assignee=None)
    db.add(
        Membership(
            user_id=world.users["reviewer"].id, journal_id=world.journal.id, role="chief_editor"
        )
    )
    db.commit()
    login("reviewer")
    me = client.get("/api/auth/me").json()
    assert me["user"]["role"] == "chief_editor"
    response = client.post(
        "/api/auth/identity", json={"role": "reviewer", "request_id": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    assert not ids(results(client, "InactiveChiefGrantNeedle"), "manuscript")
    assert manuscript.id not in ids(results(client, manuscript.id), "manuscript")


@pytest.mark.parametrize("role", ["editor", "chief_editor", "author", "reviewer"])
def test_no_workflow_legacy_policy_and_links_are_preserved(client, login, db, world, role):
    old = legacy(db, world, "LegacyScopeNeedle")
    legacy(db, world, "LegacyScopeNeedle foreign", journal=world.other_journal)
    db.commit()
    login(role)
    found = results(client, "LegacyScopeNeedle")
    assert ids(found, "manuscript") == ({old.id} if role != "reviewer" else set())
    if role != "reviewer":
        assert group(found, "manuscript")["items"][0]["href"] == f"/?manuscript={old.id}"


def test_legacy_without_editor_is_searchable_and_its_authorized_link_loads(
    client, login, db, world
):
    old = legacy(db, world, "LegacyUnassignedEditorNeedle")
    old.editor_id = None
    db.commit()
    login()
    found = results(client, "#" + old.id[:12])
    assert group(found, "manuscript")["items"] == [
        {"id": old.id, "title": old.title, "href": f"/?manuscript={old.id}"}
    ]
    opened = client.get(f"/api/manuscripts/{old.id}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["editor_name"] == ""


def test_dossiers_are_staff_creator_only_and_search_only_the_current_title(
    client, login, db, world
):
    login()
    dossier = create_dossier(client, title="DossierHistoricalNeedle")
    dossier = save_dossier(
        client, dossier, data=dossier_metadata(title="DossierScopeNeedle personal")
    )
    assert not ids(results(client, "DossierHistoricalNeedle"), "dossier")
    assert not ids(results(client, "合成作者甲"), "dossier")
    login("chief_editor")
    other = create_dossier(client, title="DossierScopeNeedle chief")
    assert ids(results(client, "DossierScopeNeedle"), "dossier") == {other["id"]}
    login()
    found = results(client, "DossierScopeNeedle")
    assert ids(found, "dossier") == {dossier["id"]}
    assert group(found, "dossier")["items"][0]["href"] == f"/library?dossier={dossier['id']}"
    for role in ("author", "reviewer"):
        login(role)
        value = group(results(client, "DossierScopeNeedle"), "dossier")
        assert value["items"] == [] and value["has_more"] is False


def test_matching_precedes_limits_and_search_reaches_older_than_workspace_window(
    client, login, db, world
):
    old, _, _, _ = formal(db, world, "OldBeyondWindowNeedle", at=now() - timedelta(days=1))
    for index in range(205):
        formal(db, world, f"RecentUnrelated {index}")
    db.commit()
    login()
    listed = client.get("/api/publishing/workspace").json()
    assert old.id not in {row["id"] for row in listed["submissions"]}
    assert ids(results(client, "OldBeyondWindowNeedle", 1), "manuscript") == {old.id}


def test_each_group_is_bounded_and_unreadable_rows_do_not_set_has_more(client, login, db, world):
    for index in range(4):
        conversation(db, world, f"BoundedNeedle {index}")
        formal(db, world, f"BoundedNeedle {index}")
    for index in range(5):
        conversation(db, world, f"PrivateOnlyNeedle {index}", user="author")
        formal(db, world, f"PrivateOnlyNeedle {index}", assignee=None)
    db.commit()
    login()
    for index in range(4):
        create_dossier(client, title=f"BoundedNeedle {index}")
    login("chief_editor")
    create_dossier(client, title="PrivateOnlyNeedle other creator")
    login()
    for kind in ("conversation", "manuscript", "dossier"):
        found = group(results(client, "BoundedNeedle", 2), kind)
        assert len(found["items"]) == 2 and found["has_more"] is True
        hidden = group(results(client, "PrivateOnlyNeedle", 2), kind)
        assert hidden["items"] == [] and hidden["has_more"] is False


def test_reviewer_matches_only_personal_invitation_snapshot_not_current_raw_title(
    client, login, db, world
):
    mid = reviewer_selection(client, login, world)
    staff = open_round(client, mid, world)
    flow = db.get(SubmissionWorkflow, mid)
    current = ManuscriptVersion(
        manuscript_id=mid,
        version_no=2,
        title="FutureRawTitleNeedle",
        created_by=world.users["author"].id,
    )
    db.add(current)
    db.flush()
    flow.current_version_id = current.id
    db.get(Manuscript, mid).title = "FutureManuscriptTitleNeedle"
    db.commit()
    login("reviewer")
    invitation_title = staff["title"]
    found = results(client, mid)
    item = group(found, "manuscript")["items"][0]
    assert item["id"] == mid and item["title"] == invitation_title
    # Number is explicitly visible in reviewer_projection; the title is the
    # personal invitation snapshot, not either current raw metadata title.
    assert ids(results(client, flow.number), "manuscript") == {mid}
    assert ids(results(client, "#" + mid[:12]), "manuscript") == {mid}
    for query in (
        "FutureRawTitleNeedle",
        "FutureManuscriptTitleNeedle",
        world.users["author"].name,
    ):
        assert not ids(results(client, query), "manuscript")


@pytest.mark.usefixtures("production")
def test_production_matches_only_accepted_frozen_title(client, login, db, world):
    mid = accepted(client, login, world)
    current = client.get(f"/api/publishing/manuscripts/{mid}").json()
    title = current["production"]["metadata_snapshot"]["title"]
    flow = db.get(SubmissionWorkflow, mid)
    future = ManuscriptVersion(
        manuscript_id=mid,
        version_no=2,
        title="ProductionUnacceptedNeedle",
        created_by=world.users["author"].id,
    )
    db.add(future)
    db.flush()
    flow.current_version_id = future.id
    db.get(Manuscript, mid).title = "ProductionFallbackNeedle"
    db.commit()
    found = results(client, mid)
    assert group(found, "manuscript")["items"] == [
        {"id": mid, "title": title, "href": f"/publishing?manuscript={mid}"}
    ]
    assert not ids(results(client, "ProductionUnacceptedNeedle"), "manuscript")
    assert not ids(results(client, "ProductionFallbackNeedle"), "manuscript")
    db.execute(
        update(Assignment)
        .where(Assignment.manuscript_id == mid, Assignment.capability == "production")
        .values(ends_at=now() - timedelta(seconds=1))
    )
    db.add(
        Assignment(
            manuscript_id=mid,
            journal_id=world.journal.id,
            user_id=world.users["production_editor"].id,
            capability="author",
        )
    )
    db.commit()
    assert not ids(results(client, mid), "manuscript")


def test_reads_are_bounded_and_never_change_business_or_audit_rows(client, login, db, world):
    conversation(db, world, "ReadonlyNeedle")
    formal(db, world, "ReadonlyNeedle")
    db.commit()
    login()
    models = (AuditEvent, Manuscript, Conversation, LoginSession)
    before = [db.scalar(select(func.count()).select_from(model)) for model in models]
    queries = []

    def record_query(*args):
        queries.append(True)

    connection = db.connection()
    event.listen(connection, "before_cursor_execute", record_query)
    try:
        response = results(client, "ReadonlyNeedle")
    finally:
        event.remove(connection, "before_cursor_execute", record_query)
    assert all(
        set(item) == {"id", "title", "href"}
        for part in response["groups"]
        for item in part["items"]
    )
    assert len(queries) <= 12
    after = [db.scalar(select(func.count()).select_from(model)) for model in models]
    assert after == before


def test_session_revoked_during_search_discards_all_read_results(
    client, login, db, world, monkeypatch
):
    conversation(db, world, "RevokedSearchNeedle")
    db.commit()
    login()
    original = search_module._conversation_rows

    def read_then_revoke(database, actor, tokens, limit):
        rows = original(database, actor, tokens, limit)
        database.execute(
            update(LoginSession)
            .where(
                LoginSession.token_hash == token_digest(client.cookies.get("publishing_session"))
            )
            .values(expires_at=now() - timedelta(seconds=1))
            .execution_options(synchronize_session=False)
        )
        return rows

    monkeypatch.setattr(search_module, "_conversation_rows", read_then_revoke)
    response = client.get(URL, params={"q": "RevokedSearchNeedle"})
    assert response.status_code == 403
    assert "RevokedSearchNeedle" not in response.text
