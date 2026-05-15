---
name: project-neuradesk-week1
description: NeuraDesk project status after Week 1 scaffold — what was built, stack decisions, and conventions to carry forward
metadata:
  type: project
---

Week 1 scaffold is complete and all 33 tests pass. The platform is a production multi-agent IT/HR ticket resolution system.

**Why:** Building a portfolio-quality agentic system demonstrating LangGraph, DSPy, RAG, and enterprise API integration.

**How to apply:** Use this context when resuming work in any subsequent week.

## Stack decisions locked in

- LLM: Claude via `langchain-anthropic==0.3.0` + `anthropic==0.40.0` (NOT OpenAI)
- Graph: LangGraph 0.2.60 with `TicketState` TypedDict (no raw dicts in nodes)
- DSPy package is `dspy` (NOT `dspy-ai` — that's a deprecated alias)
- SQLAlchemy 2.0 `mapped_column` syntax only (no legacy `Column()`)
- JWT auth via PyJWT + bcrypt (not python-jose, not passlib)
- Audit log: JSON lines at `services/audit.jsonl`, async write via `asyncio.to_thread()`
- Python 3.11 via Homebrew (`/opt/homebrew/bin/python3.11`); venv at `.venv/`

## Category Literal (tightened Week 1)

`TicketState.category` is typed as:
`Literal["password_reset", "access_request", "software_install", "leave_approval", "incident_report", "unknown"]`
NOT the old "IT" | "HR" | "UNKNOWN". Use lowercase "unknown" everywhere — the routing function `_should_escalate` checks for lowercase.

## Escalation triggers

- `confidence < 0.6` after intake
- `category == "unknown"` (lowercase)
- `status == "escalated"` (set by action_node on any exception)
- Destructive intent + `action_confirmed` is not True

## Destructive intents

`frozenset({"access_revoke", "account_lock", "account_delete"})` in `action_node.py`

## Test setup

- pytest configured with `pythonpath = ["."]` in pyproject.toml
- `conftest.py` sets env vars at top before any imports (critical for module-level `_SECRET`, `_AUDIT_FILE`)
- `override_db` fixture pattern: both `test_client` and `auth_client` share the same `db_engine` instance via fixture caching
- Mock run_ticket patches `api.main.run_ticket` (the imported name)

## Files built this week

agents/state.py, graph.py, intake_node.py, knowledge_node.py, action_node.py, escalation_node.py
api/__init__.py, main.py, auth.py, models.py
services/__init__.py, enterprise_api.py, audit_log.py
tracing/langsmith.py
tests/conftest.py, test_graph.py, test_api.py, test_enterprise_api.py
pyproject.toml, docker-compose.yml, infra/Dockerfile, .env.example, .gitignore, README.md
