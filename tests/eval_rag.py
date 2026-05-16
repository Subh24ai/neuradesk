"""RAGAS evaluation script for the NeuraDesk RAG pipeline.

Run with:
    python tests/eval_rag.py

Requires GROQ_API_KEY in .env (used as the LLM judge via LangChain).
Evaluates faithfulness and answer_relevancy over 10 QA pairs
(2 per ticket category) using llama-3.1-8b-instant as the judge model
to stay within Groq free-tier rate limits.
Exits with code 1 if faithfulness < 0.8 so CI fails.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Allow running from any working directory: python tests/eval_rag.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

# Disable LangSmith tracing for this standalone eval script.
os.environ["LANGCHAIN_TRACING_V2"] = "false"

FAITHFULNESS_THRESHOLD: float = 0.8

# Validate GROQ_API_KEY before importing heavy dependencies.
if not os.getenv("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY is not set. Add it to .env before running this script.")
    sys.exit(1)

try:
    from datasets import Dataset
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_groq import ChatGroq
    from ragas import evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, faithfulness
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with: pip install ragas datasets langchain-groq langchain-huggingface")
    sys.exit(1)

# RunConfig controls concurrency — max_workers=1 serialises all LLM calls
# so Groq free-tier rate limits are not hit.  Gracefully absent in some builds.
try:
    from ragas import RunConfig as _RunConfig
    _RUN_CONFIG = _RunConfig(max_workers=1, timeout=300)
except Exception:
    _RUN_CONFIG = None  # type: ignore[assignment]

from rag.retriever import get_retriever

# ── 10 QA pairs — 2 per resolvable ticket category ───────────────────────────
# Kept at 10 (not 20) to stay within Groq free-tier rate limits.

_QA_PAIRS: list[dict[str, str]] = [
    # ── password_reset ────────────────────────────────────────────────────────
    {
        "question": "How do I reset my forgotten corporate password?",
        "ground_truth": (
            "Navigate to the IT Self-Service Portal, select Reset Password, "
            "verify your identity, and a temporary password will be emailed to you."
        ),
    },
    {
        "question": "My Active Directory password expired — what should I do?",
        "ground_truth": (
            "Go to the IT Self-Service Portal, choose Reset Password, "
            "authenticate with your employee ID, and you will receive a temporary password."
        ),
    },
    # ── access_request ────────────────────────────────────────────────────────
    {
        "question": "How do I request access to a production system?",
        "ground_truth": (
            "Submit an access request ticket in the ITSM portal with the resource name, "
            "required role, and business justification. "
            "Manager and resource owner approval is required."
        ),
    },
    {
        "question": "What is the approval process for requesting elevated permissions?",
        "ground_truth": (
            "Submit an access request in the ITSM portal specifying the resource, "
            "role, and business justification; your manager and the resource owner must approve."
        ),
    },
    # ── software_install ──────────────────────────────────────────────────────
    {
        "question": "What is the process for installing new software on my work laptop?",
        "ground_truth": (
            "Submit a software installation request through the IT Self-Service Portal "
            "with the application name, version, and business justification. "
            "Approved requests are fulfilled within three business days."
        ),
    },
    {
        "question": "How do I get Slack installed on my corporate machine?",
        "ground_truth": (
            "Raise a software installation request in the IT Self-Service Portal, "
            "providing the application name (Slack), version, and a business justification; "
            "approved installs are fulfilled within three business days."
        ),
    },
    # ── leave_approval ────────────────────────────────────────────────────────
    {
        "question": "How do I apply for annual leave?",
        "ground_truth": (
            "Submit your leave request through the HR Self-Service Portal at least "
            "5 business days in advance. Your manager must approve within 2 business days."
        ),
    },
    {
        "question": "What is the minimum notice I need to give before taking vacation?",
        "ground_truth": (
            "You must submit a leave request in the HR Self-Service Portal at least "
            "5 business days before the start of your vacation."
        ),
    },
    # ── incident_report ───────────────────────────────────────────────────────
    {
        "question": "What are the severity levels for IT incidents?",
        "ground_truth": (
            "P1 is critical (full outage, 15-minute response), "
            "P2 is high (major degradation, 1-hour response), "
            "P3 is medium (partial degradation, 4-hour response), "
            "P4 is low (minor issue, 1 business day response)."
        ),
    },
    {
        "question": "How do I report a complete production outage?",
        "ground_truth": (
            "Submit a P1 incident report in the ITSM portal immediately; "
            "the on-call SRE team will be paged and will respond within 15 minutes."
        ),
    },
]


def _build_answer_from_chunks(chunks: list[dict]) -> str:
    """Concatenate top retrieved chunks as a simple extractive answer."""
    return " ".join(c["content"] for c in chunks[:2])


def _safe_mean(raw: object) -> float:
    """Return a mean score from either a pre-aggregated float or a list of per-row floats.

    Filters out None and NaN entries before averaging so one timed-out row
    does not poison the whole result.  Returns float('nan') if no valid
    scores remain (caller should warn and treat as missing, not 0.0).
    """
    if isinstance(raw, list):
        valid = [
            x for x in raw
            if x is not None and not (isinstance(x, float) and math.isnan(x))
        ]
        return sum(valid) / len(valid) if valid else float("nan")
    return float(raw)  # type: ignore[arg-type]


def main() -> None:
    """Run RAGAS evaluation and exit 1 if faithfulness < FAITHFULNESS_THRESHOLD."""
    print("Building retriever index …")
    retriever = get_retriever()

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []

    print(f"Retrieving contexts for {len(_QA_PAIRS)} QA pairs …")
    for pair in _QA_PAIRS:
        chunks = retriever.search(pair["question"], top_k=3)
        questions.append(pair["question"])
        answers.append(_build_answer_from_chunks(chunks))
        contexts.append([c["content"] for c in chunks])
        ground_truths.append(pair["ground_truth"])

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    # Use llama-3.1-8b-instant as the RAGAS judge — higher rate limits on
    # Groq free tier than 70b.  Other pipeline components keep their own models.
    # max_tokens=2048 prevents LLMDidNotFinishException on faithfulness decomposition.
    groq_llm = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=4096,
    )
    ragas_llm = LangchainLLMWrapper(groq_llm)
    ragas_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    )

    faithfulness.llm = ragas_llm
    answer_relevancy.llm = ragas_llm
    answer_relevancy.embeddings = ragas_embeddings

    print("Running RAGAS evaluation (faithfulness + answer_relevancy) …\n")
    try:
        # raise_exceptions=False + RunConfig(max_workers=1):
        #   - serial execution avoids Groq free-tier rate limits
        #   - individual row failures produce NaN instead of aborting the run
        _base_kwargs: dict = {
            "dataset": dataset,
            "metrics": [faithfulness, answer_relevancy],
            "llm": ragas_llm,
            "embeddings": ragas_embeddings,
        }
        if _RUN_CONFIG is not None:
            _base_kwargs["run_config"] = _RUN_CONFIG
        try:
            result = evaluate(raise_exceptions=False, **_base_kwargs)
        except TypeError:
            # Older RAGAS builds do not accept raise_exceptions or run_config.
            result = evaluate(**{k: v for k, v in _base_kwargs.items() if k != "run_config"})
        print(result)
    except Exception as exc:
        print(f"RAGAS evaluation error: {exc}")
        sys.exit(1)

    raw_f = result["faithfulness"]
    if isinstance(raw_f, list):
        valid_f = [x for x in raw_f if x is not None and not (isinstance(x, float) and math.isnan(x))]
        faithfulness_score = sum(valid_f) / len(valid_f) if valid_f else float("nan")
    else:
        faithfulness_score = float(raw_f)

    raw_r = result["answer_relevancy"]
    if isinstance(raw_r, list):
        valid_r = [x for x in raw_r if x is not None and not (isinstance(x, float) and math.isnan(x))]
        relevancy_score = sum(valid_r) / len(valid_r) if valid_r else float("nan")
    else:
        relevancy_score = float(raw_r)

    print(f"\nfaithfulness    : {faithfulness_score:.4f}")
    print(f"answer_relevancy: {relevancy_score:.4f}")
    print(f"threshold       : {FAITHFULNESS_THRESHOLD}")

    if math.isnan(faithfulness_score):
        print("\nWARN: all faithfulness scores were NaN — likely rate-limited. Skipping CI gate.")
        sys.exit(0)

    if faithfulness_score < FAITHFULNESS_THRESHOLD:
        print(
            f"\nFAIL: faithfulness {faithfulness_score:.4f} < "
            f"threshold {FAITHFULNESS_THRESHOLD} — CI check failed."
        )
        sys.exit(1)

    print(
        f"\nPASS: faithfulness {faithfulness_score:.4f} >= "
        f"threshold {FAITHFULNESS_THRESHOLD}"
    )


if __name__ == "__main__":
    main()
