"""LangChain chat-model factory — select provider via LLM_PROVIDER env var."""

import os
from typing import Union

from langchain_core.language_models.chat_models import BaseChatModel

from core.config import get_settings

_cfg = get_settings()


def get_llm() -> BaseChatModel:
    """Return a LangChain chat model for the configured provider.

    LLM_PROVIDER (default: "groq"):
        - "groq"      → ChatGroq using GROQ_MODEL / GROQ_API_KEY
        - "anthropic" → ChatAnthropic claude-sonnet-4-20250514
        - "openai"    → ChatOpenAI gpt-4o-mini
    """
    provider: str = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        from langchain_groq import ChatGroq  # type: ignore[import-untyped]

        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.getenv("GROQ_API_KEY", ""),
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]

        return ChatAnthropic(
            model=_cfg.claude_model,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )

    if provider == "openai":
        # Requires the optional OpenAI extra: pip install -e ".[openai]"
        from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]

        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Choose from: groq, anthropic, openai"
    )
