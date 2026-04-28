"""
memory/vector_store.py
──────────────────────
LlamaIndex vector store backed by ChromaDB with local HuggingFace embeddings.
No OpenAI key needed — runs 100% locally.

Model: sentence-transformers/all-MiniLM-L6-v2
Install:
    pip install llama-index
    pip install llama-index-vector-stores-chroma
    pip install llama-index-embeddings-huggingface
    pip install chromadb sentence-transformers

Phase 2: if packages not installed, all functions return safe fallbacks.
"""

from pathlib import Path
from typing import Optional
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()
# NEW import
from llama_index.embeddings.gemini import GeminiEmbedding

# Dummy API key (replace later)
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL   = "models/gemini-embedding-001"

CHROMA_PATH     = Path(".chroma")
COLLECTION_NAME = "decision_lab"
EMBED_MODEL  = "models/gemini-embedding-001"


_client = None
_index  = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    import chromadb
    CHROMA_PATH.mkdir(exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return _client


def get_index():
    """
    Return VectorStoreIndex backed by ChromaDB + HuggingFace embeddings.
    Returns None if packages not installed (Phase 2 safe).
    Matches user's exact implementation.
    """
    global _index
    if _index is not None:
        return _index

    try:
        from llama_index.core import VectorStoreIndex, StorageContext
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.embeddings.gemini import GeminiEmbedding
      
    except ImportError as e:
        print(
            f"[vector_store] Not installed — Phase 2 mode (no RAG). "
            f"pip install llama-index llama-index-vector-stores-chroma "
            f"llama-index-embeddings-huggingface chromadb sentence-transformers"
        )
        return None

    try:
        client     = _get_client()
        collection = client.get_or_create_collection(COLLECTION_NAME)

        vector_store = ChromaVectorStore(chroma_collection=collection)

        embed_model = GeminiEmbedding(
             model_name=GEMINI_MODEL,
            api_key=GEMINI_API_KEY
            )

                            


        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        _index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context,
            embed_model=embed_model,
        )

        print(f"[vector_store] Ready — collection='{COLLECTION_NAME}' model='{EMBED_MODEL}'")
        return _index

    except Exception as exc:
        print(f"[vector_store] Init failed: {exc}")
        return None


def search(query: str, top_k: int = 5) -> list:
    """
    Semantic search. Returns [] if index unavailable (Phase 2 safe).

    Returns list of dicts: [{"text": str, "score": float, "metadata": dict}]
    """
    index = get_index()
    if index is None:
        return []
    try:
        retriever = index.as_retriever(similarity_top_k=top_k)
        nodes     = retriever.retrieve(query)
        return [
            {
                "text":     node.text,
                "score":    round(node.score or 0.0, 4),
                "metadata": node.metadata or {},
            }
            for node in nodes
        ]
    except Exception as exc:
        print(f"[vector_store] Search error: {exc}")
        return []


def add_documents(documents: list) -> bool:
    """
    Add llama_index Document objects to the vector store.
    Returns True on success, False on failure.

    Example:
        from llama_index.core import Document
        add_documents([Document(text="Market data: AI SaaS $4.2B growing 23%")])
    """
    global _index
    if not documents:
        return True
    try:
        from llama_index.core import VectorStoreIndex, StorageContext
        from llama_index.vector_stores.chroma import ChromaVectorStore
        from llama_index.embeddings.gemini import GeminiEmbedding
       

        client       = _get_client()
        collection   = client.get_or_create_collection(COLLECTION_NAME)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        embed_model = GeminiEmbedding(
            model_name=GEMINI_MODEL,
            api_key=GEMINI_API_KEY
            )

    

        storage_ctx  = StorageContext.from_defaults(vector_store=vector_store)

        _index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_ctx,
            embed_model=embed_model,
        )
        print(f"[vector_store] Added {len(documents)} document(s)")
        return True

    except Exception as exc:
        print(f"[vector_store] add_documents error: {exc}")
        return False


def add_text(text: str, metadata: Optional[dict] = None) -> bool:
    try:
        from llama_index.core import Document

        meta = metadata or {}
        meta["created_at"] = datetime.now(timezone.utc).isoformat()

        return add_documents([Document(text=text, metadata=meta)])
    except ImportError:
        return False


def is_available() -> bool:
    """True if all required packages are installed."""
    try:
        from llama_index.core import VectorStoreIndex            # noqa
        from llama_index.vector_stores.chroma import ChromaVectorStore  # noqa
        from llama_index.embeddings.gemini import GeminiEmbedding
        import chromadb                                           # noqa
        return True
    except ImportError:
        return False


def collection_count() -> int:
    """Number of documents stored in ChromaDB collection."""
    try:
        return _get_client().get_or_create_collection(COLLECTION_NAME).count()
    except Exception:
        return 0


def reset_index() -> bool:
    """Delete and recreate the collection. WARNING: wipes all embeddings."""
    global _index
    try:
        _get_client().delete_collection(COLLECTION_NAME)
        _index = None
        print(f"[vector_store] Collection '{COLLECTION_NAME}' reset")
        return True
    except Exception as exc:
        print(f"[vector_store] reset error: {exc}")
        return False
    
# cleanup function

def cleanup_old_documents(days: int = 15) -> int:
    """
    Delete ChromaDB documents older than N days.
    Returns number of deleted docs.
    """
    try:
        collection = _get_client().get_or_create_collection(COLLECTION_NAME)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        data = collection.get(
            include=["metadatas"]
        )

        ids_to_delete = []

        for doc_id, meta in zip(data["ids"], data["metadatas"]):
            created_at = meta.get("created_at") if meta else None

            if not created_at:
                continue  # don't delete old docs without date automatically

            try:
                created_time = datetime.fromisoformat(created_at)
                if created_time < cutoff:
                    ids_to_delete.append(doc_id)
            except Exception:
                continue

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)

        print(f"[vector_store] Cleaned {len(ids_to_delete)} old documents")
        return len(ids_to_delete)

    except Exception as exc:
        print(f"[vector_store] cleanup error: {exc}")
        return 0    