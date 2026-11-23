"""Action node — calls mock enterprise APIs to fulfil resolved tickets."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

from agents.state import TicketState
from core.config import get_settings
from tracing.langsmith import traceable

_cfg = get_settings()

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
    "access_revoke": "/iam/revoke-access",
    "account_lock": "/iam/lock-account",
    "account_delete": "/iam/delete-account",
}

# Reply used when the action ran but the org's knowledge base had no article
# for it. Accurate to what the enterprise call actually did — no invented policy.
_STANDARD_REPLY: dict[str, str] = {
    "password_reset": "Your password reset has been started, {username}. Check your email for a temporary password and change it at your next sign-in.",
    "access_request": "Your access request has been processed, {username}. Sign out and back in if the new access doesn't appear.",
    "software_install": "Your software request has been sent to your manager for approval, {username}.",
    "leave_approval": "Your leave request has been recorded, {username}.",
    "incident_report": "An incident has been opened and routed to the support team, {username}.",
    "access_revoke": "The requested access removal has been completed, {username}.",
    "account_lock": "The requested account lock has been applied, {username}.",
    "account_delete": "The requested account deletion has been completed, {username}.",
}


def _render(template: str, values: dict[str, str]) -> str:
    """Substitute only known ``{placeholders}``.

    LLM-generated resolution text can contain stray braces; ``str.format`` would
    raise on them and crash the node, so unknown braces are left untouched.
    """
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "CRITICAL": "P1",
    "HIGH": "P2",
    "MEDIUM": "P3",
    "LOW": "P4",
}


_RETRY_DELAYS: list[float] = _cfg.action_retry_delays

# Below this confidence the action node escalates instead of calling any API.
_CONFIDENCE_THRESHOLD: float = _cfg.escalation_confidence_threshold


@traceable(name="_post_enterprise", run_type="tool", metadata={"layer": "enterprise_api"})
async def _post_enterprise(
    endpoint: str,
    payload: dict[str, Any],
    base_url: str,
    secret: str,
) -> dict[str, Any]:
    """POST payload to the enterprise API with exponential-backoff retry.

    Makes up to 4 attempts (1 initial + 3 retries) on transient
    network/timeout errors.
    4xx client errors are not retried.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([(0.0)] + _RETRY_DELAYS, start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=_cfg.enterprise_api_timeout) as client:
                resp = await client.post(
                    f"{base_url}{endpoint}",
                    json=payload,
                    headers={"Authorization": f"Bearer {secret}"},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise  # 4xx — no retry
            last_exc = exc
            log.warning("action_node.retry", attempt=attempt, status=exc.response.status_code, endpoint=endpoint)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            log.warning("action_node.retry", attempt=attempt, error=str(exc), endpoint=endpoint)
    raise last_exc  # type: ignore[misc]


def _mentioned_other_user(state: TicketState) -> str | None:
    """Return a third-party identity named in the ticket, or None.

    The intake node regex-extracts the first email in the ticket text into
    ``entities["username"]``.  That value is an *untrusted hint* — it must never
    become the action target (doing so lets any employee act on another account
    by naming it in free text).  This helper reports when the ticket names an
    identity that differs from the authenticated submitter so the caller can
    route it to a human instead of auto-acting.
    """
    authenticated: str = (state.get("user_id") or "").strip().lower()
    mentioned: str = str((state.get("entities") or {}).get("username") or "").strip().lower()
    if not mentioned or mentioned in ("unknown", ""):
        return None
    if mentioned == authenticated:
        return None
    return mentioned


def _build_payload(
    intent: str,
    state: TicketState,
) -> dict[str, Any]:
    """Construct the request body for the enterprise API call.

    The target ``user_id`` is always the authenticated submitter
    (``state["user_id"]``) — never a value parsed from the ticket text.

    Args:
        intent: Classified ticket intent (one of _ENDPOINT_MAP keys).
        state: Full ticket state.

    Returns:
        Dict ready to be JSON-serialised into the API request body.
    """
    # The action target is ALWAYS the authenticated submitter. The username in
    # fmt is derived from state["user_id"] (the JWT identity), never from text.
    user_id: str = state.get("user_id") or "unknown"
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

    if intent == "access_revoke":
        return {
            "user_id": user_id,
            "resource": entities.get("software", "all-systems"),
            "reason": raw or "Access revocation requested",
        }

    if intent == "account_lock":
        return {
            "user_id": user_id,
            "reason": raw or "Account lock requested",
        }

    if intent == "account_delete":
        # confirm=True is safe here: _build_payload is only reached after the
        # destructive gate is satisfied (action_confirmed=True), so the explicit
        # body-level confirmation the IAM endpoint requires is justified.
        return {
            "user_id": user_id,
            "confirm": True,
            "reason": raw or "Account deletion requested",
        }

    # software_install → /itsm/notify-manager
    return {"user_id": user_id, "message": raw or "Support requested"}


@traceable(name="action_node", run_type="chain", metadata={"agent": "action", "version": "1.0"})
async def action_node(state: TicketState) -> TicketState:
    """Execute the appropriate enterprise API call for the resolved intent.

    Routing:
      - "unknown" intent → escalate immediately, no API call.
      - Destructive intents (access_revoke, account_lock, account_delete) →
        blocked until action_confirmed=True.
      - Mapped intents → POST to enterprise API via _post_enterprise().

    Reads:  intent, entities, resolution_template, action_confirmed, user_id, priority
    Writes: action_taken, action_result, action_confirmed, resolution, status,
            escalated, escalation_reason, error
    """
    intent: str = state.get("intent") or "unknown"
    entities: dict[str, str] = state.get("entities") or {}

    log.info("action_node.start", ticket_id=state.get("ticket_id"), intent=intent)

    # 1. Unknown category → no enterprise action exists for it. If the org's
    #    knowledge base answered it (a policy / how-to question) and the input
    #    isn't flagged as suspicious, reply with that grounded answer — no API
    #    call is made. Otherwise escalate.
    if intent == "unknown":
        confidence_u = state.get("confidence")
        if (
            state.get("kb_grounded")
            and state.get("resolution_template")
            and confidence_u is not None
            and confidence_u >= _CONFIDENCE_THRESHOLD
        ):
            answer = _render(
                state["resolution_template"],  # type: ignore[arg-type]
                {"username": state.get("user_id") or "there", "user_id": state.get("user_id") or ""},
            )
            log.info("action_node.knowledge_answer", ticket_id=state.get("ticket_id"))
            return {
                **state,
                "action_taken": "knowledge_answer",
                "action_result": None,
                "resolution": answer,
                "escalated": False,
                "status": "resolved",
                "error": None,
            }  # type: ignore[return-value]
        log.warning("action_node.unknown_intent", ticket_id=state.get("ticket_id"))
        return {
            **state,
            "escalated": True,
            "escalation_reason": "category_unknown",
            "status": "escalated",
        }  # type: ignore[return-value]

    # 2. Confidence gate — never touch an enterprise API on a low-confidence
    #    triage/retrieval (also catches prompt-injection, which caps confidence).
    #    This MUST run before the API call, not only in the post-action router.
    confidence = state.get("confidence")
    if confidence is not None and confidence < _CONFIDENCE_THRESHOLD:
        log.warning(
            "action_node.low_confidence_escalate",
            ticket_id=state.get("ticket_id"),
            confidence=confidence,
        )
        return {
            **state,
            "escalated": True,
            "escalation_reason": f"Low triage/retrieval confidence ({confidence:.2f}) — routed to a human.",
            "status": "escalated",
        }  # type: ignore[return-value]

    # 3. Authorization gate — a ticket that names a *different* identity than the
    #    authenticated submitter is a cross-user request. These require human /
    #    delegated authority; the agent never auto-acts on another account.
    other_user = _mentioned_other_user(state)
    if other_user is not None:
        log.warning(
            "action_node.third_party_target",
            ticket_id=state.get("ticket_id"),
            submitter=state.get("user_id"),
            mentioned=other_user,
        )
        return {
            **state,
            "escalated": True,
            "escalation_reason": (
                "Request names another user's account — a human must authorize "
                "cross-user actions."
            ),
            "status": "escalated",
        }  # type: ignore[return-value]

    # 4. Destructive gate — block until caller sends action_confirmed=True.
    if intent in _DESTRUCTIVE_INTENTS and not state.get("action_confirmed"):
        log.warning("action_node.awaiting_confirmation", intent=intent)
        return {
            **state,
            "action_confirmed": False,
            "status": "awaiting_confirmation",
            "escalation_reason": f"Explicit confirmation required to execute '{intent}' on your account.",
            "error": f"Confirmation required for '{intent}'",
        }  # type: ignore[return-value]

    # 5. Build substitution context for the resolution template. "username" is
    #    the authenticated submitter only — free-text entities (software, date)
    #    are allowed through, but they can never override identity.
    authenticated_user: str = state.get("user_id") or "unknown"
    fmt: dict[str, str] = {"user_id": authenticated_user, "username": authenticated_user}
    for k, v in entities.items():
        if k == "username":
            continue  # identity is authoritative — never templated from text
        fmt[k] = str(v) if v is not None else "unknown"

    # Grounded KB answer when the org's documents covered it; otherwise an
    # accurate standard reply for the action that was performed.
    template: str = (
        state.get("resolution_template")
        if state.get("kb_grounded") and state.get("resolution_template")
        else _STANDARD_REPLY.get(intent, "Your request has been completed, {username}.")
    )  # type: ignore[assignment]
    resolution: str = _render(template, fmt)

    # 6. Call the enterprise API for the mapped intent.
    endpoint: str | None = _ENDPOINT_MAP.get(intent)
    action_result: dict[str, Any] = {}

    try:
        if endpoint:
            base_url = state.get("org_api_url") or os.getenv("ENTERPRISE_API_BASE_URL", "http://localhost:8001")
            secret = os.getenv("ENTERPRISE_API_SECRET", "")
            payload = _build_payload(intent, state)
            action_result: dict[str, Any] = await _post_enterprise(
                endpoint, payload, base_url, secret
            )

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
