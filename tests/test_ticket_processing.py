"""Tests for connection-independent ticket processing (claim + _process_ticket).

Proves a ticket is processed to a terminal state with no WebSocket involved —
the decoupling that lets API clients and dropped connections still resolve.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.main as main_mod
import api.models as models_mod
from api.main import _claim_ticket, _process_ticket
from api.models import Base, OrganizationModel, TicketModel, UserModel


@pytest.fixture()
def processing_db(monkeypatch, tmp_path):
    """Point the module-level SessionLocal(s) at an isolated DB and seed a ticket."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proc.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(main_mod, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(models_mod, "SessionLocal", TestingSessionLocal)

    db = TestingSessionLocal()
    org = OrganizationModel(name="Proc Org", slug="proc-org", invite_code="proc-invite-123")
    db.add(org)
    db.flush()
    user = UserModel(
        email="worker-user@corp.com", hashed_password="x",
        is_verified=True, org_id=org.id, role="member",
    )
    db.add(user)
    db.flush()
    ticket = TicketModel(
        id="tkt-proc-001", user_id=user.id, org_id=org.id,
        raw_text="I forgot my password", channel="text", status="pending",
        created_at=datetime.now(UTC),
    )
    db.add(ticket)
    db.commit()
    db.close()
    return TestingSessionLocal


def test_claim_is_atomic_and_single_winner(processing_db) -> None:
    """Only the first _claim_ticket wins; a second call fails (no double-run)."""
    assert _claim_ticket("tkt-proc-001") is True
    assert _claim_ticket("tkt-proc-001") is False  # already 'processing'

    db = processing_db()
    try:
        assert db.get(TicketModel, "tkt-proc-001").status == "processing"
    finally:
        db.close()


def test_claim_missing_ticket_returns_false(processing_db) -> None:
    """Claiming a non-existent ticket does not raise and returns False."""
    assert _claim_ticket("does-not-exist") is False


@pytest.mark.asyncio
async def test_process_ticket_resolves_without_websocket(processing_db) -> None:
    """_process_ticket runs the full graph and persists a terminal result — no WS."""
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="Reset your password for {username}.")

    fake_retriever = MagicMock()
    fake_retriever.search.return_value = [
        {"source": "password-reset-runbook.md", "content": "Reset via the IT portal.", "score": 0.9},
    ]

    enterprise_ok = {"success": True, "action": "reset-password", "result": {"ref": "PWD-ABC"}}

    assert _claim_ticket("tkt-proc-001") is True
    with patch("agents.intake_node.classify", return_value=("password_reset", 0.95)), \
         patch("agents.knowledge_node.get_retriever", return_value=fake_retriever), \
         patch("agents.knowledge_node.get_llm", return_value=fake_llm), \
         patch("agents.action_node._post_enterprise", new_callable=AsyncMock, return_value=enterprise_ok):
        result = await _process_ticket("tkt-proc-001")

    assert result["status"] == "resolved"

    db = processing_db()
    try:
        t = db.get(TicketModel, "tkt-proc-001")
        assert t.status == "resolved"
        assert t.category == "password_reset"
        assert t.resolution is not None
    finally:
        db.close()
