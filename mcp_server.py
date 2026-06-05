"""NeuraDesk MCP tool server (stdio transport).

Exposes a read-only slice of NeuraDesk to MCP clients (e.g. Claude Desktop) as
four tools backed by the same RAG retriever, database, and category taxonomy the
agent graph uses. Run directly over stdio:

    python mcp_server.py

This is the stdio sibling of the HTTP/SSE A2A surface in api/a2a.py. Because the
client launches it locally over stdio, it carries no bearer auth (unlike the A2A
and enterprise APIs).
"""

from contextlib import contextmanager
from typing import Iterator

from mcp.server.fastmcp import FastMCP

# api.models runs load_dotenv() at import, so DATABASE_URL is loaded before the
# engine is created. Importing it first also means env is set before triage's
# module-level DSPy configuration runs.
from api.models import OrgKnowledgeDocModel, SessionLocal, TicketModel
from dspy_modules.triage import VALID_CATEGORIES
from rag.retriever import get_retriever

mcp = FastMCP("neuradesk")

# ── Category metadata ─────────────────────────────────────────────────────────
# Human-readable descriptions, mirroring the TriageSignature taxonomy text.
# The import-time assert below guarantees these never drift from the classifier's
# VALID_CATEGORIES (single source of truth in dspy_modules/triage.py).
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "password_reset": "User forgot their password or was locked out by failed login attempts and needs it reset.",
    "access_request": "Grant new access or permissions to a resource.",
    "software_install": "Install or deploy software on a device.",
    "leave_approval": "Request to take leave, PTO, or time off.",
    "incident_report": "Report an outage, security breach, or service degradation.",
    "access_revoke": "Remove existing access or permissions from a user (offboarding, role change). Destructive.",
    "account_lock": "Disable, lock, suspend, or freeze a user's account or login. Destructive.",
    "account_delete": "Permanently delete or remove a user account. Destructive.",
    "unknown": "Does not fit any defined IT/HR service category.",
}

assert set(CATEGORY_DESCRIPTIONS) == set(VALID_CATEGORIES), (
    "CATEGORY_DESCRIPTIONS drifted from VALID_CATEGORIES: "
    f"missing={set(VALID_CATEGORIES) - set(CATEGORY_DESCRIPTIONS)}, "
    f"extra={set(CATEGORY_DESCRIPTIONS) - set(VALID_CATEGORIES)}"
)

# Canonical retrieval query per category, used by resolve_ticket_info to pull the
# most relevant runbook/policy chunks from the knowledge base.
CATEGORY_QUERIES: dict[str, str] = {
    "password_reset": "reset forgotten password account locked login credentials",
    "access_request": "request access provision permissions role resource",
    "software_install": "install software application tool device deployment",
    "leave_approval": "leave approval PTO vacation time off request",
    "incident_report": "incident outage report severity response escalation",
    "access_revoke": "revoke remove access permissions offboarding deprovision",
    "account_lock": "lock disable suspend account login security",
    "account_delete": "delete remove account offboarded user permanently",
    "unknown": "general help support request",
}

# ── DB session seam (monkeypatched in tests) ──────────────────────────────────
_session_factory = SessionLocal


@contextmanager
def _session() -> Iterator:
    """Yield a DB session from the current factory, closing it on exit."""
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()


def _load_org_chunks(org_id: str) -> list[dict]:
    """Return this org's private KB docs as [{title, content}] for retrieval merge."""
    if not org_id:
        return []
    with _session() as db:
        rows = (
            db.query(OrgKnowledgeDocModel)
            .filter(OrgKnowledgeDocModel.org_id == org_id)
            .all()
        )
        return [{"title": r.title, "content": r.content} for r in rows]


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp.tool()
def search_knowledge(query: str, org_id: str) -> dict:
    """Search the NeuraDesk knowledge base for a free-text query.

    Runs hybrid FAISS + BM25 + cross-encoder retrieval over the global IT/HR
    runbooks and the given organisation's private knowledge-base documents, and
    returns the top 3 matching chunks with their source and relevance score.

    Args:
        query: Natural-language question or keywords to search for.
        org_id: Organisation ID whose private KB docs are merged into the search
            (pass an empty string to search only the global knowledge base).

    Returns:
        {"query", "org_id", "results": [{"source", "content", "score"}, ...]}
    """
    org_chunks = _load_org_chunks(org_id)
    chunks = get_retriever().search(query, top_k=3, org_chunks=org_chunks or None)
    return {"query": query, "org_id": org_id, "results": [dict(c) for c in chunks]}


@mcp.tool()
def get_ticket_status(ticket_id: str) -> dict:
    """Look up the current status and resolution of a support ticket by its ID.

    Args:
        ticket_id: The ticket's UUID.

    Returns:
        When found: {"found": true, "ticket_id", "status", "category", "intent",
        "confidence", "resolution", "escalation_reason", "assignee_group",
        "priority", "created_at"}. When not found: {"found": false, "ticket_id",
        "error"}.
    """
    with _session() as db:
        ticket = db.get(TicketModel, ticket_id)
        if ticket is None:
            return {"found": False, "ticket_id": ticket_id, "error": "Ticket not found"}
        return {
            "found": True,
            "ticket_id": ticket.id,
            "status": ticket.status,
            "category": ticket.category,
            "intent": ticket.intent,
            "confidence": ticket.confidence,
            "resolution": ticket.resolution,
            "escalation_reason": ticket.escalation_reason,
            "assignee_group": ticket.assignee_group,
            "priority": ticket.priority,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        }


@mcp.tool()
def resolve_ticket_info(category: str) -> dict:
    """Return knowledge-base resolution steps for a given ticket category.

    Retrieves the top 3 most relevant runbook/policy chunks for the category from
    the knowledge base. Retrieval-only — does not call an LLM.

    Args:
        category: One of the supported ticket categories (see
            list_ticket_categories).

    Returns:
        When valid: {"category", "valid": true, "description",
        "steps": [{"source", "content", "score"}, ...]}. When the category is not
        recognised: {"category", "valid": false, "description": null, "steps": [],
        "error"}.
    """
    normalized = category.strip().lower()
    if normalized not in VALID_CATEGORIES:
        return {
            "category": category,
            "valid": False,
            "description": None,
            "steps": [],
            "error": f"Unknown category. Valid categories: {sorted(VALID_CATEGORIES)}",
        }
    query = CATEGORY_QUERIES.get(normalized, normalized.replace("_", " "))
    chunks = get_retriever().search(query, top_k=3)
    return {
        "category": normalized,
        "valid": True,
        "description": CATEGORY_DESCRIPTIONS[normalized],
        "steps": [dict(c) for c in chunks],
    }


@mcp.tool()
def list_ticket_categories() -> dict:
    """List every supported ticket category with its description.

    Returns:
        {"categories": [{"category", "description"}, ...]} covering all categories
        the NeuraDesk triage classifier can assign.
    """
    return {
        "categories": [
            {"category": c, "description": CATEGORY_DESCRIPTIONS[c]}
            for c in CATEGORY_DESCRIPTIONS
        ]
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
