"""Markdown document loader — reads rag/data/ and splits into paragraph chunks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

DATA_DIR: Path = Path(__file__).parent / "data"
_MIN_CHUNK_CHARS: int = 60


class Document(TypedDict):
    """One knowledge-base chunk ready for indexing."""

    source: str
    content: str


def load_documents(data_dir: Path = DATA_DIR) -> list[Document]:
    """Read every .md file under data_dir and split into paragraph-level chunks.

    Markdown heading markers are stripped from the beginning of lines so that
    section titles become plain text — keeping them in the chunk improves BM25
    keyword matching without polluting the embedding signal with hash characters.

    Args:
        data_dir: Directory containing markdown knowledge-base files.

    Returns:
        Flat list of Document dicts (source, content) with chunks of at least
        _MIN_CHUNK_CHARS characters.  Files are processed in sorted order so the
        index is deterministic across runs.
    """
    docs: list[Document] = []
    for path in sorted(data_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        # Strip leading `#` markers but keep the heading text.
        text = re.sub(r"^#{1,6}\s+", "", raw, flags=re.MULTILINE)
        for para in text.split("\n\n"):
            cleaned = para.strip()
            if len(cleaned) >= _MIN_CHUNK_CHARS:
                docs.append({"source": path.name, "content": cleaned})
    return docs
