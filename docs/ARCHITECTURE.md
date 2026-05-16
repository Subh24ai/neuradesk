# NeuraDesk — Architecture

## Agent Communication Flow

```mermaid
flowchart TD
    U([Employee<br/>text or screenshot]) --> IN

    subgraph LangGraph["LangGraph Workflow — TicketState"]
        IN[Intake Agent<br/>DSPy classifier<br/>category · intent · priority · confidence]
        KN[Knowledge Agent<br/>FAISS + BM25 + cross-encoder<br/>retrieved_chunks · resolution_template]
        AC[Action Agent<br/>Enterprise API dispatch<br/>confirmation gate for destructive ops]
        ES[Escalation Agent<br/>human handoff with full state]

        IN -->|always| KN
        KN -->|always| AC
        AC -->|status=resolved<br/>confidence≥0.6<br/>category≠unknown| DONE
        AC -->|status=escalated<br/>OR confidence<0.6<br/>OR category=unknown| ES
        ES --> HQ
    end

    DONE([Ticket Resolved<br/>resolution + trace_url])
    HQ([Human Queue<br/>full state attached])

    LangSmith[(LangSmith<br/>every node traced)]
    IN -.->|@traceable span| LangSmith
    KN -.->|@traceable span| LangSmith
    AC -.->|@traceable span| LangSmith
    ES -.->|@traceable span| LangSmith
```

---

## Guardrail Specification

Every destructive operation is gated by an explicit confirmation flag in `TicketState`.
The action node checks this before dispatching — it never auto-executes.

| Guard | Trigger | Behaviour |
|---|---|---|
| **Destructive action gate** | `action_taken` ∈ `{password_reset, provision_access}` | Requires `action_confirmed=True` in state; escalates with reason `"Destructive action requires explicit confirmation"` if absent |
| **Confidence threshold** | `confidence < 0.6` after intake | Routing function in `graph.py` sends ticket to escalation without reaching action |
| **Unknown category** | `category == "unknown"` | Short-circuits to escalation — no knowledge retrieval attempted |
| **API error escalation** | Any `httpx` exception in action node | Sets `status="escalated"`, `error=str(exc)`, routes to escalation node |
| **LangSmith silent-execution ban** | Project-wide (CLAUDE.md) | Every node decorated with `@traceable` — untraceable execution is a failing test |

---

## Context Engineering Decisions

### 1. Single TypedDict state threaded through every node

`TicketState` is a flat `TypedDict` defined once in `agents/state.py` and passed by value through every LangGraph node.

**Why:** LangGraph merges node outputs into the running state automatically. A flat TypedDict with `Optional` fields means each node only sets the fields it owns — no node needs to know what another node wrote, and the type checker catches missing fields at import time rather than at runtime.

**Alternative considered:** nested dicts per agent (intake_output, knowledge_output, …). Rejected because cross-node references (action_node reading `retrieved_chunks` from knowledge_node) require passing the entire parent dict, losing static typing.

---

### 2. Hybrid FAISS + BM25 retrieval with cross-encoder reranking

The retriever (`rag/retriever.py`) runs FAISS and BM25 in parallel, merges results by rank, then re-scores the top-k with a cross-encoder.

**Why:** Dense retrieval (FAISS + sentence-transformers) excels at semantic similarity but misses exact keyword matches. Sparse retrieval (BM25) nails exact matches but is blind to paraphrase. Cross-encoder reranking corrects both: it sees the full query-chunk pair and produces calibrated relevance scores. RAGAS faithfulness reached **1.000** with this pipeline on the 10-document corpus.

**Trade-off:** The cross-encoder adds ~150ms latency per retrieval call. Acceptable given the 2s end-to-end target for resolved tickets.

---

### 3. DSPy offline prompt compilation

The triage classifier (`dspy_modules/triage.py`) is compiled once with `BootstrapFewShot` and the result serialised to `triage_compiled.json`. The API loads the compiled program at startup; DSPy's optimiser never runs in the hot path.

**Why:** Online prompt optimisation adds 3–10s of LLM calls per request. Offline compilation gives the performance of a fine-tuned few-shot prompt with no per-request cost. Accuracy jumped from **66.7% → 93.3%** on the held-out validation set.

**Invariant:** If `triage_compiled.json` is absent the code falls back to the uncompiled signature (tested in `test_triage.py::test_missing_compiled_file_returns_uncompiled`).

---

### 4. Explicit confirmation gate for destructive operations

The action node checks `state["action_confirmed"]` before calling any API marked destructive (`password_reset`, `provision_access`). If the flag is absent the node sets `status="escalated"` without making the API call.

**Why:** Autonomous agents that silently reset passwords or revoke access at scale are a security and compliance liability. The gate means an orchestrator (or the future UI) must explicitly set `action_confirmed=True` — it cannot happen by omission. The test `test_destructive_action_blocked_without_confirmation` enforces this invariant.

---

### 5. A2A protocol on the knowledge agent

The knowledge agent is exposed as a standalone A2A-compatible endpoint (`/tasks/send`, `/tasks/sendSubscribe`). Any external orchestrator can call it directly without going through the full 4-agent graph.

**Why:** Enterprise IT environments often have existing ticketing orchestrators (ServiceNow, Jira Service Management) that want to call a specific AI skill rather than run a full graph. Wrapping the knowledge node in A2A makes NeuraDesk interoperable with those systems at zero extra cost. See `docs/a2a-agent-card.md` for the full spec.

---

### 6. WebSocket streaming for the frontend

The API exposes `GET /ws/{ticket_id}` which streams per-node events as each LangGraph node completes. The frontend renders a live timeline without polling.

**Why:** A synchronous `POST /tickets` endpoint (which also exists) blocks the HTTP response for the full graph duration — typically 1–4s. WebSocket streaming makes every node transition visible in real time, giving users confidence the system is working rather than showing a blank spinner.

**Implementation detail:** `graph.stream(..., stream_mode="updates")` runs in a background thread (blocking I/O), pushing events onto an `asyncio.Queue`. The async WebSocket handler drains the queue, keeping the event loop free.
