# NeuraDesk

**Production-grade agentic IT/HR service platform — multi-agent AI that autonomously resolves enterprise tickets**

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-202%20passing-brightgreen)](tests/)

## Live Demo
- **App**: https://neuradesk-112430812621.us-central1.run.app
- **A2A Agent Card**: https://neuradesk-112430812621.us-central1.run.app/.well-known/agent.json
- **API Docs**: https://neuradesk-112430812621.us-central1.run.app/docs

---

## What It Does

Enterprise IT/HR teams spend 60–80% of their time on repetitive tickets — password resets, access provisioning, leave approvals, incident creation — that follow predictable patterns. The bottleneck is not intelligence; it is routing, context retrieval, and safe execution at scale.

NeuraDesk routes every incoming ticket through four specialized LangGraph agents: an Intake Agent that classifies intent with a DSPy-optimized classifier, a Knowledge Agent that retrieves relevant articles via hybrid FAISS + BM25 retrieval with cross-encoder reranking, an Action Agent that executes enterprise API calls behind an explicit confirmation gate for destructive operations, and an Escalation Agent that hands off unresolved tickets with full state attached.

## Architecture

```mermaid
graph TD
    A([Employee]) -->|text or screenshot| B[Intake Agent]
    B -->|category, intent, confidence| C[Knowledge Agent]
    C -->|chunks + resolution template| D[Action Agent]
    D -->|resolved| E([Ticket Resolved])
    D -->|low confidence, unknown, or destructive unconfirmed| F[Escalation Agent]
    F -->|full context attached| G([Human Queue])
```

| Agent | Role |
|---|---|
| **Intake** | DSPy-optimized classifier — assigns category, intent, priority, and confidence score |
| **Knowledge** | Hybrid retrieval: FAISS semantic search + BM25 lexical search + cross-encoder reranking |
| **Action** | Executes ITSM/HR API calls; blocks destructive operations until explicitly confirmed |
| **Escalation** | Routes to the correct support tier with complete agent context attached |

## Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph 1.2, typed `TicketState` |
| RAG | FAISS + rank-bm25 + sentence-transformers cross-encoder |
| Prompt optimization | DSPy 2.5 |
| LLM | Groq (llama-3.3-70b-versatile) — swappable via `LLM_PROVIDER` env var (Anthropic/OpenAI supported) |
| Tracing | LangSmith — every node is a named span |
| API | FastAPI 0.115, WebSocket streaming, structlog |
| Auth | JWT (PyJWT) + bcrypt, 8-hour sessions |
| Database | PostgreSQL, SQLAlchemy 2.0 `mapped_column` |
| Cloud | GCP Cloud Run, Docker, docker-compose |
| Testing | pytest, RAGAS evaluation suite |

## Key Features

- ✅ Multi-agent orchestration with LangGraph — 4 nodes, typed `TicketState`, conditional routing
- ✅ Hybrid RAG — FAISS semantic + BM25 lexical + cross-encoder reranking
- ✅ DSPy-optimized ticket classifier with offline prompt compilation
- ✅ Multimodal input — plain text and base-64 encoded screenshots
- ✅ A2A protocol endpoint on the Knowledge Agent (agent-to-agent interop)
- ✅ Production safety — explicit confirmation gate blocks all destructive API calls
- ✅ Auto-escalation with complete agent state forwarded to the human queue
- ✅ LangSmith tracing on every node — no silent agent execution
- ✅ JWT auth + session management (GET /auth/sessions, remote revocation), JSON-lines audit log, structured errors
- ✅ RAGAS evaluation suite with CI enforcement on faithfulness and answer relevance
- ✅ Prompt injection guard — detects `system:`, role-override, and jailbreak patterns; caps confidence to 0.3 so adversarial tickets escalate safely

## Quickstart

**Prerequisites:** Python 3.11, Docker (for Postgres — optional, SQLite works locally)

```bash
git clone https://github.com/Subh24ai/neuradesk.git
cd neuradesk

python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip && pip install -e ".[dev]"

cp .env.example .env
# Fill in: GROQ_API_KEY, ENTERPRISE_API_SECRET, API_SECRET_KEY, A2A_API_KEY
```

**Full stack with Docker (recommended):**
```bash
docker-compose up --build
# Backend → localhost:8000   Enterprise mock API → localhost:8001
```

**Local dev without Docker (SQLite fallback):**
```bash
# Terminal 1 — Enterprise mock API (port 8001):
ENTERPRISE_API_SECRET=local-dev-secret-123 \
  uvicorn services.enterprise_api:app --port 8001

# Terminal 2 — Main backend (port 8000):
uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend (port 3000):
cd frontend && npm install && npm run dev
```

