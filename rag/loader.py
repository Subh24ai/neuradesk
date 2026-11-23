"""Markdown document loader — reads rag/data/ and splits into paragraph chunks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

DATA_DIR: Path = Path(__file__).parent / "data"
_MIN_CHUNK_CHARS: int = 60
# Max passage size for org-uploaded documents. ~900 chars ≈ 225 tokens,
# comfortably inside the cross-encoder's 512-token window, so every passage of a
# long policy is fully scored (a whole document would be truncated after page 1).
_MAX_CHUNK_CHARS: int = 900

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    """Split one oversized paragraph on sentence boundaries (hard-split as a last resort)."""
    pieces: list[str] = []
    buf = ""
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > max_chars:  # a single run-on "sentence" (e.g. PDF text)
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if buf and len(buf) + 1 + len(sentence) > max_chars:
            pieces.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}" if buf else sentence
    if buf:
        pieces.append(buf)
    return pieces


def chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Split a document into retrieval-sized passages.

    One passage per paragraph (mirroring how the bundled corpus is chunked, which
    keeps each passage focused so the reranker scores it accurately). Fragments
    shorter than ``_MIN_CHUNK_CHARS`` — typically headings — are attached to the
    following paragraph; paragraphs longer than ``max_chars`` (e.g. PDF pages with
    no blank lines) are split on sentence boundaries. Used for org-uploaded
    documents (PDF, DOCX, TXT, MD), which can be arbitrarily long.

    Args:
        text: Full document text.
        max_chars: Maximum characters per passage.

    Returns:
        Ordered list of passages covering the whole document.
    """
    clean = text.replace("\r\n", "\n").strip()
    if not clean:
        return []
    pieces: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n", clean)):
        if para:
            pieces.extend([para] if len(para) <= max_chars else _split_long(para, max_chars))

    chunks: list[str] = []
    carry = ""
    for piece in pieces:
        piece = f"{carry}\n\n{piece}" if carry else piece
        if len(piece) < _MIN_CHUNK_CHARS:
            carry = piece  # heading / fragment — prepend to the next paragraph
            continue
        carry = ""
        chunks.append(piece)
    if carry:  # trailing fragment
        if chunks:
            chunks[-1] = f"{chunks[-1]}\n\n{carry}"
        else:
            chunks.append(carry)
    return chunks


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
