# NeuraDesk — Agentic IT/HR Service Platform

## What this is
A production multi-agent system that autonomously resolves enterprise IT/HR 
tickets. Employees submit requests (text or screenshot); 4 LangGraph agents 
triage, retrieve knowledge, call enterprise APIs, and resolve or escalate.

## Stack
- Python 3.11, FastAPI, LangGraph, LangChain
- FAISS + BM25 + cross-encoder reranking (RAG)
- DSPy for prompt optimization
- LangSmith for tracing
- React (TypeScript) frontend
- PostgreSQL via SQLAlchemy, Docker, GCP Cloud Run
- pytest + RAGAS for testing and RAG evaluation

## Project structure
neuradesk/
  agents/          # LangGraph nodes: intake, knowledge, action, escalation
  api/             # FastAPI routes, auth, websocket
  services/        # Mock enterprise APIs: ITSM, HR, IAM
  rag/             # FAISS index, BM25, reranker, knowledge loader
  dspy_modules/    # DSPy signatures and compiled classifiers
  tracing/         # LangSmith setup and span helpers
  tests/           # pytest unit + integration, RAGAS eval suite
  frontend/        # React TypeScript SPA
  infra/           # Dockerfile, docker-compose, GCP config

## Non-negotiable code rules
- Every function has a type hint and docstring
- Every agent node has a corresponding pytest test
- No hardcoded secrets — use python-dotenv and .env (gitignored)
- All API calls wrapped in try/except with structured error logging
- Destructive actions (access revoke, account lock) require explicit 
  confirmation — never auto-execute
- LangSmith tracing on every agent node — no silent execution
- Sub-2s response time target for all resolved tickets

## Key commands
- Run backend: uvicorn api.main:app --reload
- Run tests: pytest tests/ -v
- Run RAGAS eval: python tests/eval_rag.py
- Build docker: docker-compose up --build
- Lint: ruff check . && mypy .

## Always do
- Ask for a plan before writing any code for a new feature
- Write the test file alongside the implementation, not after
- Use FAISS + BM25 hybrid retrieval pattern from rag/retriever.py for 
  any new knowledge lookup
- Keep agent state typed with TypedDict — no raw dicts in LangGraph nodes