---
name: project-production-hardening
description: Production hardening changes made to NeuraDesk — security, reliability, observability
metadata:
  type: project
---

Production hardening completed (2026-05-17). All 133 tests pass.

**Why:** User explicitly asked for a complete working product, not a demo. Audit found it was ~54% production-ready.

**Changes made:**

Backend:
- CORS middleware added (`CORSMiddleware`), origins from `ALLOWED_ORIGINS` env var
- Rate limiting via `slowapi` — 10/min register, 20/min login, 5/min forgot-password, 30/min ticket create
- Rate limiter disabled when `APP_ENV != production` (prevents test failures)
- `API_SECRET_KEY` now raises `RuntimeError` on startup if unset in production
- DB connection pooling: `pool_size=10`, `max_overflow=20`, `pool_recycle=3600`, `pool_pre_ping=True` for PostgreSQL
- Input limits: `text` max 4000 chars, `image_b64` max ~1MB on `TicketCreateRequest`
- Deep health check at `GET /health/deep` — checks DB + RAG index, returns 503 if unhealthy
- All `print()` debug statements replaced with `log.debug()` / `log.info()` (structlog)
- Alembic initialized with `autogenerate` wired to ORM models — run `alembic upgrade head` to migrate
- `slowapi==0.1.9` added to `pyproject.toml`

Frontend:
- `ErrorBoundary` component wraps entire app — catches React errors, shows reload prompt
- `StrictMode` enabled in `main.tsx`
- JWT expiry checked client-side on app load — clears stale auth from localStorage
- 401 responses auto-trigger logout in ticket submit handler
- WebSocket reconnect: up to 3 retries with 2s × attempt backoff; shows "Reconnecting…" badge
- Image upload size validated client-side (1 MB limit) before FileReader/base64 encoding
- Character counter appears on textarea when within 500 chars of 4000-char limit

Infrastructure:
- `.env.example` created with all required vars documented
- `alembic/` directory created, `env.py` reads `DATABASE_URL` from env

**How to apply:** When suggesting new features or changes, assume these are the current baselines. New endpoints should add `@limiter.limit()` decorators. New DB engines should use the pool kwargs pattern. Schema changes need `alembic revision --autogenerate`.