**Submit your first ticket:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@company.com", "password": "testpass123"}' | jq -r .access_token)

curl -s -X POST http://localhost:8000/tickets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "I forgot my password"}' | jq .
```

**Run tests:**
```bash
pytest tests/ -v          # 202 tests
```

**Run the load test:**
```bash
# Start both servers, then:
python3 tests/load_test.py
```

## Project Structure

```
neuradesk/
├── agents/              # LangGraph nodes and typed TicketState
│   ├── state.py         # Single TypedDict threaded through every node
│   ├── graph.py         # Wiring, conditional routing, entry point
│   ├── intake_node.py   # Category · intent · priority · confidence
│   ├── knowledge_node.py# FAISS + BM25 retrieval + cross-encoder reranking
│   ├── action_node.py   # Enterprise API dispatch + destructive-action gate
│   └── escalation_node.py # Human handoff with full state
├── api/                 # FastAPI app — auth, ticket routes, WebSocket stream, admin SSE
├── core/                # LLM factory, DSPy config, security (injection guard)
├── notifications/       # Slack incoming-webhook alerts
├── storage/             # GCS image upload utility
├── services/            # Mock ITSM/HR endpoints + async JSON-lines audit log
├── rag/                 # Retriever (FAISS + BM25 + cross-encoder)
├── dspy_modules/        # DSPy signatures and compiled classifiers
├── tracing/             # LangSmith @traceable helpers, trace URL utilities
├── tests/               # pytest suite — agents, API, RAG, security
├── infra/               # Dockerfile, GCP Cloud Run config
└── docker-compose.yml   # PostgreSQL · backend · enterprise mock API
```

## API Reference

### Main API — port 8000

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | — | Create account, returns 8-hour JWT |
| `POST` | `/auth/login` | — | Login, returns 8-hour JWT |
| `POST` | `/tickets` | JWT | Run agent graph, persist and return result |
| `GET` | `/tickets/` | JWT | Last 20 tickets for the authenticated user |
| `GET` | `/tickets/{id}` | JWT | Full ticket state by ID |
| `WS` | `/ws/{ticket_id}` | — | Stream per-node status events in real time |
| `POST` | `/tickets/{id}/confirm-action` | JWT | Confirm a destructive action awaiting authorization |
| `POST` | `/tickets/{id}/cancel` | JWT | Cancel a destructive action (routes to escalation) |
| `GET` | `/auth/sessions` | JWT | List active sessions for the current user |
| `DELETE` | `/auth/sessions/{jti}` | JWT | Revoke a session by JTI (remote sign-out) |
| `GET` | `/admin/stream` | JWT (query) | SSE stream of resolved/escalated ticket events (admin) |
| `GET` | `/.well-known/agent.json` | — | A2A Agent Card |
| `POST` | `/tasks/send` | — | A2A synchronous knowledge-retrieval task |

### Enterprise Mock API — port 8001

All endpoints require `Authorization: Bearer <ENTERPRISE_API_SECRET>` and append to `services/audit.jsonl`.

| Method | Endpoint | Destructive | Description |
|---|---|---|---|
| `POST` | `/itsm/reset-password` | ✅ | Generate temporary password |
| `POST` | `/itsm/provision-access` | ✅ | Grant resource role |
| `POST` | `/hr/approve-leave` | — | Approve leave request |
| `POST` | `/itsm/create-incident` | — | Open incident record |
| `POST` | `/itsm/notify-manager` | — | Email reporting manager |

## MCP Interface

NeuraDesk ships an [MCP](https://modelcontextprotocol.io) tool server
(`mcp_server.py`) that exposes a read-only slice of the platform to MCP clients
such as Claude Desktop over **stdio**. It reuses the same hybrid retriever,
database, and category taxonomy as the agent graph. Being stdio (client-launched
and local), it carries no bearer auth — unlike the HTTP A2A and enterprise APIs.

| Tool | Parameters | Description |
|---|---|---|
| `search_knowledge` | `query`, `org_id` | Hybrid FAISS + BM25 + cross-encoder search over the global KB merged with an org's private docs; returns the top 3 chunks |
| `get_ticket_status` | `ticket_id` | Current status, category, resolution, and escalation details for a ticket |
| `resolve_ticket_info` | `category` | Top 3 knowledge-base resolution steps for a ticket category (retrieval-only) |
| `list_ticket_categories` | — | All supported ticket categories with descriptions |

**Run it (stdio):**
```bash
python mcp_server.py
```
The server reads `DATABASE_URL` from the environment — point it at the same
database the API uses.

**Use with Claude Desktop**

Add this to `claude_desktop_config.json` (macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`). The snippet
uses absolute paths — replace every `/ABS/PATH/` placeholder with your own
virtualenv Python and repo paths:

