"""Async JSON-lines audit log for every enterprise API call."""

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_AUDIT_FILE = Path(os.getenv("AUDIT_LOG_PATH", "services/audit.jsonl"))


def _hash_token(token: str) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of the token.

    Stored instead of the raw token so the log file is safe to share.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _write_line_sync(entry: dict[str, Any]) -> None:
    """Append one JSON line to the audit file — runs in a thread-pool worker."""
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUDIT_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


async def log_audit(
    endpoint: str,
    token: str,
    request_body: dict[str, Any],
    response_status: int,
    latency_ms: float,
) -> None:
    """Append one audit record asynchronously using asyncio.to_thread().

    Never blocks the event loop — the file write runs in the default
    ThreadPoolExecutor and the coroutine resumes when it completes.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "token_hash": _hash_token(token),
        "request_body": request_body,
        "response_status": response_status,
        "latency_ms": round(latency_ms, 2),
    }
    await asyncio.to_thread(_write_line_sync, entry)
