# NeuraDesk — Development Guide

Everything you need to run, test, extend, and deploy NeuraDesk locally. For the
product overview and API reference, see [README.md](README.md).

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | **3.11** (`>=3.11,<3.12`) | pinned in `pyproject.toml` |
| Node.js | 20+ | frontend only |
| Docker + Docker Compose | recent | optional — SQLite works without it |
| A Groq API key | — | default LLM provider; swappable to Anthropic/OpenAI |

First run downloads two sentence-transformers models (~120 MB total) into
`~/.cache/huggingface`: the embedder (`all-MiniLM-L6-v2`) and cross-encoder
(`ms-marco-MiniLM-L-6-v2`). After that, everything runs offline.

---

## 2. First-time setup

```bash
git clone https://github.com/Subh24ai/neuradesk.git
cd neuradesk

python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -e ".[dev]"

cp .env.example .env     # then fill in the required keys (see §6)
```

Optional LLM providers are extras:

```bash
pip install -e ".[dev,anthropic]"   # langchain-anthropic + anthropic
pip install -e ".[dev,openai]"      # langchain-openai + openai
```

---

## 3. Running the app

NeuraDesk is three processes: the **main backend** (8000), the **mock enterprise
API** (8001), and the **frontend** (3000). The backend calls the enterprise API,
so start that first.

### Option A — Docker (closest to production)

```bash
docker-compose up --build
# Postgres + backend (8000) + enterprise mock (8001).
# Frontend is a separate profile:
docker-compose --profile frontend up frontend   # → localhost:3000
```

### Option B — Local, no Docker (SQLite fallback)

