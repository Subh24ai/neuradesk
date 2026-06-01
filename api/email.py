"""Shared email utilities — OTP dispatch and ticket notifications."""

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from core.config import get_settings

_cfg = get_settings()

log = structlog.get_logger(__name__)

_OTP_EXPIRE_MINUTES = 10

# Expected human response times per priority level — shown in escalation emails.
RESPONSE_TIMES: dict[str, str] = {
    "CRITICAL": "15 minutes",
    "HIGH": "1 hour",
    "MEDIUM": "4 hours",
    "LOW": "24 hours",
}

_SMTP_HOST = lambda: os.getenv("SMTP_HOST", "")  # noqa: E731
_SMTP_USER = lambda: os.getenv("SMTP_USER", "")  # noqa: E731
_SMTP_PASS = lambda: os.getenv("SMTP_PASS", "")  # noqa: E731
_SMTP_PORT = lambda: int(os.getenv("SMTP_PORT", "587"))  # noqa: E731
_FROM_ADDR = lambda: os.getenv("SMTP_FROM", _SMTP_USER()) or "noreply@neuradesk.ai"  # noqa: E731


def _send(to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send a MIME email via SMTP STARTTLS. Falls back to console log when SMTP is not configured."""
    host = _SMTP_HOST()
    user = _SMTP_USER()
    password = _SMTP_PASS()

    if not host or not user or not password:
        log.warning("smtp.not_configured", to=to, subject=subject,
                    hint="Set SMTP_HOST/SMTP_USER/SMTP_PASS in .env to send real emails",
                    body_preview=text_body[:200])
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"NeuraDesk <{_FROM_ADDR()}>"
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(host, _SMTP_PORT(), timeout=_cfg.email_smtp_timeout) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(user, password)
            server.sendmail(_FROM_ADDR(), to, msg.as_string())
        log.info("email.sent", to=to, subject=subject)
    except Exception as exc:
        log.error("email.failed", to=to, subject=subject, error=str(exc))
        raise


def send_otp_email(email: str, otp: str) -> None:
    """Send a 6-digit OTP to the given address."""
    text = (
        f"Your NeuraDesk verification code is: {otp}\n\n"
        f"This code expires in {_OTP_EXPIRE_MINUTES} minutes.\n"
        "If you did not request this, you can safely ignore this email."
    )
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:480px;margin:40px auto;padding:32px;
                background:#fff;border-radius:12px;border:1px solid #e2e8f0;">
      <h2 style="margin:0 0 4px;color:#4f46e5;font-size:20px;">NeuraDesk</h2>
      <p style="margin:0 0 24px;color:#64748b;font-size:14px;">Your email verification code</p>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                  padding:28px;text-align:center;margin-bottom:24px;">
        <span style="font-size:40px;font-weight:800;letter-spacing:14px;
                     color:#1e293b;font-family:monospace;">{otp}</span>
      </div>
      <p style="margin:0;color:#94a3b8;font-size:13px;">
        Expires in {_OTP_EXPIRE_MINUTES} minutes. Did not request this? Ignore it.
      </p>
    </div>
    """
    _send(email, "Your NeuraDesk verification code", text, html)


def send_escalation_alert(
    ticket_id: str,
    reason: str,
    assignee_group: str,
    priority: str,
    org_name: str,
    support_email: str,
) -> None:
    """Notify the support team that a ticket has been escalated and needs human attention."""
    if not support_email:
        log.warning("escalation.no_support_email", ticket_id=ticket_id)
        return
    short_id = ticket_id[:8]
    text = (
        f"NeuraDesk — Escalated Ticket [{short_id}]\n\n"
        f"Organisation: {org_name}\n"
        f"Assigned group: {assignee_group}\n"
        f"Priority: {priority}\n"
        f"Reason: {reason}\n\n"
        "Log in to the NeuraDesk admin dashboard to review and resolve this ticket."
    )
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:520px;margin:40px auto;padding:32px;
                background:#fff;border-radius:12px;border:1px solid #e2e8f0;">
      <h2 style="margin:0 0 4px;color:#4f46e5;font-size:20px;">NeuraDesk</h2>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">Escalated ticket — action required</p>
      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
        <p style="margin:0 0 8px;color:#92400e;font-size:14px;font-weight:600;">Ticket #{short_id} needs human review</p>
        <p style="margin:0;color:#92400e;font-size:13px;">{reason}</p>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;color:#475569;">
        <tr><td style="padding:4px 0;font-weight:600;">Organisation</td><td>{org_name}</td></tr>
        <tr><td style="padding:4px 0;font-weight:600;">Assigned to</td><td>{assignee_group}</td></tr>
        <tr><td style="padding:4px 0;font-weight:600;">Priority</td><td>{priority}</td></tr>
      </table>
      <p style="margin-top:20px;color:#94a3b8;font-size:12px;">
        Log in to the NeuraDesk admin dashboard to view full details and resolve this ticket.
      </p>
    </div>
    """
    _send(support_email, f"[{priority}] Escalated ticket requires attention — {org_name}", text, html)


def send_ticket_notification(
    email: str,
    ticket_id: str,
    status: str,
    resolution: str | None,
    escalation_reason: str | None,
    priority: str | None = None,
    assignee_group: str | None = None,
) -> None:
    """Notify the ticket owner that their ticket has been resolved or escalated."""
    if status == "resolved":
        subject = "Your NeuraDesk request has been resolved"
        detail_text = f"Resolution:\n{resolution}" if resolution else "Your request was handled automatically."
        detail_html = (
            f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;margin:16px 0;">'
            f'<p style="margin:0;color:#166534;font-size:14px;">{resolution or "Your request was handled automatically."}</p>'
            f'</div>'
        )
        accent = "#16a34a"
        badge = "Resolved"
    else:
        subject = "Your NeuraDesk request has been escalated"
        response_time = RESPONSE_TIMES.get((priority or "MEDIUM").upper(), "4 hours")
        group_label = assignee_group or "support team"
        escalation_body = escalation_reason or "Your request needs human attention."
        detail_text = (
            f"Reason:\n{escalation_body}\n\n"
            f"Assigned to: {group_label}\n"
            f"Expected response: {response_time}"
        )
        detail_html = (
            f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:16px 20px;margin:16px 0;">'
            f'<p style="margin:0 0 8px;color:#92400e;font-size:14px;">{escalation_body}</p>'
            f'<p style="margin:0;color:#b45309;font-size:13px;">'
            f'Assigned to: <strong>{group_label}</strong> &nbsp;·&nbsp; '
            f'Expected response: <strong>{response_time}</strong>'
            f'</p>'
            f'</div>'
        )
        accent = "#d97706"
        badge = "Escalated to human queue"

    text = f"""NeuraDesk — Ticket Update

Ticket ID: {ticket_id}
Status: {status.capitalize()}

{detail_text}

Log in to NeuraDesk to view the full details.
"""
    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:520px;margin:40px auto;padding:32px;
                background:#fff;border-radius:12px;border:1px solid #e2e8f0;">
      <h2 style="margin:0 0 4px;color:#4f46e5;font-size:20px;">NeuraDesk</h2>
      <p style="margin:0 0 20px;color:#64748b;font-size:14px;">Ticket update</p>
      <div style="display:inline-block;background:{accent}1a;border:1px solid {accent}33;
                  border-radius:99px;padding:4px 12px;margin-bottom:16px;">
        <span style="color:{accent};font-size:13px;font-weight:600;">{badge}</span>
      </div>
      {detail_html}
      <p style="color:#94a3b8;font-size:12px;margin-top:20px;">
        Ticket ID: <code style="font-family:monospace;">{ticket_id[:8]}…</code>
      </p>
    </div>
    """
    _send(email, subject, text, html)