```json
{
  "mcpServers": {
    "neuradesk": {
      "command": "/ABS/PATH/neuradesk/.venv/bin/python",
      "args": ["/ABS/PATH/neuradesk/mcp_server.py"],
      "env": {
        "DATABASE_URL": "sqlite:////ABS/PATH/neuradesk/neuradesk.db"
      }
    }
  }
}
```

Restart Claude Desktop, then the four tools appear under the MCP (🔌) menu. Try
"What ticket categories does NeuraDesk support?" or "Search the knowledge base
for VPN setup."

## Benchmarks

| Metric | Value |
|---|---|
| Ticket resolution latency (P50) | 4.28s (Groq LLM) |
| Ticket resolution latency (P95) | 4.71s (Groq LLM) |
| Concurrent users tested | 10 (3 workers) |
| Success rate | 100/100 |
| RAG faithfulness score (RAGAS)        | 1.000 (10-question eval, llama-3.1-8b-instant judge) |
| RAG answer relevancy (RAGAS)          | 0.439 (10-question eval, llama-3.1-8b-instant judge) |
| DSPy classifier accuracy — zero-shot  | 66.7% (10/15) |
| DSPy classifier accuracy — compiled   | 93.3% (14/15) |

See [BENCHMARKS.md](BENCHMARKS.md) for full breakdown and latency footnote.

## Known Limitations

### Fixed in v1.1

| Issue | Fix |
|---|---|
| ✅ No escalation notifications | Email + Slack alerts fire from `escalation_node` |
| ✅ Destructive actions unconfirmable from UI | Confirm/cancel flow via `POST /tickets/{id}/confirm-action` |
| ✅ FAISS not updated on KB upload | `add_documents()` called after every admin KB insert |
| ✅ JWT not revocable | `TokenBlocklist` table — every authenticated request checked |
| ✅ Images not persisted after upload | GCS upload utility; URL stored in `tickets.image_url` |
| ✅ No admin real-time push | SSE stream at `GET /admin/stream` with per-org queue |
| ✅ WebSocket no reconnect logic | Exponential backoff (1 s / 2 s / 4 s) + fetch on reconnect |
| ✅ No Slack notifications on escalation | Slack incoming-webhook via `notifications/slack.py` |

### Fixed in v1.2

| Issue | Fix |
|---|---|
| ✅ Hardcoded false `<2s` stat in UI | Updated to `~4s` to match BENCHMARKS.md P50 |
| ✅ No prompt injection filter | `core/security.py` — 7 patterns, confidence capped to 0.3, 13 tests |
| ✅ RAG threshold disabled (0.0) | Threshold set to 0.35; off-topic tickets now escalate instead of hallucinating |
| ✅ Mock sessions in Account panel | Real `GET /auth/sessions` + `DELETE /auth/sessions/{jti}` endpoints wired to UI |
| ✅ Docker inter-container env var mismatch | `ENTERPRISE_API_URL` → `ENTERPRISE_API_BASE_URL` across codebase |
| ✅ GCP deployment live | Cloud Run URL — see Live Demo above |

### Remaining

- Mock enterprise APIs — `services/enterprise_api.py` stubs only; no real ITSM/HR integration
- Groq single point of failure — no fallback LLM configured
- `audit.jsonl` unbounded — no rotation or max-size policy
- RAG answer relevancy 0.44 — corpus too small; improves with more KB documents
- `SUPPORT_EMAIL` / SMTP must be configured manually per org

## Roadmap

- ✅ **Week 1** — Core scaffold: LangGraph skeleton, FastAPI, JWT auth, mock enterprise API, 33 passing tests
- ✅ **Week 2** — RAG (faithfulness 1.0) ✓, DSPy 93.3% ✓, all agents live ✓ — 80 tests green
- ✅ **Week 3** — A2A protocol ✓, LangSmith tracing ✓, CI/CD ✓ — 111 tests green
- ✅ **Week 4** — React frontend ✓, GCP deployment ✓, load test ✓ (P50 4.28s, 100/100 success)
- ✅ **v1.1 hardening** — 8 production fixes: escalation alerts, confirmation flow, FAISS live update, JWT revocation, image persistence, SSE admin push, WS reconnect, Slack webhook — 169 tests green
- ✅ **v1.2 security** — prompt injection guard, RAG threshold fix, real session management, Docker env fix, GCP Cloud Run deploy — 202 tests green

---

Built by [Subhash Gupta](https://linkedin.com/in/subhash24gupta) · [GitHub](https://github.com/Subh24ai/neuradesk)
