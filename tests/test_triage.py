"""Tests for dspy_modules.triage — all tests use DummyLM, no real API calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import dspy
import pytest
from dspy.utils import DummyLM

from dspy_modules.triage import (
    VALID_CATEGORIES,
    TriageClassifier,
    _get_classifier,
    classify,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _configure_dummy_lm():
    """Configure DSPy with a DummyLM for all tests in this module.

    autouse=True ensures no test accidentally makes a real API call.
    The DummyLM is replaced per-test by the individual fixtures below when a
    different answer set is needed.
    """
    dspy.configure(lm=DummyLM(answers=[
        {"category": "password_reset", "confidence": "0.92", "reasoning": "Default dummy answer."}
    ]))
    yield


def _make_lm(category: str, confidence: str, reasoning: str) -> DummyLM:
    """Return a DummyLM that always answers with the given field values."""
    return DummyLM(answers=[{"category": category, "confidence": confidence, "reasoning": reasoning}])


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestClassify:
    """Unit tests for the public classify() function."""

    def test_classify_returns_valid_category(self) -> None:
        """classify() must return a category that belongs to VALID_CATEGORIES."""
        dspy.configure(lm=_make_lm("password_reset", "0.92", "User forgot password."))
        cat, _ = classify("I can't log in to my computer")
        assert cat in VALID_CATEGORIES

    def test_classify_returns_confidence_float_between_0_and_1(self) -> None:
        """classify() must return a float confidence clamped to [0.0, 1.0]."""
        dspy.configure(lm=_make_lm("access_request", "0.88", "User needs permissions."))
        _, conf = classify("I need access to the production database")
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_classify_password_reset(self) -> None:
        """classify() returns ('password_reset', 0.95) for a typical reset ticket."""
        dspy.configure(lm=_make_lm("password_reset", "0.95", "User explicitly forgot password."))
        cat, conf = classify("I forgot my password and need to reset it")
        assert cat == "password_reset"
        assert conf == pytest.approx(0.95)

    def test_classify_access_request(self) -> None:
        """classify() returns 'access_request' for a permissions request."""
        dspy.configure(lm=_make_lm("access_request", "0.91", "User requires system access."))
        cat, _ = classify("Please grant me read access to the analytics data warehouse")
        assert cat == "access_request"

    def test_classify_software_install(self) -> None:
        """classify() returns 'software_install' for an installation request."""
        dspy.configure(lm=_make_lm("software_install", "0.94", "User requests software deployment."))
        cat, _ = classify("I need Docker Desktop installed on my MacBook")
        assert cat == "software_install"

    def test_classify_leave_approval(self) -> None:
        """classify() returns 'leave_approval' for a leave request."""
        dspy.configure(lm=_make_lm("leave_approval", "0.97", "Employee requesting annual leave."))
        cat, _ = classify("I'd like to take annual leave next week")
        assert cat == "leave_approval"

    def test_classify_incident_report(self) -> None:
        """classify() returns 'incident_report' for an outage report."""
        dspy.configure(lm=_make_lm("incident_report", "0.99", "Production service is down."))
        cat, _ = classify("The payment service is completely down, customers can't check out")
        assert cat == "incident_report"

    def test_classify_unknown_category(self) -> None:
        """classify() returns 'unknown' when the LM outputs an unrecognised category."""
        dspy.configure(lm=_make_lm("unknown", "0.60", "Does not match any category."))
        cat, _ = classify("Can you explain the company's side-project IP policy?")
        assert cat == "unknown"

    def test_classify_invalid_category_remapped_to_unknown(self) -> None:
        """An invalid LM category response is silently remapped to 'unknown'."""
        dspy.configure(lm=_make_lm("completely_invalid_label", "0.50", "Bad category."))
        cat, _ = classify("Something completely unrelated")
        assert cat == "unknown"

    def test_confidence_clamped_above_1(self) -> None:
        """Overconfident LM output (>1.0) is clamped to 1.0."""
        dspy.configure(lm=_make_lm("password_reset", "1.5", "Very confident."))
        _, conf = classify("Reset my password")
        assert conf <= 1.0

    def test_confidence_clamped_below_0(self) -> None:
        """Negative LM confidence output is clamped to 0.0."""
        dspy.configure(lm=_make_lm("password_reset", "-0.3", "Negative confidence."))
        _, conf = classify("Reset my password")
        assert conf >= 0.0

    def test_non_numeric_confidence_defaults_to_0_5(self) -> None:
        """DSPy parse failure (e.g. non-numeric confidence) falls back to ('unknown', 0.5).

        DSPy's ChatAdapter enforces float parsing via Pydantic before the Prediction
        reaches application code, so we inject the failure via mock rather than DummyLM.
        """
        with patch.object(TriageClassifier, "forward", side_effect=ValueError("unable to parse float")):
            cat, conf = classify("The server is down")
        assert cat == "unknown"
        assert conf == pytest.approx(0.5)


class TestCompiledLoad:
    """Tests for _get_classifier() compiled-file loading behaviour."""

    def test_compiled_program_loads_if_file_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_classifier() loads from triage_compiled.json without error."""
        # Save an uncompiled classifier (no LM call — just module state).
        save_path = tmp_path / "triage_compiled.json"
        TriageClassifier().save(str(save_path))

        monkeypatch.setattr("dspy_modules.triage._COMPILED_PATH", save_path)

        loaded = _get_classifier()
        assert loaded is not None
        assert isinstance(loaded, TriageClassifier)

    def test_missing_compiled_file_returns_uncompiled(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_classifier() silently returns an uncompiled classifier when file absent."""
        monkeypatch.setattr(
            "dspy_modules.triage._COMPILED_PATH",
            tmp_path / "does_not_exist.json",
        )
        classifier = _get_classifier()
        assert isinstance(classifier, TriageClassifier)

    def test_corrupted_compiled_file_falls_back_gracefully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A corrupt JSON file causes _get_classifier() to fall back, not crash."""
        bad_file = tmp_path / "triage_compiled.json"
        bad_file.write_text("{ this is not valid json !!!", encoding="utf-8")

        monkeypatch.setattr("dspy_modules.triage._COMPILED_PATH", bad_file)
        classifier = _get_classifier()
        assert isinstance(classifier, TriageClassifier)
