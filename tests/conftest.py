"""Shared pytest fixtures for NeuraDesk.

Env vars are set at the very top — before any project imports — so that
module-level reads (ENTERPRISE_API_SECRET, LANGCHAIN_TRACING_V2, etc.)
pick up test values when the modules are first imported by a fixture.
"""

import os

os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("ENTERPRISE_API_SECRET", "test-enterprise-secret")
os.environ.setdefault("API_SECRET_KEY", "test-api-secret-key-32chars!!")
os.environ.setdefault("ENTERPRISE_API_URL", "http://localhost:8001")

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.main import app
from api.models import Base, get_db

# ── Fixed TicketState returned by mock_run_ticket ─────────────────────────────

_MOCK_TICKET_STATE: dict = {
    "ticket_id": "mock-ticket-0001",
    "user_id": "mock-user-id",
    "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    "trace_id": "mock-trace-id",
    "channel": "text",
    "raw_text": "I forgot my password",
    "raw_image_b64": None,
    "extracted_text": None,
    "category": "password_reset",
    "intent": "password_reset",
    "priority": "MEDIUM",
    "confidence": 0.92,
    "entities": {"username": "mock-user-id"},
    "retrieved_chunks": [{"source": "kb/test.md", "content": "Test chunk", "score": 0.9}],
    "resolution_template": "Password reset initiated for {username} via IT Portal.",
    "action_taken": "password_reset_executed",
    "action_result": {"status": "ok", "data": {"temp_password": "Stub!"}},
    "action_confirmed": True,
    "resolution": "Password reset initiated for mock-user-id via IT Portal.",
    "escalated": None,
    "escalation_reason": None,
    "assignee_group": None,
    "status": "resolved",
    "error": None,
    "trace_url": None,
}


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_engine(tmp_path):
    """Fresh SQLite engine + all tables, dropped and disposed after each test."""
    db_file = tmp_path / "neuradesk_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def override_db(db_engine):
    """Override the FastAPI get_db dependency with the isolated test engine.

    Both test_client and auth_client depend on this fixture. Because fixtures
    are cached within their scope, a single test that uses both clients shares
    the same engine (and therefore the same database).
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def _test_get_db():
        """Yield a test-scoped DB session."""
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _test_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


# ── API clients ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def test_client(override_db) -> TestClient:
    """Unauthenticated FastAPI TestClient backed by an isolated SQLite DB."""
    return TestClient(app)


@pytest.fixture(scope="function")
def auth_client(override_db) -> TestClient:
    """FastAPI TestClient with a valid JWT pre-set in the Authorization header.

    Registers 'auth-fixture@neuradesk.ai' and stores the token in the
    session headers so every request is automatically authenticated as that user.
    """
    client = TestClient(app)
    r = client.post(
        "/auth/register",
        json={"email": "auth-fixture@neuradesk.ai", "password": "testpassword99"},
    )
    assert r.status_code == 201, f"auth_client fixture registration failed: {r.text}"
    token = r.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ── Enterprise API client ─────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def enterprise_client() -> TestClient:
    """TestClient for the mock enterprise API.

    The ENTERPRISE_API_SECRET env var is already set at the top of this file,
    so the module-level _SECRET in enterprise_api.py is correct on first import.
    """
    from services.enterprise_api import app as ea_app
    return TestClient(ea_app)


@pytest.fixture(scope="session")
def enterprise_token() -> str:
    """Bearer token that matches ENTERPRISE_API_SECRET for the test session."""
    return "test-enterprise-secret"


# ── Payload fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_ticket_payload() -> dict:
    """Minimal valid POST /tickets request body."""
    return {"text": "I forgot my password"}


@pytest.fixture(scope="session")
def sample_image_ticket_payload() -> dict:
    """POST /tickets body carrying a 1×1 white PNG in base-64."""
    return {
        "text": "Screenshot showing login error",
        # 1×1 white PNG, base-64 encoded
        "image_b64": (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        ),
    }


# ── Graph mock ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def mock_run_ticket():
    """Patch api.main.run_ticket to return a deterministic resolved TicketState.

    API tests use this so they are isolated from graph logic and run fast.
    """
    with patch("api.main.run_ticket", return_value=_MOCK_TICKET_STATE):
        yield


# ── Enterprise API HTTP mock ──────────────────────────────────────────────────

_DEFAULT_ENTERPRISE_RESPONSE: dict = {
    "success": True,
    "action": "stub",
    "destructive": False,
    "result": {
        "status": "ok",
        "temp_password": "TestTmp-abc123!",
        "ticket_ref": "TEST-000001",
    },
    "timestamp": "2026-01-01T00:00:00+00:00",
}


@pytest.fixture(autouse=True)
def _mock_enterprise_http():
    """Prevent real HTTP calls from action_node in every test.

    tests/test_action_node.py overrides _post_enterprise per test with its own
    patch — that patch shadows this one within the test's scope.
    """
    with patch(
        "agents.action_node._post_enterprise",
        return_value=_DEFAULT_ENTERPRISE_RESPONSE,
    ):
        yield
