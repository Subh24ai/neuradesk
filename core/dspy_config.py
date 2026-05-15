"""DSPy LM configuration — call configure_dspy() once at app startup."""

import os

import dspy


def configure_dspy() -> None:
    """Configure the global DSPy LM from environment variables.

    Idempotent: returns immediately if an LM is already configured, so it is
    safe to call from module level in submodules (e.g. triage.py) and again
    from the FastAPI lifespan without double-configuring.

    LLM_PROVIDER (default: "groq"):
        - "groq"      → dspy.LM("groq/<GROQ_MODEL>")
        - "anthropic" → dspy.LM("anthropic/claude-sonnet-4-20250514")
    """
    if dspy.settings.lm is not None:
        return

    provider: str = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        lm = dspy.LM(
            f"groq/{model}",
            api_key=os.getenv("GROQ_API_KEY", ""),
        )
    elif provider == "anthropic":
        lm = dspy.LM(
            "anthropic/claude-sonnet-4-20250514",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )
    else:
        # Fallback: let DSPy raise a clear error rather than silently misconfiguring.
        raise ValueError(
            f"configure_dspy: unsupported LLM_PROVIDER={provider!r}. "
            "Choose from: groq, anthropic"
        )

    dspy.configure(lm=lm)
