"""Central configuration — every tuneable value in one place.

Each field maps to an environment variable of the same name (uppercase).
Settings are validated on first access and cached for the process lifetime.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── LLM models ────────────────────────────────────────────────────────
    claude_model: str = "claude-sonnet-4-20250514"
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    dspy_model: str = "anthropic/claude-sonnet-4-20250514"

    # ── Timeouts (seconds) ────────────────────────────────────────────────
    enterprise_api_timeout: float = 10.0
    email_smtp_timeout: int = 15
    slack_webhook_timeout: float = 5.0
    a2a_query_timeout: int = 30
    graph_execution_timeout: int = 120

    # ── Retry ─────────────────────────────────────────────────────────────
    action_retry_delays: list[float] = [1.0, 2.0, 4.0]

    # ── RAG ───────────────────────────────────────────────────────────────
    rag_score_threshold: float = 0.35
    rag_stage_candidates: int = 10
    embed_model: str = "all-MiniLM-L6-v2"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Auth ──────────────────────────────────────────────────────────────
    token_expire_minutes: int = 480

    # ── Admin SSE ─────────────────────────────────────────────────────────
    admin_sse_queue_size: int = 64

    # ── WebSocket ticket poll ─────────────────────────────────────────────
    ticket_poll_attempts: int = 10
    ticket_poll_interval: float = 0.2

    # ── Background jobs (also readable as env vars independently) ─────────
    stale_ticket_poll_seconds: int = 300
    faiss_reload_poll_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()
