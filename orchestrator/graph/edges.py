"""
graph/edges.py
──────────────
Conditional routing functions for LangGraph.
Each function receives the current AgentState and returns a string
that LangGraph uses to pick the next node.
"""

from graph.state import AgentState


def route_after_cache_check(state: AgentState) -> str:
    """
    After cache_check node runs:
    - If a cached result exists  → jump straight to END (skip all agents)
    - Otherwise                  → proceed to parallel agent dispatch
    """
    if state.get("cached_result"): 
        return "hit"
    return "miss"


def route_debate_loop(state: AgentState) -> str:
    return state.get("heartbeat_action", "refine")


def route_after_meta_eval(state: AgentState) -> str:
    """
    After meta_eval node (post-CEO):
    Always ends — meta agent runs asynchronously after the decision is delivered.
    """
    return "done"