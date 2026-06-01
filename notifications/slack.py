"""Slack incoming-webhook notifications for escalation alerts."""

import httpx
import structlog

from core.config import get_settings

_cfg = get_settings()

log = structlog.get_logger(__name__)


def send_slack_escalation(
    webhook_url: str,
    ticket_id: str,
    reason: str,
    assignee_group: str,
    priority: str,
    org_name: str,
) -> None:
    """POST an escalation alert to a Slack incoming webhook. Never raises."""
    text = (
        f":rotating_light: *Ticket escalated* — `{ticket_id}`\n"
        f"*Org:* {org_name}  |  *Priority:* {priority}  |  *Assignee:* {assignee_group}\n"
        f"*Reason:* {reason}"
    )
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=_cfg.slack_webhook_timeout)
        resp.raise_for_status()
        log.info("slack.escalation_sent", ticket_id=ticket_id)
    except Exception as exc:
        log.warning("slack.escalation_failed", ticket_id=ticket_id, error=str(exc))
