# graph/state.py
from typing import Annotated, Optional ,TypedDict
from langgraph.graph.message import add_messages
from operator import add


def _append_list(existing: list, new: list) -> list:
    """Reducer: always appends new items to existing list."""
    if existing is None:
        existing = []
    if new is None:
        return existing
    return existing + new


class AgentState(TypedDict, total=False):
    # ── Identity ──────────────────────────────────────────────────────────
    query:                   str
    session_id:              str
    round:                   int
    max_rounds:              int

    # ── Scoring ───────────────────────────────────────────────────────────
    confidence_score:        float
    confidence_threshold:    float
    evals_since_improvement: int
    best_score:              float

    # ── Agent outputs ─────────────────────────────────────────────────────
    research_output:         str
    finance_output:          str
    competitor_output:       str
    final_decision:          str
    reasoning_summary:       str

    # ── Lists with append reducers — safe for concurrent node writes ───────
    competitors_list:        Annotated[list, _append_list]
    critiques:               Annotated[list, _append_list]
    debate_transcript:       Annotated[list, _append_list]  # ← THIS fixes the crash
    coral_notes:             Annotated[list, _append_list]
    coral_attempts:          Annotated[list, _append_list]
    coral_skills:            Annotated[list, _append_list]
    heartbeat_prompts:       Annotated[list, _append_list]

    # ── Control ───────────────────────────────────────────────────────────
    heartbeat_action:        str

    # ── Cache ─────────────────────────────────────────────────────────────
    cached_result:           Optional[str]
    cache_score:             float