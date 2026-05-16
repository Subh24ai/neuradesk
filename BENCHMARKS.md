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
| RAG faithfulness score    | 1.000 (5-question eval, Groq judge) |
| RAG answer relevancy      | 0.633 (5-question eval, Groq judge) |
| Corpus size               | 10 documents, 50 chunks             |
| Dense retriever | FAISS + all-MiniLM-L6-v2 |
| Sparse retriever | BM25Okapi |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |

## End-to-End Latency

| Metric | Value |
|---|---|
| Ticket resolution latency (P50) | — (Week 4) |
| Ticket resolution latency (P95) | — (Week 4) |
| Target | < 2 s for auto-resolved tickets |

## System

| Metric | Value |
|---|---|
| Tests passing | 80 |
| Concurrent users tested | — (Week 4) |
