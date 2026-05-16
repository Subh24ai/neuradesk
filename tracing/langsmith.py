"""LangSmith trace URL utilities and @traceable re-export.

Helpers
-------
get_trace_url   — resolve a run URL from an explicit ID or the current run tree
print_trace_url — print that URL to stdout (no-op when tracing is off)
traceable       — re-exported from langsmith so callers import from one place
"""

from __future__ import annotations

import os
import urllib.parse

from dotenv import load_dotenv
from langsmith import traceable  # noqa: F401  re-exported

load_dotenv()


def get_trace_url(run_id: str | None = None) -> str | None:
    """Return the LangSmith trace URL for the given run ID (or the current active run).

    When run_id is None, attempts to resolve the ID from the currently executing
    run tree (only works inside a @traceable-decorated call stack).  Returns None
    when LANGCHAIN_TRACING_V2 is "false" or no active run can be found.

    Args:
        run_id: Explicit LangSmith run UUID.  Pass None to auto-detect.

    Returns:
        Full HTTPS URL string, or None.
    """
    if os.getenv("LANGCHAIN_TRACING_V2", "false").lower() != "true":
        return None

    if run_id is None:
        try:
            from langsmith.run_helpers import get_current_run_tree  # type: ignore[import]

            tree = get_current_run_tree()
            if tree is None:
                return None
            run_id = str(tree.id)
        except Exception:
            return None

    project = urllib.parse.quote(
        os.getenv("LANGCHAIN_PROJECT", "neuradesk-dev"), safe=""
    )
    return f"https://smith.langchain.com/projects/{project}/r/{run_id}"


def print_trace_url(run_id: str | None = None) -> None:
    """Print the LangSmith trace URL to stdout after a graph run.

    No-op when tracing is disabled or the URL cannot be resolved.

    Args:
        run_id: Optional explicit run ID.  Defaults to auto-detect from run tree.
    """
    url = get_trace_url(run_id)
    if url:
        print(f"\n[LangSmith] Trace: {url}\n", flush=True)


__all__ = ["get_trace_url", "print_trace_url", "traceable"]
