"""Action node — calls mock enterprise APIs to fulfil resolved tickets."""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from agents.state import TicketState
from tracing.langsmith import traceable

log = structlog.get_logger(__name__)

# Intents that require explicit human confirmation before any API call.
_DESTRUCTIVE_INTENTS: frozenset[str] = frozenset({
    "access_revoke", "account_lock", "account_delete",
})

# Maps DSPy-classified intent labels to enterprise API endpoint paths.
_ENDPOINT_MAP: dict[str, str] = {
    "password_reset": "/itsm/reset-password",
    "access_request": "/itsm/provision-access",
    "leave_approval": "/hr/approve-leave",
    "incident_report": "/itsm/create-incident",
    "software_install": "/itsm/notify-manager",
}

_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "CRITICAL": "P1",
    "HIGH": "P2",
    "MEDIUM": "P3",
    "LOW": "P4",
}


@traceable(name="_post_enterprise", run_type="tool", metadata={"layer": "enterprise_api"})
def _post_enterprise(
    endpoint: str,
    payload: dict[str, Any],
    base_url: str,
    secret: str,
) -> dict[str, Any]:
    """POST payload to the enterprise API and return the parsed JSON response.

    Args:
        endpoint: Path component, e.g. "/itsm/reset-password".
        payload: Request body dict (will be JSON-serialised).
        base_url: Enterprise API base URL, e.g. "http://localhost:8001".
        secret: Bearer token for Authorization header.

    Returns:
        Parsed JSON response body.

    Raises:
        httpx.HTTPStatusError: On non-2xx responses.
        httpx.RequestError: On network-level failures.
    """
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{base_url}{endpoint}",
            json=payload,
            headers={"Authorization": f"Bearer {secret}"},
        )
        resp.raise_for_status()
        return resp.json()


def _build_payload(
    intent: str,
    state: TicketState,
    fmt: dict[str, str],
) -> dict[str, Any]:
    """Construct the request body for the enterprise API call.

    Args:
        intent: Classified ticket intent (one of _ENDPOINT_MAP keys).
        state: Full ticket state.
        fmt: Pre-built format context dict with "username" already resolved.

    Returns:
        Dict ready to be JSON-serialised into the API request body.
    """
    user_id: str = fmt.get("username") or state.get("user_id") or "unknown"
    entities: dict[str, str] = state.get("entities") or {}
    raw: str = (state.get("extracted_text") or state.get("raw_text") or "")[:500]

    if intent == "password_reset":
        return {"user_id": user_id, "email": user_id}

    if intent == "access_request":
        return {
            "user_id": user_id,
            "resource": entities.get("software", "corporate-systems"),
            "role": "reader",
        }

    if intent == "leave_approval":
        date_val: str = entities.get("date", "TBD")
        return {
            "user_id": user_id,
            "start_date": date_val,
            "end_date": date_val,
            "days": 1,
        }

    if intent == "incident_report":
        severity = _PRIORITY_TO_SEVERITY.get(state.get("priority") or "MEDIUM", "P3")
        return {
            "user_id": user_id,
            "description": raw or "No description provided",
            "severity": severity,
        }

    # software_install → /itsm/notify-manager
    return {"user_id": user_id, "message": raw or "Support requested"}


@traceable(name="action_node", run_type="chain", metadata={"agent": "action", "version": "1.0"})
def action_node(state: TicketState) -> TicketState:
    """Execute the appropriate enterprise API call for the resolved intent.

    Routing:
      - "unknown" intent → escalate immediately, no API call.
      - Destructive intents (access_revoke, account_lock, account_delete) →
        blocked until action_confirmed=True.
      - Mapped intents → POST to enterprise API via _post_enterprise().
      - Unmapped confirmed intents (legacy destructive ops) → stub resolve.

    Reads:  intent, entities, resolution_template, action_confirmed, user_id, priority
    Writes: action_taken, action_result, action_confirmed, resolution, status,
            escalated, escalation_reason, error
    """
    intent: str = state.get("intent") or "unknown"
    entities: dict[str, str] = state.get("entities") or {}

    log.info("action_node.start", ticket_id=state.get("ticket_id"), intent=intent)

    # 1. Unknown category → escalate without any API call.
    if intent == "unknown":
        log.warning("action_node.unknown_intent", ticket_id=state.get("ticket_id"))
        return {
            **state,
            "escalated": True,
            "escalation_reason": "category_unknown",
            "status": "escalated",
        }  # type: ignore[return-value]

    # 2. Destructive gate — block until caller sends action_confirmed=True.
    if intent in _DESTRUCTIVE_INTENTS and not state.get("action_confirmed"):
        log.warning("action_node.awaiting_confirmation", intent=intent)
        return {
            **state,
            "action_confirmed": False,
            "status": "escalated",
            "error": f"Destructive intent '{intent}' requires explicit confirmation.",
        }  # type: ignore[return-value]

    # 3. Build username substitution context for the resolution template.
    user_fallback: str = state.get("user_id") or "unknown"
    fmt: dict[str, str] = {"user_id": user_fallback, "username": user_fallback}
    for k, v in entities.items():
        if k == "username" and v in (None, "unknown", ""):
            continue
        fmt[k] = str(v) if v is not None else "unknown"

    resolution: str = (
        state.get("resolution_template") or "Action completed."
    ).format(**fmt)

    # 4. Call enterprise API or fall back to stub for unmapped intents.
    endpoint: str | None = _ENDPOINT_MAP.get(intent)

    try:
        if endpoint:
            base_url = os.getenv("ENTERPRISE_API_URL", "http://localhost:8001")
            secret = os.getenv("ENTERPRISE_API_SECRET", "")
            payload = _build_payload(intent, state, fmt)
            action_result: dict[str, Any] = _post_enterprise(
                endpoint, payload, base_url, secret
            )
        else:
            # Confirmed legacy destructive intent with no direct endpoint
            # (e.g. access_revoke) — acknowledge without an API call.
            action_result = {
                "status": "ok",
                "data": {"action": intent, "acknowledged": True},
            }

        updates: dict = {
            "action_taken": f"{intent}_executed",
            "action_result": action_result,
            "action_confirmed": True,
            "resolution": resolution,
            "status": "resolved",
            "error": None,
        }

        log.info(
            "action_node.done",
            action_taken=updates["action_taken"],
            ticket_id=state.get("ticket_id"),
        )
        return {**state, **updates}  # type: ignore[return-value]

    except Exception as exc:
        log.exception("action_node.error", ticket_id=state.get("ticket_id"))
        return {
            **state,
            "status": "escalated",
            "error": str(exc),
        }  # type: ignore[return-value]
