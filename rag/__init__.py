"""RAG package — hybrid FAISS + BM25 retrieval with cross-encoder reranking."""

from rag.loader import Document, load_documents
from rag.retriever import HybridRetriever, get_retriever

__all__ = ["Document", "HybridRetriever", "get_retriever", "load_documents"]
