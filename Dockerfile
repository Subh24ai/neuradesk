# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Installs all Python dependencies into /install so the runtime image
# can copy them without needing build tools.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Non-editable install: all deps land in /install; source is copied in the runtime stage.
# PYTHONPATH=/app (set in runtime) resolves app packages from /app at runtime.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install ".[dev]"

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Lean image: no build tools, non-root user, source copied last.
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/tmp

# Runtime system libs only (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Non-root user — principle of least privilege
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --no-create-home appuser

# Copy source (invalidates only this layer on code changes)
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
