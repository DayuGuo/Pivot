"""Real PostgreSQL tests. Each HTTP test rolls back its own outer transaction.

Application commits/rollbacks only touch savepoints. No TRUNCATE or demo-data deletion.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.publishing.db import engine, get_db
from apps.api.publishing.main import app
from apps.api.publishing.models import Journal, Membership, User
from apps.api.publishing.security import hash_password

PASSWORD = "TestOnly2026!"
PROMPT = "创建一篇测试稿件，并交给编辑初筛。"


@pytest.fixture(autouse=True)
def isolated_model_configuration(monkeypatch):
    # API regression must never call a real provider because a developer exported a key.
    monkeypatch.setenv("EDITORIAL_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("EDITORIAL_MODEL_LIVE_ENABLED", "false")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def world(db):
    suffix = uuid4().hex
    journal = Journal(name=f"Pytest isolated {suffix}")
    other_journal = Journal(name=f"Pytest other {suffix}")
    db.add_all([journal, other_journal])
    db.flush()
    users = {}
    for role in ("editor", "chief_editor", "author", "reviewer"):
        user = User(
            email=f"{role}-{suffix}@publishing.test",
            name=f"测试 {role}",
            password_hash=hash_password(PASSWORD),
        )
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, journal_id=journal.id, role=role))
        users[role] = user
    # The tool intentionally uses only the designated synthetic author.
    synthetic_author = db.scalar(select(User).where(User.email == "author@publishing.test"))
    if synthetic_author is None:
        synthetic_author = User(
            email="author@publishing.test", name="合成作者", password_hash=hash_password(PASSWORD)
        )
        db.add(synthetic_author)
        db.flush()
    db.add(Membership(user_id=synthetic_author.id, journal_id=journal.id, role="author"))
    db.commit()
    return SimpleNamespace(
        journal=journal, other_journal=other_journal, users=users, synthetic_author=synthetic_author
    )


@pytest.fixture
def client(db, world):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def login(client, world):
    def authenticate(role="editor"):
        response = client.post(
            "/api/auth/login", json={"email": world.users[role].email, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        client.headers["X-CSRF-Token"] = data["csrf_token"]
        return data

    return authenticate
