from langgraph.graph import StateGraph, END

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


def build_graph():
    g = StateGraph(AgentState)

    # Nodes
    g.add_node("cache_check", cache_check_node)
    g.add_node("research", research_node)
    g.add_node("finance", finance_node)
    g.add_node("competitor", competitor_node)
    g.add_node("critic", critic_node)
    g.add_node("heartbeat", heartbeat_node)
    g.add_node("ceo", ceo_node)
    g.add_node("meta_eval", meta_eval_node)

    # Entry
    g.set_entry_point("cache_check")

    # Cache routing → single entry point
    g.add_conditional_edges(
        "cache_check",
        route_after_cache_check,
        {
            "hit": END,
            "miss": "fanout",
        },
    )

    # 🔥 Proper fan-out node (IMPORTANT)
    g.add_node("fanout", lambda state: state)

    g.add_edge("fanout", "research")
    g.add_edge("fanout", "finance")
    g.add_edge("fanout", "competitor")

    # Fan-in
    g.add_edge("research", "critic")
    g.add_edge("finance", "critic")
    g.add_edge("competitor", "critic")

    # Critic → heartbeat
    g.add_edge("critic", "heartbeat")

    # Loop routing
    g.add_conditional_edges(
        "heartbeat",
        route_debate_loop,
        {
            "refine": "fanout",
            "pivot": "fanout",
            "exit": "ceo",
        },
    )

    # Final
    g.add_edge("ceo", "meta_eval")
    g.add_edge("meta_eval", END)

    return g.compile()


graph = build_graph()