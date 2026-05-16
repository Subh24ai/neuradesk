# NeuraDesk Benchmarks

Metrics collected during development.  Week 4 targets include load-test numbers and RAGAS scores.

## DSPy Triage Classifier

| Metric | Value |
|---|---|
| DSPy classifier accuracy (before) | 66.7% (10/15) |
| DSPy classifier accuracy (after)  | 93.3% (14/15) |
| DSPy error reduction              | 40% via BootstrapFewShot |
| Training set | 45 synthetic examples (10 per category) |
| Validation set | 15 synthetic examples (held-out) |
| Optimizer | BootstrapFewShot, max_bootstrapped_demos=4 |
| Model | llama-3.3-70b-versatile (Groq) |

## RAG Retrieval Pipeline

| Metric | Value |
|---|---|
| RAG faithfulness score    | 1.000 (10-question eval, llama-3.1-8b-instant judge) |
| RAG answer relevancy      | 0.439 (10-question eval)                             |
| Eval methodology          | RAGAS, Groq LLM judge, HuggingFace embeddings,       |
|                           | max_workers=1, nan-safe aggregation                  |
| Eval set                  | 2 questions × 5 categories                          |
| Corpus size               | 10 documents, 50 chunks                              |
| Dense retriever | FAISS + all-MiniLM-L6-v2 |
| Sparse retriever | BM25Okapi |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |

## End-to-End Latency

100-ticket simulation via `tests/load_test.py`.
Backend: SQLite (local dev), concurrency=3 workers, LLM: llama-3.3-70b-versatile (Groq).

| Metric | Value |
|---|---|
| Ticket resolution latency (P50) | 4.28 s |
| Ticket resolution latency (P95) | 4.71 s |
| Ticket resolution latency (mean) | 3.12 s |
| Ticket resolution latency (min) | 0.30 s |
| Ticket resolution latency (max) | 5.72 s |
| Total run time (100 tickets, 3 workers) | 104.7 s |
| Success rate | 100 / 100 |
| Target | < 2 s for auto-resolved tickets (Cloud Run + Postgres) |

\* Latency measured with Groq cloud LLM (llama-3.1-70b-versatile).
Breakdown: RAG retrieval ~0.3s, LLM round-trip ~2–4s per node.
Sub-2s achievable with: local vLLM inference, Anthropic claude-haiku,
or tickets hitting the fast-path (unknown category exits before retrieval).
Production target: P50 < 2s with dedicated inference.

## System

| Metric | Value |
|---|---|
| Tests passing | 111 |
| Concurrent workers (load test) | 3 |
| Tickets simulated | 100 |
