"""Input security utilities — prompt injection detection for ticket text.

The guard never blocks a ticket; it downgrades confidence so the graph routes
to a human instead of acting on potentially adversarial input.
"""

from __future__ import annotations

import re

import structlog

log = structlog.get_logger(__name__)

# Patterns that signal a prompt-injection attempt.
# Checked case-insensitively; each tuple is (label, compiled_pattern).
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("system_role_prefix",      re.compile(r"\bsystem\s*:", re.IGNORECASE)),
    ("ignore_previous",         re.compile(r"ignore\s+(previous|prior|all)\s+(instructions?|prompts?|rules?)", re.IGNORECASE)),
    ("forget_instructions",     re.compile(r"forget\s+(your\s+)?(instructions?|rules?|training)", re.IGNORECASE)),
    ("you_are_now",             re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE)),
    ("disregard_instructions",  re.compile(r"\bdisregard\s+(all\s+)?(previous\s+)?(instructions?|rules?)", re.IGNORECASE)),
    ("prompt_delimiter",        re.compile(r"\n\s*---+\s*\n", re.IGNORECASE)),
    ("jailbreak_marker",        re.compile(r"\[\s*(?:INST|SYS|SYSTEM|PROMPT)\s*\]", re.IGNORECASE)),
]

# Confidence is capped to this value when an injection pattern is detected.
_INJECTION_CONFIDENCE_CAP: float = 0.3


def input_guard(text: str) -> str | None:
    """Scan ticket text for prompt-injection patterns.

    Returns the label of the first matched pattern, or None if the text is clean.
    When a pattern is matched, the caller should cap the triage confidence to
    _INJECTION_CONFIDENCE_CAP so the ticket escalates to a human reviewer.

    Args:
        text: Raw ticket text (or vision-extracted text) before classification.

    Returns:
        Pattern label string if injection detected, None otherwise.
    """
    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            log.warning(
                "security.input_guard.injection_detected",
                pattern=label,
                text_preview=text[:120],
            )
            return label
    return None


def apply_injection_guard(text: str, confidence: float) -> float:
    """Return confidence unchanged if text is clean, or capped to 0.3 if injected.

    Convenience wrapper for intake_node: call after classify() to apply the cap.

    Args:
        text:       Ticket text that was classified.
        confidence: Raw confidence returned by the classifier.

    Returns:
        Original confidence, or _INJECTION_CONFIDENCE_CAP if injection detected.
    """
    matched = input_guard(text)
    if matched:
        return min(confidence, _INJECTION_CONFIDENCE_CAP)
    return confidence
