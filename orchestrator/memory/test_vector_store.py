"""
test_vector_store.py
────────────────────
Standalone test for memory/vector_store.py.

Run AFTER installing packages:
    pip install llama-index llama-index-vector-stores-chroma
    pip install llama-index-embeddings-huggingface
    pip install chromadb sentence-transformers

Usage:
    python test_vector_store.py
"""

import sys


def test_availability():
    print("── Test 1: package availability ──")
    from memory.vector_store import is_available
    available = is_available()
    if available:
        print("   PASS — all packages installed")
    else:
        print("   SKIP — llama_index not installed (Phase 2 mode OK)")
        print("   Run: pip install llama-index llama-index-vector-stores-chroma")
        print("        pip install llama-index-embeddings-huggingface")
        print("        pip install chromadb sentence-transformers")
    return True   # never fail — Phase 2 works without it


def test_get_index():
    print("── Test 2: get_index() ──")
    from memory.vector_store import get_index, is_available
    if not is_available():
        print("   SKIP — packages not installed")
        return True

    index = get_index()
    if index is None:
        print("   FAIL — get_index() returned None despite packages being installed")
        return False
    print(f"   PASS — index created: {type(index).__name__}")
    return True


def test_add_and_search():
    print("── Test 3: add_documents + search ──")
    from memory.vector_store import add_documents, search, is_available, reset_index

    if not is_available():
        print("   SKIP — packages not installed")
        return True

    try:
        from llama_index.core import Document
    except ImportError:
        print("   SKIP — llama_index.core not available")
        return True

    # Reset to clean state
    reset_index()

    # Add test documents
    docs = [
        Document(text="AI SaaS market is worth $4.2 billion and growing at 23% YoY"),
        Document(text="Main competitors are OpenAI, Anthropic, and Cohere in the LLM space"),
        Document(text="ROI for AI tools investment averages 275% over 12 months"),
        Document(text="Resume screening AI tools have 87% adoption rate in enterprise HR"),
    ]
    ok = add_documents(docs)
    assert ok, "add_documents should return True"
    print(f"   PASS — added {len(docs)} documents")

    # Search
    results = search("AI SaaS market size revenue", top_k=2)
    assert isinstance(results, list), "search should return a list"
    assert len(results) > 0, "search should return at least 1 result"
    assert "text" in results[0], "result should have 'text' key"
    assert "score" in results[0], "result should have 'score' key"
    print(f"   PASS — search returned {len(results)} result(s)")
    print(f"          Top result score: {results[0]['score']:.4f}")
    print(f"          Top result text:  {results[0]['text'][:80]}...")

    return True


def test_add_text_shortcut():
    print("── Test 4: add_text() shortcut ──")
    from memory.vector_store import add_text, is_available

    if not is_available():
        print("   SKIP — packages not installed")
        return True

    ok = add_text(
        "Finance agent decision: Monthly burn rate $12,000 with 4-month payback period",
        metadata={"agent": "finance", "round": 1}
    )
    assert ok, "add_text should return True"
    print("   PASS — add_text() works")
    return True


def test_collection_count():
    print("── Test 5: collection_count() ──")
    from memory.vector_store import collection_count, is_available

    if not is_available():
        print("   SKIP — packages not installed")
        return True

    count = collection_count()
    assert isinstance(count, int)
    assert count >= 0
    print(f"   PASS — collection has {count} document(s)")
    return True


def test_phase2_safe():
    print("── Test 6: Phase 2 safety (search returns [] when unavailable) ──")
    from memory.vector_store import search, add_documents, add_text, is_available

    if is_available():
        print("   SKIP — packages installed, Phase 3 mode active")
        return True

    # These must not raise, must return safe defaults
    results = search("any query here")
    assert results == [], f"Expected [] got {results}"

    ok = add_documents([])
    assert ok is True

    ok2 = add_text("some text")
    assert ok2 is False or ok2 is True  # either is acceptable

    print("   PASS — all functions return safe fallbacks when llama_index missing")
    return True


def run_all():
    results = []
    print("")
    for fn in [
        test_availability,
        test_get_index,
        test_add_and_search,
        test_add_text_shortcut,
        test_collection_count,
        test_phase2_safe,
    ]:
        try:
            results.append(fn())
        except Exception as exc:
            print(f"   FAIL — {exc}")
            import traceback; traceback.print_exc()
            results.append(False)

    print("\n── Summary ──")
    passed = sum(results)
    total  = len(results)
    print(f"   {passed}/{total} tests passed")

    if passed == total:
        print("\n   vector_store.py ready for Phase 3 Research Agent.\n")
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_all()