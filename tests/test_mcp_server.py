"""Tests for the NeuraDesk MCP tool server — one test per tool.

Each tool is invoked over a real in-memory MCP client/server round-trip
(create_connected_server_and_client_session), not by calling the function
directly, so the registered schema and serialization are exercised too.
"""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import mcp_server
from api.models import Base, TicketModel
from dspy_modules.triage import VALID_CATEGORIES


async def _call(client, name: str, args: dict) -> dict:
    """Call an MCP tool and return its parsed JSON payload."""
    res = await client.call_tool(name, args)
    assert res.isError is False, f"{name} returned an error: {res.content}"
    return json.loads(res.content[0].text)


@pytest.fixture()
def seeded_db(monkeypatch, tmp_path):
    """Point mcp_server at an isolated sqlite DB seeded with one ticket."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'mcp_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSessionLocal()
    db.add(
        TicketModel(
            id="mcp-test-ticket-1",
            user_id="u1",
            raw_text="I forgot my password",
            channel="text",
            status="resolved",
            category="password_reset",
            intent="password_reset",
            confidence=0.95,
            resolution="Reset your password via the IT Self-Service Portal.",
            priority="MEDIUM",
        )
    )
    db.commit()
    db.close()

    monkeypatch.setattr(mcp_server, "_session_factory", TestingSessionLocal)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.mark.asyncio
async def test_list_ticket_categories() -> None:
    """Returns all VALID_CATEGORIES, each with a description."""
    async with connect(mcp_server.mcp._mcp_server) as client:
        data = await _call(client, "list_ticket_categories", {})

    cats = data["categories"]
    assert {c["category"] for c in cats} == set(VALID_CATEGORIES)
    assert all(c["description"] for c in cats)


@pytest.mark.asyncio
async def test_search_knowledge() -> None:
    """Returns up to 3 chunks, each with source/content/score (global KB only)."""
    async with connect(mcp_server.mcp._mcp_server) as client:
        data = await _call(
            client,
            "search_knowledge",
            {"query": "how do I reset my corporate password", "org_id": ""},
        )

    assert data["query"]
    results = data["results"]
    assert isinstance(results, list) and 0 < len(results) <= 3
    for r in results:
        assert set(r) >= {"source", "content", "score"}


@pytest.mark.asyncio
async def test_resolve_ticket_info() -> None:
    """A valid category returns steps + description; an invalid one returns valid=false."""
    async with connect(mcp_server.mcp._mcp_server) as client:
        ok = await _call(client, "resolve_ticket_info", {"category": "password_reset"})
        bad = await _call(client, "resolve_ticket_info", {"category": "not_a_category"})

    assert ok["valid"] is True
    assert ok["description"]
    assert 0 < len(ok["steps"]) <= 3
    assert bad["valid"] is False
    assert bad["steps"] == []


@pytest.mark.asyncio
async def test_get_ticket_status(seeded_db) -> None:
    """A seeded ticket id returns found=true with its status; unknown id returns found=false."""
    async with connect(mcp_server.mcp._mcp_server) as client:
        found = await _call(client, "get_ticket_status", {"ticket_id": "mcp-test-ticket-1"})
        missing = await _call(client, "get_ticket_status", {"ticket_id": "does-not-exist"})

    assert found["found"] is True
    assert found["status"] == "resolved"
    assert found["category"] == "password_reset"
    assert found["resolution"]
    assert missing["found"] is False
    assert missing["ticket_id"] == "does-not-exist"
