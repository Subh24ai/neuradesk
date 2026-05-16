# NeuraDesk Knowledge Agent — A2A Agent Card

The NeuraDesk Knowledge Agent implements the [Google A2A protocol](https://google.github.io/A2A/).
Any A2A-compatible orchestrator can discover this agent at `/.well-known/agent.json` and submit
natural-language IT/HR queries to receive grounded, knowledge-base-backed answers.

---

## Agent Card (`GET /.well-known/agent.json`)

```json
{
  "name": "NeuraDesk Knowledge Agent",
  "description": "Resolves IT and HR support queries using hybrid FAISS + BM25 retrieval over the NeuraDesk knowledge base. Returns a grounded one-sentence resolution together with the source chunks.",
  "url": "http://<host>",
  "version": "1.0.0",
  "documentationUrl": "/docs",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": false
  },
  "authentication": {
    "schemes": ["none"]
  },
  // authentication: none — internal network only.
  // Production: add mTLS or API key per A2A spec section 8.
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "knowledge_retrieval",
      "name": "IT/HR Knowledge Retrieval",
      "description": "Answer IT and HR support questions using the internal knowledge base. Covers: password reset, access requests, software installation, leave approval, and incident reporting.",
      "tags": ["itsm", "hr", "knowledge-base", "rag"],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"],
      "examples": [
        "How do I reset my corporate password?",
        "What is the process for requesting software installation?",
        "How do I apply for annual leave?",
        "What are the P1 incident response times?"
      ]
    }
  ]
}
```

### Field reference

| Field | Type | Description |
|---|---|---|
| `name` | string | Human-readable agent name |
| `description` | string | What this agent does |
| `url` | string | Base URL — populated dynamically from the incoming request host |
| `version` | string | Semantic version of this agent implementation |
| `capabilities.streaming` | bool | `true` — `/tasks/sendSubscribe` is supported |
| `capabilities.pushNotifications` | bool | `false` — push callbacks are not implemented |
| `authentication.schemes` | array | `["none"]` — no auth required (internal network agent) |
| `skills[0].id` | string | Stable skill identifier for orchestrators to reference |

---

## Endpoints

### `POST /tasks/send` — Synchronous task

Submit a query and block until the answer is ready.

**Request body (A2A Task)**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "sessionId": "550e8400-e29b-41d4-a716-446655440001",
  "message": {
    "role": "user",
    "parts": [
      {
        "type": "text",
        "text": "How do I reset my corporate password?"
      }
    ]
  }
}
```

| Field | Required | Description |
|---|---|---|
| `id` | No | Task UUID — auto-generated if omitted |
| `sessionId` | No | Conversation session UUID — auto-generated if omitted |
| `message.role` | Yes | Must be `"user"` |
| `message.parts` | Yes | At least one `{"type": "text", "text": "..."}` part |

**Response (completed Task)**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "sessionId": "550e8400-e29b-41d4-a716-446655440001",
  "status": {
    "state": "completed",
    "timestamp": "2026-05-16T10:00:00+00:00"
  },
  "artifacts": [
    {
      "name": "resolution",
      "index": 0,
      "lastChunk": true,
      "parts": [
        {
          "type": "text",
          "text": "Navigate to the IT Self-Service Portal, select Reset Password, verify your identity, and a temporary password will be emailed to you."
        }
      ]
    }
  ],
  "metadata": {
    "chunks_retrieved": 3,
    "sources": [
      "kb/password-reset-runbook.md",
      "kb/it-self-service-portal.md",
      "kb/active-directory-policy.md"
    ]
  }
}
```

**`status.state` values**

| State | Meaning |
|---|---|
| `completed` | Answer was retrieved successfully |
| `failed` | No text query in message parts, or retrieval error |

---

### `POST /tasks/sendSubscribe` — SSE streaming task

Submit a query and receive real-time status events via [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events).
Request body is identical to `/tasks/send`.

**Event sequence (guaranteed order)**

```
data: {"id": "...", "status": {"state": "working", "timestamp": "...", "message": {...}}}

data: {"id": "...", "artifact": {"name": "resolution", "index": 0, "lastChunk": true, "parts": [{"type": "text", "text": "..."}], "metadata": {...}}}

data: {"id": "...", "status": {"state": "completed", "timestamp": "..."}, "final": true}
```

1. **`working`** — Emitted immediately; signals retrieval has started.
2. **`artifact`** — Carries the resolution text and source metadata.
3. **`completed`** — Final event; `"final": true` signals end of stream.

On empty query or retrieval error the sequence is:

```
data: {"id": "...", "status": {"state": "working", ...}}

data: {"id": "...", "status": {"state": "failed", ...}, "final": true}
```

**SSE event fields**

| Field | Present on | Description |
|---|---|---|
| `id` | all events | Echoes the submitted task `id` |
| `status.state` | status events | `working`, `completed`, or `failed` |
| `status.timestamp` | status events | ISO 8601 UTC timestamp |
| `artifact` | artifact event | Resolution text + source metadata |
| `final` | last event | `true` — client can close the connection |

---

## Integration example (Python)

```python
import httpx, json

BASE = "http://localhost:8000"

# 1. Discover the agent
card = httpx.get(f"{BASE}/.well-known/agent.json").json()
print(card["name"], card["version"])

# 2. Synchronous query
task = {
    "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "How do I apply for annual leave?"}],
    }
}
result = httpx.post(f"{BASE}/tasks/send", json=task).json()
print(result["artifacts"][0]["parts"][0]["text"])

# 3. Streaming query
with httpx.stream("POST", f"{BASE}/tasks/sendSubscribe", json=task) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            event = json.loads(line[5:].strip())
            if "artifact" in event:
                print(event["artifact"]["parts"][0]["text"])
            if event.get("final"):
                break
```
