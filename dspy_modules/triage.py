"""DSPy triage classifier — categorises IT/HR support tickets.

Public API:
    classify(text: str) -> tuple[str, float]

Compile and evaluate via __main__:
    python -m dspy_modules.triage
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import dspy
import structlog
from dotenv import load_dotenv

from core.dspy_config import configure_dspy
from dspy_modules.training_data import TRAINING_EXAMPLES

# Auto-configure the DSPy LM when this module is imported outside FastAPI.
# configure_dspy() is idempotent — it is a no-op if an LM is already set
# (e.g. by FastAPI lifespan or a test fixture's DummyLM).
load_dotenv()
configure_dspy()

log = structlog.get_logger(__name__)

_COMPILED_PATH: Path = Path(__file__).parent / "triage_compiled.json"

VALID_CATEGORIES: frozenset[str] = frozenset({
    "password_reset",
    "access_request",
    "software_install",
    "leave_approval",
    "incident_report",
    "access_revoke",
    "account_lock",
    "account_delete",
    "unknown",
})


# ── Signature ─────────────────────────────────────────────────────────────────


class TriageSignature(dspy.Signature):
    """Classify an enterprise IT/HR support ticket into the correct service category.

    Categories:
      password_reset    — user forgot their password or was locked out by failed
                          login attempts and needs it reset.
      access_request    — grant NEW access or permissions to a resource.
      software_install  — install or deploy software on a device.
      leave_approval    — request to take leave / PTO / time off.
      incident_report   — an outage, breach, or service degradation.
      access_revoke     — REMOVE existing access or permissions from a user
                          (offboarding, role change). Destructive.
      account_lock      — disable, lock, suspend, or freeze a user's account or
                          login (security or offboarding). Destructive.
      account_delete    — permanently delete or remove a user account. Destructive.
      unknown           — does not fit any category above.

    Disambiguation: access_request GRANTS access while access_revoke REMOVES it;
    password_reset restores a user's own login while account_lock deliberately
    disables someone's account.
    """

    ticket_text: str = dspy.InputField(
        desc="Raw support ticket text submitted by the employee."
    )
    category: str = dspy.OutputField(
        desc=(
            "Ticket category — one of: password_reset, access_request, "
            "software_install, leave_approval, incident_report, access_revoke, "
            "account_lock, account_delete, unknown."
        )
    )
    confidence: float = dspy.OutputField(
        desc="Confidence score as a decimal between 0.0 and 1.0."
    )
    reasoning: str = dspy.OutputField(
        desc="One-sentence explanation of why this category was chosen."
    )


# ── Module ────────────────────────────────────────────────────────────────────


class TriageClassifier(dspy.Module):
    """DSPy module that wraps TriageSignature with a single Predict call."""

    def __init__(self) -> None:
        """Initialise the predictor."""
        super().__init__()
        self.predict: dspy.Predict = dspy.Predict(TriageSignature)

    def forward(self, ticket_text: str) -> dspy.Prediction:
        """Run the classifier on a single ticket text.

        Args:
            ticket_text: Raw employee support ticket.

        Returns:
            dspy.Prediction with fields: category, confidence, reasoning.
        """
        return self.predict(ticket_text=ticket_text)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_confidence(raw: Any) -> float:
    """Coerce raw confidence output to a float clamped to [0.0, 1.0].

    Args:
        raw: Raw value from the DSPy prediction (may be str, float, or None).

    Returns:
        Float in [0.0, 1.0]; defaults to 0.5 on any parse error.
    """
    try:
        return max(0.0, min(1.0, float(raw)))
    except (ValueError, TypeError):
        return 0.5

_classifier: TriageClassifier | None = None


def _get_classifier() -> TriageClassifier:
    """Return a TriageClassifier, loading compiled weights when available.

    Falls back to an uncompiled classifier if the compiled file is missing or
    fails to load — never raises. Singleton: built once per process.
    """
    global _classifier
    if _classifier is not None:
        return _classifier
    classifier = TriageClassifier()
    if _COMPILED_PATH.exists():
        try:
            classifier.load(str(_COMPILED_PATH))
            log.info("triage.loaded_compiled", path=str(_COMPILED_PATH))
        except Exception as exc:
            log.warning("triage.load_failed_fallback_to_uncompiled", error=str(exc))
    _classifier = classifier
    return _classifier


# ── Public API ────────────────────────────────────────────────────────────────


def classify(text: str) -> tuple[str, float]:
    """Classify a ticket text into a category and return confidence.

    Loads the compiled classifier from dspy_modules/triage_compiled.json when
    present; falls back to the uncompiled predictor otherwise.

    Args:
        text: Raw ticket text from the employee.

    Returns:
        Tuple of (category, confidence) where category is one of VALID_CATEGORIES
        and confidence is clamped to [0.0, 1.0].
    """
    classifier = _get_classifier()
    try:
        prediction = classifier(ticket_text=text)
    except Exception as exc:
        # DSPy's adapter raises if it cannot parse a typed output field (e.g.
        # confidence: float when the LM returns a non-numeric string).  Fall
        # back to a safe default rather than propagating the error.
        log.warning("triage.parse_error_fallback", error=str(exc))
        return "unknown", 0.5

    raw_category = str(prediction.category).strip().lower()
    category = raw_category if raw_category in VALID_CATEGORIES else "unknown"
    confidence = _safe_confidence(prediction.confidence)

    log.info("triage.classified", category=category, confidence=confidence)
    return category, confidence


# ── Metric ────────────────────────────────────────────────────────────────────


def triage_metric(
    example: dspy.Example, prediction: dspy.Prediction, trace: Any = None
) -> bool:
    """Return True when the predicted category matches the gold label.

    Args:
        example: A labelled dspy.Example from training data.
        prediction: The model's dspy.Prediction.
        trace: Unused — required by BootstrapFewShot signature.

    Returns:
        True if predicted category matches example.category (case-insensitive).
    """
    return (
        str(prediction.category).strip().lower()
        == str(example.category).strip().lower()
    )


# ── Compilation ───────────────────────────────────────────────────────────────


# Examples held out per category for validation; the remainder are used to train.
_VAL_PER_CATEGORY: int = 3


def _stratified_split(
    examples: list[dspy.Example],
) -> tuple[list[dspy.Example], list[dspy.Example]]:
    """Split examples into (train, val), holding out _VAL_PER_CATEGORY per category.

    Stratifying keeps every category represented in both splits so the compiled
    demos and the before/after benchmark cover all 9 categories — including the
    destructive ones appended to the end of TRAINING_EXAMPLES. The previous
    fixed examples[:45]/[45:] slice silently excluded the new categories.
    """
    by_cat: dict[str, list[dspy.Example]] = {}
    for ex in examples:
        by_cat.setdefault(str(ex.category), []).append(ex)
    train: list[dspy.Example] = []
    val: list[dspy.Example] = []
    for cat_examples in by_cat.values():
        val.extend(cat_examples[:_VAL_PER_CATEGORY])
        train.extend(cat_examples[_VAL_PER_CATEGORY:])
    return train, val


def compile_classifier(lm: Any) -> TriageClassifier:
    """Compile TriageClassifier with BootstrapFewShot on the training data.

    Uses a stratified train split (every category represented), runs
    BootstrapFewShot, and saves the compiled program to triage_compiled.json.

    Args:
        lm: A DSPy-compatible language model instance.

    Returns:
        The compiled TriageClassifier with bootstrapped demonstrations.
    """
    from dspy.teleprompt import BootstrapFewShot

    dspy.configure(lm=lm)

    examples = [
        dspy.Example(**ex).with_inputs("ticket_text") for ex in TRAINING_EXAMPLES
    ]
    trainset, _ = _stratified_split(examples)

    teleprompter = BootstrapFewShot(metric=triage_metric, max_bootstrapped_demos=4)
    compiled: TriageClassifier = teleprompter.compile(
        TriageClassifier(), trainset=trainset
    )
    compiled.save(str(_COMPILED_PATH))
    log.info("triage.compiled_saved", path=str(_COMPILED_PATH))
    return compiled


# ── __main__ — real API calls, run manually ───────────────────────────────────


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        print("ERROR: GROQ_API_KEY is not set in .env")
        sys.exit(1)

    lm = dspy.LM(
        f"groq/{os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')}",
        api_key=groq_key,
    )
    dspy.configure(lm=lm)

    examples = [
        dspy.Example(**ex).with_inputs("ticket_text") for ex in TRAINING_EXAMPLES
    ]
    _, valset = _stratified_split(examples)  # 3 per category held out (27 total)

    # ── Before compilation ────────────────────────────────────────────────────
    uncompiled = TriageClassifier()
    before_correct = sum(
        triage_metric(ex, uncompiled(ticket_text=ex.ticket_text)) for ex in valset
    )
    print(f"Before: {before_correct}/{len(valset)}")

    # ── Compile ───────────────────────────────────────────────────────────────
    compiled = compile_classifier(lm)

    # ── After compilation ─────────────────────────────────────────────────────
    after_correct = sum(
        triage_metric(ex, compiled(ticket_text=ex.ticket_text)) for ex in valset
    )
    print(f"After: {after_correct}/{len(valset)}")
