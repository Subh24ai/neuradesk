"""Tests for the A2A (Agent-to-Agent) protocol endpoints.

Covers:
- GET  /.well-known/agent.json   — AgentCard schema
- POST /tasks/send               — sync task execution
- POST /tasks/sendSubscribe      — SSE stream: asserts exact event order

All tests use the autouse _mock_enterprise_http fixture from conftest.py
and additionally patch api.a2a._run_knowledge_query to avoid real LLM calls.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

_MOCK_QUERY_RESULT = (
    "Navigate to the IT Self-Service Portal to reset your password.",
    [{"source": "kb/password-reset.md", "content": "Reset via IT Portal.", "score": 0.95}],
)

_TASK_PAYLOAD: dict[str, Any] = {
    "id": "test-task-001",
    "sessionId": "test-session-001",
    "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "How do I reset my corporate password?"}],
    },
}

_EMPTY_PARTS_PAYLOAD: dict[str, Any] = {
    "id": "test-task-002",
    "sessionId": "test-session-002",
    "message": {"role": "user", "parts": []},
}


def _parse_sse_events(raw: str) -> list[dict[str, Any]]:
    """Parse raw SSE response body into a list of JSON event dicts.

    Each SSE event is a 'data: <json>\\n\\n' block.
    """
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


# ── Agent Card ────────────────────────────────────────────────────────────────


class TestAgentCard:
    """GET /.well-known/agent.json"""

    def test_agent_card_returns_200(self, test_client) -> None:
        """Agent card endpoint is reachable without authentication."""
        r = test_client.get("/.well-known/agent.json")
        assert r.status_code == 200

    def test_agent_card_has_required_fields(self, test_client) -> None:
        """AgentCard contains all required top-level A2A fields."""
        card = test_client.get("/.well-known/agent.json").json()
        for field in ("name", "description", "url", "version", "capabilities", "skills"):
            assert field in card, f"Missing required field: {field}"

    def test_agent_card_streaming_capability(self, test_client) -> None:
        """AgentCard declares streaming=True."""
        card = test_client.get("/.well-known/agent.json").json()
        assert card["capabilities"]["streaming"] is True

    def test_agent_card_has_at_least_one_skill(self, test_client) -> None:
        """AgentCard contains at least one skill with id, name, description."""
        card = test_client.get("/.well-known/agent.json").json()
        assert len(card["skills"]) >= 1
        skill = card["skills"][0]
        for field in ("id", "name", "description"):
            assert field in skill, f"Skill missing field: {field}"

    def test_agent_card_url_matches_base_url(self, test_client) -> None:
        """AgentCard 'url' field is populated (not empty)."""
        card = test_client.get("/.well-known/agent.json").json()
        assert card["url"]


# ── Synchronous task endpoint ─────────────────────────────────────────────────


class TestTaskSend:
    """POST /tasks/send"""

    def test_task_send_returns_completed(self, test_client) -> None:
        """Valid query returns status.state == 'completed' with an artifact."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            r = test_client.post("/tasks/send", json=_TASK_PAYLOAD, headers={"Authorization": "Bearer test-key"})

        assert r.status_code == 200
        body = r.json()
        assert body["status"]["state"] == "completed"

    def test_task_send_artifact_contains_answer(self, test_client) -> None:
        """Resolution text appears in the first artifact's text part."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            r = test_client.post("/tasks/send", json=_TASK_PAYLOAD, headers={"Authorization": "Bearer test-key"})

        artifact = r.json()["artifacts"][0]
        text = artifact["parts"][0]["text"]
        assert "IT Self-Service Portal" in text

    def test_task_send_metadata_includes_sources(self, test_client) -> None:
        """Response metadata lists source document paths."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            r = test_client.post("/tasks/send", json=_TASK_PAYLOAD, headers={"Authorization": "Bearer test-key"})

        meta = r.json()["metadata"]
        assert meta["chunks_retrieved"] == 1
        assert "kb/password-reset.md" in meta["sources"]

    def test_task_send_empty_parts_returns_failed(self, test_client) -> None:
        """Message with no text parts returns status.state == 'failed'."""
        r = test_client.post("/tasks/send", json=_EMPTY_PARTS_PAYLOAD, headers={"Authorization": "Bearer test-key"})
        assert r.json()["status"]["state"] == "failed"

    def test_task_send_echoes_task_id(self, test_client) -> None:
        """Response id matches the submitted task id."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            r = test_client.post("/tasks/send", json=_TASK_PAYLOAD, headers={"Authorization": "Bearer test-key"})
        assert r.json()["id"] == "test-task-001"


# ── SSE streaming task endpoint ───────────────────────────────────────────────


class TestTaskSendSubscribe:
    """POST /tasks/sendSubscribe — exact SSE event sequence."""

    def _get_events(self, test_client, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Consume the full SSE response and return the parsed event list."""
        with test_client.stream("POST", "/tasks/sendSubscribe", json=payload, headers={"Authorization": "Bearer test-key"}) as resp:
            assert resp.status_code == 200
            raw = resp.read().decode()
        return _parse_sse_events(raw)

    def test_sse_event_count(self, test_client) -> None:
        """Happy path produces exactly 3 events: working, artifact, completed."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        assert len(events) == 3

    def test_sse_first_event_is_working(self, test_client) -> None:
        """First SSE event has status.state == 'working'."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        assert events[0]["status"]["state"] == "working"

    def test_sse_second_event_is_artifact(self, test_client) -> None:
        """Second SSE event contains an 'artifact' key (not 'status')."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        assert "artifact" in events[1]
        assert "status" not in events[1]

    def test_sse_artifact_contains_resolution_text(self, test_client) -> None:
        """Artifact event's text part contains the mocked resolution."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        artifact_text = events[1]["artifact"]["parts"][0]["text"]
        assert "IT Self-Service Portal" in artifact_text

    def test_sse_last_event_is_completed_and_final(self, test_client) -> None:
        """Last SSE event has status.state == 'completed' and final == True."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        last = events[-1]
        assert last["status"]["state"] == "completed"
        assert last.get("final") is True

    def test_sse_working_arrives_before_artifact(self, test_client) -> None:
        """'working' event index is strictly less than 'artifact' event index."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)

        working_idx = next(
            i for i, e in enumerate(events) if e.get("status", {}).get("state") == "working"
        )
        artifact_idx = next(i for i, e in enumerate(events) if "artifact" in e)
        assert working_idx < artifact_idx

    def test_sse_artifact_arrives_before_completed(self, test_client) -> None:
        """'artifact' event index is strictly less than 'completed' event index."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)

        artifact_idx = next(i for i, e in enumerate(events) if "artifact" in e)
        completed_idx = next(
            i for i, e in enumerate(events) if e.get("status", {}).get("state") == "completed"
        )
        assert artifact_idx < completed_idx

    def test_sse_empty_query_emits_working_then_failed(self, test_client) -> None:
        """Empty query SSE stream: first event is 'working', last is 'failed' with final=True."""
        events = self._get_events(test_client, _EMPTY_PARTS_PAYLOAD)
        assert events[0]["status"]["state"] == "working"
        assert events[-1]["status"]["state"] == "failed"
        assert events[-1].get("final") is True

    def test_sse_all_events_share_task_id(self, test_client) -> None:
        """Every SSE event carries the same task id as the submitted task."""
        with patch("api.a2a._run_knowledge_query", return_value=_MOCK_QUERY_RESULT):
            events = self._get_events(test_client, _TASK_PAYLOAD)
        assert all(e.get("id") == "test-task-001" for e in events)
