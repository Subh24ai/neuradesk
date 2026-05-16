"""RAGAS evaluation script for the NeuraDesk RAG pipeline.

Run with:
    python tests/eval_rag.py

Requires GROQ_API_KEY in .env (used as the LLM judge via LangChain).
Evaluates faithfulness and answer_relevancy over 20 representative QA pairs
(4 per ticket category).  Exits with code 1 if faithfulness < 0.8 so CI fails.
"""

from __future__ import annotations

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

from rag.retriever import get_retriever

# ── 20 QA pairs — 4 per resolvable ticket category ───────────────────────────

_QA_PAIRS: list[dict[str, str]] = [
    # ── password_reset (4) ────────────────────────────────────────────────────
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
    {
        "question": "I'm locked out of my work account — how do I regain access?",
        "ground_truth": (
            "Visit the IT Self-Service Portal and select Unlock Account or Reset Password, "
            "verify your identity, and access will be restored."
        ),
    },
    {
        "question": "Where can I reset my SSO (single sign-on) password?",
        "ground_truth": (
            "Use the IT Self-Service Portal's Reset Password workflow to update "
            "your corporate SSO credentials."
        ),
    },
    # ── access_request (4) ────────────────────────────────────────────────────
    {
        "question": "How do I request access to a production system?",
        "ground_truth": (
            "Submit an access request ticket in the ITSM portal with the resource name, "
            "required role, and business justification. Manager and resource owner approval is required."
        ),
    },
    {
        "question": "What is the approval process for requesting elevated permissions?",
        "ground_truth": (
            "Submit an access request in the ITSM portal specifying the resource, "
            "role, and business justification; your manager and the resource owner must approve."
        ),
    },
    {
        "question": "How long does provisioning a new system access request take?",
        "ground_truth": (
            "Access provisioning takes up to two business days after both manager "
            "and resource owner have approved the ITSM ticket."
        ),
    },
    {
        "question": "I need read access to the data warehouse — how do I request it?",
        "ground_truth": (
            "Open an access request in the ITSM portal, specify 'data-warehouse' as the resource "
            "and 'reader' as the role, include a business justification, "
            "and submit for manager and resource owner approval."
        ),
    },
    # ── software_install (4) ─────────────────────────────────────────────────
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
    {
        "question": "Can I install open-source tools on my work laptop without IT approval?",
        "ground_truth": (
            "No — all software installations on corporate machines require an approved "
            "IT Self-Service Portal request, regardless of whether the tool is open-source."
        ),
    },
    {
        "question": "How many business days does it take to process a software install request?",
        "ground_truth": (
            "Approved software installation requests are fulfilled within three business days."
        ),
    },
    # ── leave_approval (4) ────────────────────────────────────────────────────
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
    {
        "question": "How does my manager approve my leave request?",
        "ground_truth": (
            "After you submit a leave request in the HR Self-Service Portal, "
            "your manager receives an email notification and must approve or reject "
            "within 2 business days."
        ),
    },
    {
        "question": "What happens if my leave request is not approved in time?",
        "ground_truth": (
            "If your manager does not respond within 2 business days, "
            "the HR Self-Service Portal escalates the request to the HR business partner."
        ),
    },
    # ── incident_report (4) ───────────────────────────────────────────────────
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
    {
        "question": "What is the response time for a P2 incident?",
        "ground_truth": (
            "P2 incidents (major service degradation) have a 1-hour response time "
            "from the tier-2 support team."
        ),
    },
    {
        "question": "How do I escalate an incident that has not been resolved within the SLA?",
        "ground_truth": (
            "If the incident SLA is breached, update the ITSM ticket with 'SLA Breach' "
            "in the subject and the system will auto-escalate to the tier-2 support group."
        ),
    },
]


def _build_answer_from_chunks(chunks: list[dict]) -> str:
    """Concatenate top retrieved chunks as a simple extractive answer."""
    return " ".join(c["content"] for c in chunks[:2])


def main() -> None:
    """Run RAGAS evaluation and exit 1 if faithfulness < FAITHFULNESS_THRESHOLD."""
    print(f"Building retriever index …")
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

    groq_llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        api_key=os.getenv("GROQ_API_KEY"),
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
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )
        print(result)
    except Exception as exc:
        print(f"RAGAS evaluation error: {exc}")
        sys.exit(1)

    faithfulness_score: float = float(result["faithfulness"])
    relevancy_score: float = float(result["answer_relevancy"])

    print(f"\nfaithfulness    : {faithfulness_score:.4f}")
    print(f"answer_relevancy: {relevancy_score:.4f}")
    print(f"threshold       : {FAITHFULNESS_THRESHOLD}")

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
