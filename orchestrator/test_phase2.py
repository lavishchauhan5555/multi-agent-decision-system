# Updated `test_phase2.py`


"""
test_phase2.py
──────────────
Compatibility test suite for your LangGraph backend.

Usage:
    python test_phase2.py

Tests:
  1. Imports resolve correctly
  2. AgentState contains required fields
  3. Graph compiles correctly
  4. Nodes execute with valid state
  5. Routing logic works
"""

import asyncio
import sys

from graph.init import init_agent


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Imports
# ─────────────────────────────────────────────────────────────────────────────

def test_imports():
    print("── Test 1: imports ──")

    try:
        from graph.state import AgentState
        from graph.edges import route_after_cache_check, route_debate_loop
        from graph.nodes import (
            cache_check_node,
            research_node,
            finance_node,
            competitor_node,
            critic_node,
            heartbeat_node,
            ceo_node,
            meta_eval_node,
        )
        from graph.builder import build_graph

        print("   PASS — all imports resolved")
        return True

    except Exception as e:
        print(f"   FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — AgentState fields
# ─────────────────────────────────────────────────────────────────────────────

def test_state_fields():
    print("── Test 2: AgentState fields ──")

    from graph.state import AgentState

    required = [
        "query",
        "session_id",
        "round",
        "max_rounds",
        "confidence_score",
        "confidence_threshold",
        "evals_since_improvement",
        "best_score",
        "research_output",
        "finance_output",
        "competitor_output",
        "critiques",
        "debate_transcript",
        "final_decision",
        "reasoning_summary",
        "coral_notes",
        "coral_attempts",
        "coral_skills",
        "heartbeat_action",
        "heartbeat_prompts",
        "cached_result",
        "cache_score",
    ]

    keys = list(AgentState.__annotations__.keys())

    missing = [field for field in required if field not in keys]

    if missing:
        print(f"   FAIL — missing fields: {missing}")
        return False

    print(f"   PASS — {len(required)} fields verified")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Graph compile
# ─────────────────────────────────────────────────────────────────────────────

def test_graph_compiles():
    print("── Test 3: graph compiles ──")

    try:
        from graph.builder import build_graph

        graph = build_graph()

        print("   PASS — graph compiled successfully")
        return True

    except Exception as e:
        print(f"   FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Nodes execution
# ─────────────────────────────────────────────────────────────────────────────

async def test_nodes_async():
    print("── Test 4: node execution ──")

    from graph.nodes import (
        cache_check_node,
        research_node,
        finance_node,
        competitor_node,
        critic_node,
        meta_eval_node,
    )

    base_state = {
        "query": "Should I build an AI resume SaaS startup?",
        "session_id": "test-session-001",
        "round": 0,
        "max_rounds": 3,
        "confidence_score": 0.0,
        "confidence_threshold": 0.85,
        "evals_since_improvement": 0,
        "best_score": 0.0,
        "research_output": "",
        "finance_output": "",
        "competitor_output": "",
        "critiques": [],
        "debate_transcript": [],
        "final_decision": "",
        "reasoning_summary": "",
        "coral_notes": [],
        "coral_attempts": [],
        "coral_skills": [],
        "heartbeat_action": "",
        "heartbeat_prompts": [],
        "cached_result": None,
        "cache_score": 0.0,
    }

    try:
        result = await cache_check_node(base_state)
        assert "cached_result" in result
        print("   PASS — cache_check_node")

        result = await research_node(base_state)
        assert "research_output" in result
        print("   PASS — research_node")

        result = await finance_node(base_state)
        assert "finance_output" in result
        print("   PASS — finance_node")

        result = await competitor_node(base_state)
        assert "competitor_output" in result
        print("   PASS — competitor_node")

        critic_state = {**base_state}
        critic_state["round"] = 1

        result = await critic_node(critic_state)
        assert "confidence_score" in result
        assert "critiques" in result
        print("   PASS — critic_node")

        result = await meta_eval_node(base_state)
        assert isinstance(result, dict)
        print("   PASS — meta_eval_node")

        return True

    except Exception as e:
        print(f"   FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — Routing logic
# ─────────────────────────────────────────────────────────────────────────────

def test_routing():
    print("── Test 5: routing logic ──")

    from graph.edges import route_after_cache_check, route_debate_loop

    try:
        cache_hit = route_after_cache_check({
            "cached_result": "existing answer"
        })

        assert cache_hit == "hit"

        cache_miss = route_after_cache_check({
            "cached_result": None
        })

        assert cache_miss == "miss"

        print("   PASS — cache routing")

        base = {
            "round": 0,
            "max_rounds": 3,
            "confidence_score": 0.5,
            "confidence_threshold": 0.85,
            "evals_since_improvement": 0,
            "heartbeat_action": "refine",
        }

        result = route_debate_loop(base)
        assert result in ["refine", "pivot", "exit"]

        print("   PASS — debate routing")

        return True

    except Exception as e:
        print(f"   FAIL — {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def run_all():
    print("\n════════════════════════════════════════════")
    print(" LangGraph Backend Compatibility Test Suite")
    print("════════════════════════════════════════════")

    print("\n── Initializing runtime ──")

    try:
        await init_agent()
        print("   PASS — runtime initialized")
    except Exception as e:
        print(f"   WARNING — runtime init failed: {e}")

    results = []

    results.append(test_imports())
    results.append(test_state_fields())
    results.append(test_graph_compiles())
    results.append(await test_nodes_async())
    results.append(test_routing())

    passed = sum(results)
    total = len(results)

    print("\n── Summary ──")
    print(f"   {passed}/{total} tests passed")

    if passed == total:
        print("\n   Backend graph is ready.")
        print("   Start server using:")
        print("   uvicorn main:app --reload --port 8000\n")
    else:
        print("\n   Fix failures before running backend.\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())

