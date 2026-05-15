"""TicketState — the single TypedDict threaded through every LangGraph node."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from typing_extensions import TypedDict


class RetrievedChunk(TypedDict):
    """One document chunk returned by the RAG pipeline."""

    source: str
    content: str
    score: float


class TicketState(TypedDict):
    # ── Identity ──────────────────────────────────────────────────────────
    ticket_id: str                          # UUID, generated at intake
    user_id: str
    created_at: datetime
    trace_id: str                           # LangSmith run ID

    # ── Raw input ─────────────────────────────────────────────────────────
    channel: Literal["text", "image"]
    raw_text: str                           # original text from user
    raw_image_b64: Optional[str]            # base-64 encoded image (if channel=="image")
    extracted_text: Optional[str]           # vision-model OCR output

    # ── Intake node output ────────────────────────────────────────────────
    category: Optional[Literal[
        "password_reset", "access_request", "software_install",
        "leave_approval", "incident_report", "unknown",
    ]]
    intent: Optional[str]                   # e.g. "password_reset"
    priority: Optional[str]                 # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    confidence: Optional[float]             # triage confidence 0.0–1.0
    entities: Optional[dict[str, str]]      # {"username": "jdoe", ...}

    # ── Knowledge node output ─────────────────────────────────────────────
    retrieved_chunks: Optional[list[RetrievedChunk]]
    resolution_template: Optional[str]

    # ── Action node output ────────────────────────────────────────────────
    action_taken: Optional[str]             # e.g. "password_reset_executed"
    action_result: Optional[dict[str, Any]] # raw API response
    action_confirmed: Optional[bool]        # explicit confirmation for destructive ops
    resolution: Optional[str]              # human-readable resolution summary

    # ── Escalation node output ────────────────────────────────────────────
    escalated: Optional[bool]
    escalation_reason: Optional[str]
    assignee_group: Optional[str]

    # ── Graph control ─────────────────────────────────────────────────────
    status: Literal["triaging", "retrieving", "acting", "resolved", "escalated"]
    error: Optional[str]
    trace_url: Optional[str]
