"""Intake node — DSPy triage + Groq vision for multimodal IT/HR tickets."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from agents.state import TicketState
from dspy_modules.triage import classify
from tracing.langsmith import traceable

log = structlog.get_logger(__name__)

_GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"

_CRITICAL_KEYWORDS: frozenset[str] = frozenset({
    "outage", "down", "critical", "crashed", "breach", "attack", "emergency",
})

_PRIORITY_MAP: dict[str, str] = {
    "incident_report": "HIGH",
    "access_request": "MEDIUM",
    "software_install": "MEDIUM",
    "password_reset": "MEDIUM",
    "leave_approval": "LOW",
    "unknown": "MEDIUM",
}

_KNOWN_SOFTWARE: frozenset[str] = frozenset({
    "adobe", "confluence", "docker", "excel", "github", "gitlab",
    "intellij", "jira", "notion", "outlook", "postman", "python",
    "salesforce", "slack", "tableau", "teams", "vs code", "vscode",
    "word", "zoom",
})


# ── Vision extraction ─────────────────────────────────────────────────────────


def _extract_text_from_image(image_b64: str, api_key: str) -> str:
    """Call the Groq vision model to extract an issue description from a screenshot.

    Args:
        image_b64: Base-64 encoded image bytes (PNG or JPEG).
        api_key: Groq API key.

    Returns:
        Extracted issue description string, or empty string on any error.
    """
    try:
        from groq import Groq  # type: ignore[import-untyped]

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=_GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are an IT/HR helpdesk assistant. "
                                "Describe the specific IT or HR issue visible in this screenshot. "
                                "Be concise (1–2 sentences). Focus on error messages and the user's problem."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        log.exception("intake_node.vision_error", error=str(exc))
        return ""


# ── Entity extraction ─────────────────────────────────────────────────────────


def _extract_entities(text: str) -> dict[str, str]:
    """Extract structured entities from ticket text using regex patterns.

    Extracts username (email address), date (first date or range), and
    software name (first recognised tool from _KNOWN_SOFTWARE).

    Args:
        text: Raw ticket or vision-extracted text.

    Returns:
        Dict of entity name → extracted value.  Keys present only when found.
    """
    entities: dict[str, str] = {}

    email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    if email:
        entities["username"] = email.group()

    date = re.search(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2}(?:\s+(?:to|-)\s+\w+\s+\d{1,2})?|\b\d{4}-\d{2}-\d{2}\b",
        text,
        re.IGNORECASE,
    )
    if date:
        entities["date"] = date.group()

    text_lower = text.lower()
    for sw in sorted(_KNOWN_SOFTWARE):  # sorted for deterministic first-match
        if sw in text_lower:
            entities["software"] = sw
            break

    return entities


# ── Priority assignment ───────────────────────────────────────────────────────


def _assign_priority(category: str, text: str) -> str:
    """Assign ticket priority from category and keyword signals.

    Critical keywords in the text override the category-based default.

    Args:
        category: Classified ticket category.
        text: Ticket text to scan for severity keywords.

    Returns:
        One of "CRITICAL", "HIGH", "MEDIUM", "LOW".
    """
    if any(kw in text.lower() for kw in _CRITICAL_KEYWORDS):
        return "CRITICAL"
    return _PRIORITY_MAP.get(category, "MEDIUM")


# ── Node ──────────────────────────────────────────────────────────────────────


@traceable(name="intake_node", run_type="chain", metadata={"agent": "intake", "version": "1.0"})
def intake_node(state: TicketState) -> TicketState:
    """Classify the ticket, extract entities, and assign priority.

    For image-channel tickets, calls the Groq vision model to extract a
    text description before classification.  If GROQ_API_KEY is absent, falls
    back to using raw_text as-is with a warning log.

    Reads:  channel, raw_text, raw_image_b64, ticket_id, trace_id
    Writes: ticket_id, created_at, category, intent, priority, confidence,
            entities, extracted_text, status
    """
    log.info("intake_node.start", ticket_id=state.get("ticket_id"))

    channel: str = state.get("channel") or "text"
    raw_text: str = state.get("raw_text") or ""
    raw_image_b64: Optional[str] = state.get("raw_image_b64")
    extracted_text: Optional[str] = None

    # ── Vision extraction ──────────────────────────────────────────────────────
    if channel == "image" and raw_image_b64:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            log.warning(
                "intake_node.vision_fallback",
                reason="GROQ_API_KEY not set — using raw_text as extracted_text",
            )
            extracted_text = raw_text
        else:
            result = _extract_text_from_image(raw_image_b64, api_key)
            extracted_text = result if result else raw_text

    # Prefer vision output over raw text for classification.
    classify_text: str = extracted_text if extracted_text is not None else raw_text

    # ── DSPy classification ────────────────────────────────────────────────────
    category, confidence = classify(classify_text)

    # ── Entities + priority ───────────────────────────────────────────────────
    entities = _extract_entities(classify_text)
    priority = _assign_priority(category, classify_text)

    updates: dict = {
        "ticket_id": state.get("ticket_id") or str(uuid.uuid4()),
        "created_at": state.get("created_at") or datetime.now(timezone.utc),
        "category": category,
        "intent": category,
        "priority": priority,
        "confidence": confidence,
        "entities": entities,
        "extracted_text": extracted_text,
        "status": "retrieving",
    }

    log.info(
        "intake_node.done",
        category=category,
        confidence=confidence,
        priority=priority,
        ticket_id=updates["ticket_id"],
    )
    return {**state, **updates}  # type: ignore[return-value]
