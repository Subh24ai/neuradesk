"""TicketState — the single TypedDict threaded through every LangGraph node."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    raw_image_b64: str | None            # base-64 encoded image (if channel=="image")
    extracted_text: str | None           # vision-model OCR output

    # ── Intake node output ────────────────────────────────────────────────
    category: Literal["password_reset", "access_request", "software_install", "leave_approval", "incident_report", "access_revoke", "account_lock", "account_delete", "unknown"] | None
    intent: str | None                   # e.g. "password_reset"
    priority: str | None                 # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    confidence: float | None             # triage confidence 0.0–1.0
    entities: dict[str, str] | None      # {"username": "jdoe", ...}

    # ── Knowledge node output ─────────────────────────────────────────────
    retrieved_chunks: list[RetrievedChunk] | None
    resolution_template: str | None
    kb_grounded: bool | None             # True when a KB passage cleared the relevance threshold

    # ── Action node output ────────────────────────────────────────────────
    action_taken: str | None             # e.g. "password_reset_executed"
    action_result: dict[str, Any] | None # raw API response
    action_confirmed: bool | None        # explicit confirmation for destructive ops
    resolution: str | None              # human-readable resolution summary

    # ── Escalation node output ────────────────────────────────────────────
    escalated: bool | None
    escalation_reason: str | None
    assignee_group: str | None

    # ── Org context (populated before graph run from DB) ──────────────────
    org_id: str | None
    org_name: str | None             # human-readable org name for notifications
    org_kb_docs: list[dict] | None   # [{title, content}] from OrgKnowledgeDocModel
    org_api_url: str | None          # per-org enterprise API base URL override
    support_email: str | None        # support team email for escalation alerts
    user_email: str | None           # submitting user's email for notifications
    slack_webhook_url: str | None    # org Slack webhook URL for escalation alerts

    # ── Graph control ─────────────────────────────────────────────────────
    status: Literal["triaging", "retrieving", "acting", "resolved", "escalated", "awaiting_confirmation"]
    error: str | None
    trace_url: str | None