Set `DATABASE_URL=sqlite:///./neuradesk_local.db` in `.env` first (the
`.env.example` default points at Postgres in Docker, which this option doesn't use).

```bash
# Terminal 1 — enterprise mock API (destructive-op stubs + audit log)
source .venv/bin/activate
uvicorn services.enterprise_api:app --port 8001

# Terminal 2 — main backend (migrate first; safe to run every time)
source .venv/bin/activate
python -m scripts.migrate_db && uvicorn api.main:app --reload --port 8000

# Terminal 3 — frontend (Vite dev server, proxies /api, /auth, /ws … to :8000)
cd frontend && npm install && npm run dev
```

With no `DATABASE_URL`, the backend uses `sqlite:///./neuradesk.db`. Either way,
run `python -m scripts.migrate_db` after pulling new code (see §7).

> **Single vs. multiple workers:** the admin SSE feed is now DB-backed, so you
> can run multiple uvicorn/gunicorn workers safely. (Before v1.3 it only worked
> on one worker.)

---

## 4. The agent workflow (what actually happens to a ticket)

```
POST /tickets                      → persists a "pending" ticket, returns 201
open  /ws/{ticket_id} (WebSocket)  → runs the LangGraph graph, streams per-node events
```

The graph (`agents/graph.py`) is:

```
intake_node → knowledge_node → action_node → [escalation_node] → END
```

| Node | File | Responsibility |
|---|---|---|
| `intake_node` | `agents/intake_node.py` | Vision OCR (image tickets) → DSPy triage → category, intent, priority, confidence, entities |
| `knowledge_node` | `agents/knowledge_node.py` | Hybrid FAISS + BM25 + cross-encoder retrieval → grounded resolution (top-3 chunks) |
| `action_node` | `agents/action_node.py` | Safety gates, then the enterprise API call |
| `escalation_node` | `agents/escalation_node.py` | Human handoff + email/Slack notifications |

Routing after `action_node` is decided by `_should_escalate` in `agents/graph.py`.

### 4.1 Safety model — read this before touching `action_node`

`action_node` applies gates **in this order**, and only reaches an enterprise API
if all pass:

1. **`unknown` category** (no enterprise action exists, e.g. a policy question) →
   if the org's knowledge base answered it (`kb_grounded`) and confidence is above
   the threshold, reply with that grounded answer — **no API call**. Otherwise escalate.
2. **Low confidence** (`< escalation_confidence_threshold`, default 0.6) → escalate.
   This is the *triage* confidence; the prompt-injection guard caps it to 0.3, so
   suspicious input funnels through here *before* any action runs. Knowledge-base
   coverage deliberately does **not** lower it — `knowledge_node` reports
   `kb_grounded` instead, so a missing article never blocks a well-understood
   action (the reply then uses a standard per-action message).
3. **Cross-user request** → escalate. The action target is **always the
   authenticated submitter** (`state["user_id"]`, from the JWT). A different
   identity named in the ticket text is an untrusted hint, never the target.
   `_mentioned_other_user` detects this and routes to a human.
4. **Destructive intent** (`access_revoke`, `account_lock`, `account_delete`)
   without `action_confirmed=True` → `awaiting_confirmation` (halts the graph).
5. Otherwise → call the mapped enterprise endpoint with a payload whose
   `user_id` is the authenticated submitter.

> ⚠️ **Never** set the enterprise `user_id` from `entities` / ticket text. That
> was the critical authorization bug fixed in v1.3 — regressing it lets any user
> act on another account.

### 4.2 Destructive confirmation flow

1. Destructive ticket halts at `awaiting_confirmation`; the WS emits the status.
2. UI shows Confirm / Cancel.
3. `POST /tickets/{id}/confirm-action` atomically claims the ticket
   (`awaiting_confirmation → processing`, so a double-click can never execute the
   action twice), then resumes through the same `_process_ticket` path as every
   other ticket with the **persisted triage** (`intake_node` short-circuits — no
   LLM re-classification) and `action_confirmed=True`. `POST /tickets/{id}/cancel`
   escalates instead.

---

## 5. Testing

```bash
pytest tests/ -v                      # full unit + integration suite (250 tests)
pytest tests/test_action_node.py -v   # one file
pytest tests/ -k "confirm or otp"     # by keyword
```

**Useful flags / env:**

- `HF_HUB_OFFLINE=1 pytest …` — force offline; fails fast instead of hitting the
  HuggingFace hub if a model isn't cached. Recommended once models are downloaded.
- The `conftest.py` sets test-safe env vars (`API_SECRET_KEY`,
  `ENTERPRISE_API_SECRET`, `A2A_API_KEY=test-key`, tracing off) before any import,
  and an **autouse fixture mocks `_post_enterprise`** so no test makes a real
  enterprise HTTP call.
- **The suite is hermetic.** `conftest.py` points `DATABASE_URL` at a throwaway
  SQLite file and blanks every LLM API key before the app is imported, so tests
  never read/write your real database, never spend API quota, and pass even when
  Postgres or the network is down. (Live-model quality checks live in
  `tests/eval_rag.py`, not pytest.)

**RAG evaluation (RAGAS)** — needs a real `GROQ_API_KEY`:

```bash
python tests/eval_rag.py              # faithfulness / answer-relevancy thresholds
```

**Load test** — start both backends first:

```bash
python tests/load_test.py             # concurrency + latency percentiles
```

**Lint / type-check:**

```bash
ruff check .          # style + bug lints (CI gate)
ruff check --fix .    # auto-fix the safe ones
mypy .                # strict type-check (config in pyproject)
```

CI (`.github/workflows/ci.yml`) runs `pytest` (ignoring `eval_rag.py`) and `ruff`;
RAGAS runs only when a `GROQ_API_KEY` secret is present.

---

## 6. Environment variables

| Var | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `production` enables rate limiting + work-email enforcement |
| `API_SECRET_KEY` | — | **Required in prod** — JWT signing secret |
| `DATABASE_URL` | `sqlite:///./neuradesk.db` | Postgres in prod (`postgresql://…`) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 10 / 20 | Postgres pool tuning |
| `LLM_PROVIDER` | `groq` | `groq` \| `anthropic` \| `openai` |
| `GROQ_API_KEY` / `GROQ_MODEL` | — / `openai/gpt-oss-20b` | Groq LLM (Groq retires models — check `GET /openai/v1/models` if calls 404) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | — | alternate providers |
| `ENTERPRISE_API_BASE_URL` | `http://localhost:8001` | mock enterprise API base |
| `ENTERPRISE_API_SECRET` | — | bearer secret shared with the mock API |
| `A2A_API_KEY` | — | **optional** — required only to use the A2A endpoints |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASS` / `SMTP_PORT` / `SMTP_FROM` | — / — / — / 587 / — | OTP + notification email; unset → OTP returned inline as `dev_otp` |
| `SUPPORT_EMAIL` | — | escalation alert recipient |
| `ALLOWED_ORIGINS` | `localhost:5173,4173` | CORS allowlist (comma-separated) |
| `GCS_BUCKET` | — | screenshot upload target; unset → uploads skipped |
| `ORG_CREATION_SECRET` | — | if set, creating a new org requires this token |
| `INCLUDE_SAMPLE_KB` | `true` | serve the bundled demo policies to orgs that uploaded none |
| `KB_SAMPLE_FALLBACK` | `false` | if an org's own docs don't match, answer from the samples instead of escalating |
| `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` / `LANGCHAIN_PROJECT` | `false` / — / `neuradesk-dev` | LangSmith tracing |

All tunable constants (timeouts, retry delays, RAG thresholds,
`escalation_confidence_threshold`) live in `core/config.py` and are overridable
via same-named uppercase env vars.

---

## 7. Database & migrations

**Run this after every pull and before first start — it is safe for any database state:**

```bash
python -m scripts.migrate_db
```

It handles all three cases (see `scripts/migrate_db.py`): an **empty** database
gets the full schema created from the models and is stamped at head; an
**Alembic-versioned** database is upgraded (`alembic upgrade head`); an
**unversioned** database that the app already created is stamped if it matches
the models, or the script stops and lists missing columns instead of guessing.

> Why not plain `alembic upgrade head`? The first revision in the chain only adds
> indexes (it was generated against tables `create_all` had already built), so
> Alembic alone cannot build a schema from an empty database.

App startup still runs `Base.metadata.create_all`, which adds missing *tables*
but never missing *columns* — so skipping the migrate step after pulling new
code can leave the app failing with errors like `column users.otp_attempts does
not exist`. Lower-level Alembic commands (they read `DATABASE_URL` from the env):

```bash
alembic current               # revision the database is at
alembic heads                 # show the current head (should be a single revision)
alembic history               # full chain
alembic revision -m "add X"   # scaffold a new migration
alembic downgrade -1          # roll back one
```

**Writing a migration:** set `down_revision` to the current `alembic heads`
output so the chain stays linear (single head). Models live in `api/models.py`;
keep the ORM model and the migration in sync.

---

## 8. Extending the system

### Add a new ticket category

1. `agents/state.py` — add the literal to `TicketState.category`.
2. `dspy_modules/triage.py` — add to `VALID_CATEGORIES` and describe it in
   `TriageSignature`'s docstring.
3. `dspy_modules/training_data.py` — add labelled examples (≥ a few per category).
4. `agents/intake_node.py` — add a `_PRIORITY_MAP` entry.
5. `agents/action_node.py` — add an `_ENDPOINT_MAP` entry and a `_build_payload`
   branch; if it's destructive, add it to `_DESTRUCTIVE_INTENTS`.
6. `services/enterprise_api.py` (or `iam_api.py`) — add the endpoint.
7. Add tests alongside each change (project rule: every node change has a test).
8. Re-compile the classifier if you changed training data:
   `python -m dspy_modules.triage` (writes `triage_compiled.json`).

### Add a RAG knowledge document

Each organisation brings **its own** policies. Admins upload them with
`POST /admin/kb` (text) or `POST /admin/kb/upload` (PDF/TXT/MD/DOCX, ≤ 10 MB);
they are stored per org in `org_knowledge_docs` and loaded **per ticket** for that
org only — they are never added to the shared index, so one org's documents can
never answer another org's ticket.

How retrieval treats them (`HybridRetriever.search`):

1. Uploaded docs are split into one passage per paragraph (`rag.loader.chunk_text`;
   long PDF pages are sentence-split, ≤ 900 chars) so every section of a long
   handbook is searchable, then BM25-prefiltered and cross-encoder reranked.
2. **The org's documents are authoritative.** If the best org passage clears
   `RAG_SCORE_THRESHOLD`, only org passages are used — never blended with sample
   text that could contradict the org's policy.
3. Org has docs but none match → the ticket escalates to a human (set
   `KB_SAMPLE_FALLBACK=true` to answer from the bundled samples instead).
4. Org has uploaded nothing → the bundled demo policies in `rag/data/` are used
   (`INCLUDE_SAMPLE_KB=false` disables them entirely for production).

The `rag/data/*.md` files are **fictional sample policies** for demos and tests;
edit them only to change the demo corpus.

Always use the hybrid retriever (`rag/retriever.py`, `get_retriever()`) for any
new knowledge lookup — don't hand-roll a second retrieval path.

---

## 9. Common gotchas

- **Groq retires models.** If tickets suddenly all escalate as `unknown`, check the
  backend log for `404 … model … does not exist` and list what your key can use:
  `curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models`.
  Groq's free tier is ~1,000 requests/day and 8,000 tokens/min (≈ 2–3 tickets/min);
  use a paid tier for real multi-user load. There is currently no Groq vision model
  on the free tier, so screenshot tickets fall back to their text.
- **Model download on first run** — the first ticket (or `/health/deep`) builds
  the retriever and downloads the embedder/cross-encoder. Expect a slow first call.
- **`HF_HUB_OFFLINE=1`** avoids accidental network calls once models are cached.
- **A2A endpoints return 503** until `A2A_API_KEY` is set — this is expected; the
  rest of the app runs fine without it.
- **OTP in dev** — with no SMTP configured, `/auth/register` returns the OTP inline
  as `dev_otp`. Five wrong `/auth/verify-otp` guesses lock the code (request a new one).
- **Enterprise API 401** — the backend and the mock API must share the exact same
  `ENTERPRISE_API_SECRET`.
- **Postgres checkpointer (optional)** — `agents/graph.py` can use
  `AsyncPostgresSaver` for crash recovery if you install
  `langgraph-checkpoint-postgres` + `psycopg[binary]`; it's off by default.

---

## 10. Deployment

The runtime image is built from `infra/Dockerfile` (multi-stage, non-root user).
`.dockerignore` keeps secrets, the DB, PII backups, and the venv out of the image
— **keep it tracked**. The app is deployed on GCP Cloud Run; `.gcloudignore`
controls the source upload.

```bash
docker build -f infra/Dockerfile -t neuradesk .
docker run -p 8000:8000 --env-file .env neuradesk
```

Before shipping an image, confirm no secret is in it:

```bash
docker run --rm neuradesk sh -c 'ls -la /app/.env 2>/dev/null || echo "no .env in image ✓"'
```

---

## 11. Project structure

```
neuradesk/
├── agents/          # LangGraph nodes + typed TicketState (the agent workflow)
├── api/             # FastAPI app: auth, tickets, WebSocket, admin, A2A, models
├── core/            # config, LLM factory, DSPy config, security (injection guard)
├── services/        # mock ITSM/HR/IAM enterprise APIs + audit log
├── rag/             # hybrid retriever (FAISS + BM25 + cross-encoder) + loader + data/
├── dspy_modules/    # DSPy triage signature + compiled classifier + training data
├── notifications/   # Slack webhook alerts
├── storage/         # GCS image upload
├── tracing/         # LangSmith helpers
├── alembic/         # DB migrations
├── frontend/        # React + TypeScript + Vite SPA
├── infra/           # Dockerfile, Cloud Run config
├── tests/           # pytest suite + RAGAS eval + load test
├── mcp_server.py    # MCP stdio tool server (Claude Desktop, etc.)
└── docker-compose.yml
```
