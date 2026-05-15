"""LangSmith client initialisation and per-node span helpers."""

import os
from contextlib import contextmanager
from typing import Any, Generator

from dotenv import load_dotenv
from langsmith import Client
from langsmith import traceable  # re-exported for convenience

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    """Return a singleton LangSmith client, initialised from env vars."""
    global _client
    if _client is None:
        _client = Client(
            api_key=os.environ["LANGCHAIN_API_KEY"],
        )
    return _client


@contextmanager
def node_span(name: str, inputs: dict[str, Any]) -> Generator[None, None, None]:
    """Context manager that wraps an agent node in a LangSmith span.

    Usage::

        with node_span("intake_node", {"raw_text": state["raw_text"]}):
            ...  # node logic
    """
    project = os.getenv("LANGCHAIN_PROJECT", "neuradesk-dev")
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"

    if not tracing_enabled:
        yield
        return

    client = get_client()
    run = client.create_run(
        name=name,
        run_type="chain",
        inputs=inputs,
        project_name=project,
    )
    try:
        yield
        client.update_run(run.id, end_time=None, outputs={"status": "ok"})
    except Exception as exc:
        client.update_run(run.id, end_time=None, error=str(exc))
        raise


__all__ = ["get_client", "node_span", "traceable"]
