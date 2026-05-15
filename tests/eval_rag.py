"""RAGAS evaluation script for the NeuraDesk RAG pipeline.

Run with:
    python tests/eval_rag.py

Requires GROQ_API_KEY in .env (used as the LLM judge via LangChain).
Prints faithfulness and answer_relevancy scores for 5 representative QA pairs.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Validate GROQ_API_KEY before importing heavy dependencies.
if not os.getenv("GROQ_API_KEY"):
    print("ERROR: GROQ_API_KEY is not set. Add it to .env before running this script.")
    sys.exit(1)

try:
    from datasets import Dataset
    from langchain_groq import ChatGroq
    from ragas import evaluate
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, faithfulness
except ImportError as exc:
    print(f"Missing dependency: {exc}")
    print("Install with: pip install ragas datasets langchain-groq")
    sys.exit(1)

from rag.retriever import get_retriever

# ── QA pairs covering all 5 resolvable categories ────────────────────────────

_QA_PAIRS: list[dict[str, str]] = [
    {
        "question": "How do I reset my forgotten corporate password?",
        "ground_truth": "Navigate to the IT Self-Service Portal, select Reset Password, verify your identity, and a temporary password will be emailed to you.",
    },
    {
        "question": "How do I request access to a production system?",
        "ground_truth": "Submit an access request ticket in the ITSM portal with the resource name, required role, and business justification. Manager and resource owner approval is required.",
    },
    {
        "question": "What is the process for installing new software on my work laptop?",
        "ground_truth": "Submit a software installation request through the IT Self-Service Portal with the application name, version, and business justification. Approved requests are fulfilled within three business days.",
    },
    {
        "question": "How do I apply for annual leave?",
        "ground_truth": "Submit your leave request through the HR Self-Service Portal at least 5 business days in advance. Your manager must approve within 2 business days.",
    },
    {
        "question": "What are the severity levels for IT incidents?",
        "ground_truth": "P1 is critical (full outage, 15-minute response), P2 is high (major degradation, 1-hour response), P3 is medium (partial degradation, 4-hour response), P4 is low (minor issue, 1 business day response).",
    },
]


def _build_answer_from_chunks(chunks: list[dict]) -> str:
    """Concatenate top retrieved chunks as a simple extractive answer."""
    return " ".join(c["content"] for c in chunks[:2])


def main() -> None:
    """Run RAGAS evaluation and print metric scores."""
    print("Building retriever index …")
    retriever = get_retriever()

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []

    print("Retrieving contexts for 5 QA pairs …")
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

    # Configure RAGAS to use Groq instead of OpenAI.
    groq_llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"),
        api_key=os.getenv("GROQ_API_KEY"),
    )
    ragas_llm = LangchainLLMWrapper(groq_llm)

    print("Running RAGAS evaluation (faithfulness + answer_relevancy) …\n")
    try:
        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy],
            llm=ragas_llm,
        )
        print(result)
    except Exception as exc:
        print(f"RAGAS evaluation error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
