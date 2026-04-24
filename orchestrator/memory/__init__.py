"""
memory/ — Vector store and long-term RAG memory
Uses ChromaDB + HuggingFace sentence-transformers (no API key needed)
"""
from memory.vector_store import (
    get_index,
    search,
    add_documents,
    add_text,
    is_available,
    collection_count,
    reset_index,
)

__all__ = [
    "get_index",
    "search",
    "add_documents",
    "add_text",
    "is_available",
    "collection_count",
    "reset_index",
]