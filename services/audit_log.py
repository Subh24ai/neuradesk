"""Async JSON-lines audit log for every enterprise API call.

Security properties:
- PII fields in request bodies are redacted before writing.
- Log file is rotated at AUDIT_LOG_MAX_BYTES (default 10 MB) with up to
  AUDIT_LOG_BACKUP_COUNT (default 5) rotated files — ~60 MB max on disk.
- File created with 0o600 permissions (owner read/write only).
"""

import asyncio
import hashlib
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths and rotation config ─────────────────────────────────────────────────

_AUDIT_FILE: Path = Path(os.environ.get("AUDIT_LOG_PATH", "services/audit.jsonl"))
_AUDIT_LOG_MAX_BYTES: int = int(os.environ.get("AUDIT_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
_AUDIT_LOG_BACKUP_COUNT: int = int(os.environ.get("AUDIT_LOG_BACKUP_COUNT", "5"))

# ── PII redaction ─────────────────────────────────────────────────────────────

_PII_FIELDS: frozenset[str] = frozenset({
    "user_id",       # employee identifier — present in every endpoint
    "email",         # present in reset-password
    "start_date",    # leave dates — present in approve-leave
    "end_date",      # leave dates — present in approve-leave
    "description",   # free-text incident description — may contain PII
    "message",       # free-text manager notification — may contain PII
})


def _redact(body: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of body with all PII field values replaced."""
    return {k: "[REDACTED]" if k in _PII_FIELDS else v for k, v in body.items()}


# ── Token hashing ─────────────────────────────────────────────────────────────

def _hash_token(token: str) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of the token."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


# ── Rotating file handler (initialised once at module level) ──────────────────

def _init_handler() -> logging.handlers.RotatingFileHandler:
    """Create the audit log directory, set 0o600 on new files, return handler."""
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    is_new = not _AUDIT_FILE.exists()

    handler = logging.handlers.RotatingFileHandler(
        str(_AUDIT_FILE),
        mode="a",
        maxBytes=_AUDIT_LOG_MAX_BYTES,
        backupCount=_AUDIT_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    # Emit only the raw message — no logging timestamp, level, or logger name.
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Restrict permissions on newly created files only.  Skipped if the file
    # already exists (process may not own it, and chmod would fail).
    if is_new and _AUDIT_FILE.exists():
        os.chmod(str(_AUDIT_FILE), 0o600)

    return handler


_handler: logging.handlers.RotatingFileHandler | None = None

_audit_logger: logging.Logger = logging.getLogger("neuradesk.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False  # do not forward to the root logger or structlog


# ── Write helpers ─────────────────────────────────────────────────────────────

def _get_handler() -> logging.handlers.RotatingFileHandler:
    """Return the cached handler, initialising it on first call.

    Reads the current value of _AUDIT_FILE at init time so that tests can
    monkeypatch _AUDIT_FILE and reset _handler = None to force reinitialisation
    against the patched path.
    """
    global _handler
    if _handler is None:
        _audit_logger.handlers.clear()  # drop any stale handler from a prior init
        _handler = _init_handler()
        _audit_logger.addHandler(_handler)
    return _handler


def _write_line_sync(entry: dict[str, Any]) -> None:
    """Write one JSON line via the rotating audit logger (thread-safe)."""
    _get_handler()  # ensure handler points to the current _AUDIT_FILE
    _audit_logger.info(json.dumps(entry, default=str))


async def log_audit(
    endpoint: str,
    token: str,
    request_body: dict[str, Any],
    response_status: int,
    latency_ms: float,
) -> None:
    """Append one redacted audit record asynchronously.

    Runs the file write in the default ThreadPoolExecutor so the event loop
    is never blocked.  The RotatingFileHandler serialises concurrent writes
    via its internal threading lock.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "token_hash": _hash_token(token),
        "request_body": _redact(request_body),
        "response_status": response_status,
        "latency_ms": round(latency_ms, 2),
    }
    await asyncio.to_thread(_write_line_sync, entry)
