"""Tests for the DB-backed admin SSE fan-out (cross-worker correctness)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import api.models as models
from api.admin import _publish_sse, _sse_event_stream
from api.models import AdminEventModel, Base


@pytest.fixture()
def sse_session(monkeypatch, tmp_path):
    """Point the module-level SessionLocal at an isolated DB with admin_events."""
    engine = create_engine(f"sqlite:///{tmp_path / 'sse.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # _publish_sse / _sse_event_stream import SessionLocal from api.models at call time.
    monkeypatch.setattr(models, "SessionLocal", TestingSessionLocal)
    yield TestingSessionLocal
    engine.dispose()


def test_publish_persists_event(sse_session) -> None:
    """_publish_sse writes a durable row any worker can read."""
    _publish_sse("org-123", {"ticket_id": "t1", "status": "resolved"})
    db = sse_session()
    try:
        rows = db.query(AdminEventModel).filter(AdminEventModel.org_id == "org-123").all()
    finally:
        db.close()
    assert len(rows) == 1
    assert json.loads(rows[0].payload)["status"] == "resolved"


def test_publish_isolates_by_org(sse_session) -> None:
    """An admin only ever streams their own org's events."""
    _publish_sse("org-a", {"ticket_id": "a1"})
    _publish_sse("org-b", {"ticket_id": "b1"})
    db = sse_session()
    try:
        a = db.query(AdminEventModel).filter(AdminEventModel.org_id == "org-a").all()
    finally:
        db.close()
    assert len(a) == 1
    assert json.loads(a[0].payload)["ticket_id"] == "a1"


@pytest.mark.asyncio
async def test_stream_delivers_published_event(sse_session) -> None:
    """A published event is delivered to a polling SSE stream (proves cross-worker path)."""
    _publish_sse("org-x", {"ticket_id": "tx", "status": "escalated"})
    gen = _sse_event_stream("org-x", start_after_id=0)
    frame = await gen.__anext__()  # first poll returns the backlog immediately
    await gen.aclose()
    assert frame.startswith("data: ")
    assert json.loads(frame[len("data: "):].strip())["ticket_id"] == "tx"
