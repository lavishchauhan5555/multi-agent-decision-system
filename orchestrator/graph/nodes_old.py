"""
graph/nodes.py
──────────────
Production-ready LangGraph node functions.

All 8 nodes follow the same signature:
    async def node_name(state: AgentState) -> dict

The returned dict is MERGED into AgentState.

LLM call budget per node (strictly enforced):
    - LLM call 1  : prompt → optional tool call
    - Tool call    : at most 1
    - LLM call 2  : tool result → final JSON text
    - Pydantic     : json.loads() + model_validate() — NO extra LLM call
    Total          : exactly 2 LLM calls, at most 1 tool call

Inter-node data contract:
    Every node receives clean text strings from state and returns clean
    text strings. No dicts, no nested objects cross node boundaries.
    All structured parsing is local to each node.

LLM routing:
    Research   → hf      (Gemini)
    Finance    → hf      (Gemini)
    Competitor → hf      (Gemini)
    Critic     → gemini  (Gemini)
    CEO        → gemini  (Gemini) with grok fallback
"""

import asyncio
import json
import re
import time
from typing import Any

from graph.state import AgentState
from graph.structured_outputs import (
    ResearchOutput,
    FinanceOutput,
    CompetitorOutput,
    CriticOutput,
    CEOOutput,
    structured_to_markdown,
)





def unwrap_ai_text(raw: Any) -> str:
    if raw is None:
        return ""

    if isinstance(raw, str):
        return raw

    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(item["text"])
                elif item.get("content"):
                    parts.append(str(item["content"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    if isinstance(raw, dict):
        if raw.get("text"):
            return raw["text"]
        if raw.get("content"):
            return str(raw["content"])
        return json.dumps(raw)

    return str(raw)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_content(response) -> str:
    """Extract a plain string from any LangChain response object."""
    if response is None:
        return "[ERROR] LLM returned None"

    from pydantic import BaseModel as PydanticBase
    if isinstance(response, PydanticBase):
        return structured_to_markdown(response)

    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, list):
            parts = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            ]
            return "\n".join(p for p in parts if p).strip()
        return content or ""

    return str(response)


def _parse_json_response(raw: str, model_class):
    """
    Robustly extract ONE JSON object from LLM output.
 
    Handles:
      - Clean JSON                          → parsed directly
      - Markdown fences  ```json ... ```    → stripped then parsed
      - Prose before/after JSON             → regex extracts first { ... }
      - Multiple JSON blocks                → takes the LARGEST one (most complete)
      - Nested braces                       → brace-counting to find correct end
 
    Returns (obj, None) on success or (None, error_string) on failure.
    No LLM call is made here.
    """
    if not raw or not isinstance(raw, str):
        return None, "Empty or non-string input"
 
    # Step 1: strip markdown fences
    clean = re.sub(r"```(?:json)?\s*", "", raw.strip())
    clean = re.sub(r"```", "", clean).strip()
 
    # Step 2: extract ALL top-level JSON objects using brace counting
    candidates = []
    i = 0
    while i < len(clean):
        if clean[i] == '{':
            depth = 0
            start = i
            for j in range(i, len(clean)):
                if clean[j] == '{':
                    depth += 1
                elif clean[j] == '}':
                    depth -= 1
                    if depth == 0:
                        candidates.append(clean[start:j + 1])
                        i = j + 1
                        break
            else:
                break
        else:
            i += 1
 
    if not candidates:
        return None, f"No JSON object found in response: {clean[:120]}"
 
    # Step 3: take the largest candidate (most likely the complete schema object)
    candidates.sort(key=len, reverse=True)
 
    last_err = None
    for candidate in candidates:
        try:
            obj = model_class.model_validate(json.loads(candidate))
            return obj, None
        except Exception as exc:
            last_err = str(exc)
            continue
 
    return None, f"All JSON candidates failed validation. Last error: {last_err}"
 

def _schema_hint(model_class) -> str:
    """
    Build a compact JSON schema hint from a Pydantic model's field definitions.
    Used in system prompts so the LLM knows exactly what shape to return.
    """
    return "\n".join(
        f'  "{name}": {field.annotation}'
        for name, field in model_class.model_fields.items()
    )


async def rag_retrieve(query: str) -> list[str]:
    """LlamaIndex semantic retrieval — async-safe. Returns list of text strings."""
    try:
        from memory.vector_store import get_index
        index = get_index()
        if index is None:
            return []
        retriever = index.as_retriever(similarity_top_k=3)
        results = await asyncio.to_thread(retriever.retrieve, query)
        docs = []
        for r in results:
            text = getattr(r, "text", None)
            if not text and hasattr(r, "node"):
                text = r.node.get_content()
            if text:
                docs.append(text.strip())
        return docs
    except Exception as exc:
        print(f"[rag_retrieve] Error: {exc}")
        return []


def _get_runtime():
    """Lazy import of RUNTIME — never crashes at module load time."""
    try:
        from graph.runtime import RUNTIME
        return RUNTIME
    except ImportError:
        print("[RUNTIME] graph/runtime.py not found — LLM calls will be stubbed")
        return None


async def _llm_invoke_with_tools(llm, tools: list, messages: list) -> str:
    """
    Strictly enforced single-tool-round helper.
 
    Contract:
      - At most 2 LLM calls total
      - At most 1 tool call total — first tool_call only, rest discarded
      - If tool call errors → error message appended, second LLM call still runs
      - If LLM call times out → returns error string, never hangs
 
    No loops, no recursion, no exceptions bubble up.
    """
    from langchain_core.messages import ToolMessage
 
    MAX_TOOL_OUTPUT_CHARS = 8000
    LLM_TIMEOUT_SECONDS   = 60
 
    if llm is None:
        return "[STUB] LLM not configured — install dependencies and set API keys"
 
    if not messages or not isinstance(messages, list):
        return "[ERROR] Invalid messages passed to _llm_invoke_with_tools"
 
    # Build tool map — only tools with a valid name
    safe_tools = [t for t in (tools or []) if getattr(t, "name", None)]
    tool_map: dict[str, object] = {t.name: t for t in safe_tools}
 
    def _truncate(value: object) -> str:
        text = str(value)
        if len(text) <= MAX_TOOL_OUTPUT_CHARS:
            return text
        extra = len(text) - MAX_TOOL_OUTPUT_CHARS
        return text[:MAX_TOOL_OUTPUT_CHARS] + f"\n...[TRUNCATED {extra} CHARS]..."
 
    async def _invoke_tool(tool_fn, tool_args: dict) -> str:
        """Run a single tool call, async-safe, with error handling."""
        try:
            ainvoke = getattr(tool_fn, "ainvoke", None)
            invoke  = getattr(tool_fn, "invoke",  None)
            if callable(ainvoke):
                raw = await asyncio.wait_for(ainvoke(tool_args), timeout=30)
            elif callable(invoke):
                raw = await asyncio.wait_for(
                    asyncio.to_thread(invoke, tool_args), timeout=30
                )
            else:
                return f"[ERROR] Tool has no invoke method"
            return _truncate(raw)
        except asyncio.TimeoutError:
            return f"[ERROR] Tool timed out after 30s"
        except Exception as exc:
            return f"[ERROR] Tool raised: {exc}"
 
    async def _llm_call(msgs: list) -> object:
        """Single LLM call with timeout."""
        return await asyncio.wait_for(llm.ainvoke(msgs), timeout=LLM_TIMEOUT_SECONDS)
 
    def _safe_content(response) -> str:
     if response is None:
        return "[ERROR] LLM returned None"

     content = getattr(response, "content", None)

    # Case 1: normal string
     if isinstance(content, str):
        if content.strip():
            return content.strip()

    # Case 2: content blocks: [{"type": "text", "text": "..."}]
     if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("content"):
                    parts.append(str(block["content"]))
            else:
                parts.append(str(block))

        text = "\n".join(p for p in parts if p.strip()).strip()
        if text:
            return text

     # Case 3: final response still contains tool calls
     tool_calls = getattr(response, "tool_calls", None) or []
     if tool_calls:
        return json.dumps(tool_calls, default=str)

     # Case 4: fallback to full response
     return str(response)
 
    try:
        # ── LLM Call 1 ───────────────────────────────────────────────────────
        try:
            first_response = await _llm_call(messages)
        except asyncio.TimeoutError:
            return f"[ERROR] LLM call 1 timed out after {LLM_TIMEOUT_SECONDS}s"
        except Exception as exc:
            return f"[ERROR] LLM call 1 failed: {exc}"
 
        # Check for tool calls
        tool_calls = getattr(first_response, "tool_calls", None) or []
        if not isinstance(tool_calls, list):
            tool_calls = []
 
        # No tool calls → return immediately, spend only 1 LLM call
        if not tool_calls:
            return _safe_content(first_response)
 
        # ── Execute ONLY the first tool call, discard the rest ───────────────
        tc = tool_calls[0]   # <-- strictly first only
 
        if len(tool_calls) > 1:
            print(f"[tool_loop] {len(tool_calls)} tool calls requested — "
                  f"executing only first: '{tc.get('name', '?')}', rest discarded")
 
        if not isinstance(tc, dict):
            return "[ERROR] Tool call is not a valid dict"
 
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
        tool_id   = tc.get("id") or tool_name or "tool_call_1"
 
        if not tool_name:
            return "[ERROR] Tool call missing name"
        if not isinstance(tool_args, dict):
            tool_args = {}
 
        tool_fn = tool_map.get(tool_name)
        print(f"[tool_loop] single tool selected='{tool_name}'")
 
        # Build follow-up message list
        followup = list(messages)
        followup.append(first_response)
 
        if tool_fn is None:
            tool_output = f"[ERROR] Tool '{tool_name}' not found."
            print(f"[tool_loop] {tool_output}")
        else:
            tool_output = await _invoke_tool(tool_fn, tool_args)
            print(f"[tool_loop] '{tool_name}' -> {tool_output[:160]}...")
 
        # Append tool result
        followup.append(
            ToolMessage(
               content=tool_output,
               tool_call_id=tool_id,
               name=tool_name,
            )
        )
 
        # ── LLM Call 2 (final) ────────────────────────────────────────────────
        try:
            final_response = await _llm_call(followup)
        except asyncio.TimeoutError:
            return f"[ERROR] LLM call 2 timed out after {LLM_TIMEOUT_SECONDS}s"
        except Exception as exc:
            return f"[ERROR] LLM call 2 failed: {exc}"
 
        return _safe_content(final_response)
 
    except Exception as exc:
        return f"[ERROR] Tool-loop failed unexpectedly: {exc}"
 
def _bind(base_llm, tools: list):
    """Bind tools to LLM only when tools is non-empty."""
    if base_llm and tools:
        return base_llm.bind_tools(tools)
    return base_llm


def _build_messages(system: str, human: str):
    """Construct [SystemMessage, HumanMessage] pair."""
    from langchain_core.messages import SystemMessage, HumanMessage
    return [SystemMessage(content=system), HumanMessage(content=human)]


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — Cache Check
# ─────────────────────────────────────────────────────────────────────────────

async def cache_check_node(state: AgentState) -> dict:
    """
    Semantic cache check via LlamaIndex vector store.
    No LLM call — pure vector similarity lookup.
    Threshold: cosine similarity > 0.92

    Output to state:
        cached_result : str | None   — clean text of the cached decision
        cache_score   : float
    """
    query = state["query"]
    print(f"[cache_check] query='{query[:60]}...'")

    try:
        from memory.vector_store import get_index
        index = get_index()

        if index is None:
            print("[cache_check] Vector store unavailable — CACHE MISS")
            return {"cached_result": None, "cache_score": 0.0}

        retriever = index.as_retriever(similarity_top_k=1)
        results   = await asyncio.to_thread(retriever.retrieve, query)

        if results:
            top   = results[0]
            score = getattr(top, "score", None) or 0.0
            print(f"[cache_check] top score={score:.4f}")

            if score > 0.92:
                print("[cache_check] CACHE HIT")
                return {
                    "cached_result": str(top.text),   # clean string only
                    "cache_score":   round(score, 4),
                }

    except Exception as exc:
        print(f"[cache_check] Error (non-fatal): {exc}")

    print("[cache_check] CACHE MISS")
    return {"cached_result": None, "cache_score": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Research Agent
# ─────────────────────────────────────────────────────────────────────────────

async def research_node(state: AgentState) -> dict:
    """
    CORAL + RAG + single-tool-round research agent.

    Call budget:
        LLM call 1  → prompt + optional tool selection
        Tool call   → at most 1 (search/crawl)
        LLM call 2  → produces final JSON text
        Pydantic    → local json.loads() + model_validate()
    Total: 2 LLM calls, ≤1 tool call, 0 extra extraction calls.

    Input from state  : query (str), coral_notes (list[str]), critiques (list[str])
    Output to state   : research_output (str), debate_transcript entry
    """
    print(
        f"[research] round={state['round']} "
        f"coral_notes={len(state.get('coral_notes', []))}"
    )

    query        = state["query"]
    coral_notes  = state.get("coral_notes", [])
    critiques    = state.get("critiques", [])

    coral_context    = "\n".join(coral_notes) if coral_notes else "No prior notes."
    critique_context = "\n".join(critiques[-2:]) if critiques else "First round — no critiques yet."

    docs        = await rag_retrieve(query)
    rag_context = "\n---\n".join(docs) if docs else "No external documents found."

    system = (
    "You are a senior research analyst in a multi-agent AI decision system.\n"
    "You MUST call exactly ONE search tool before producing the final JSON. "
    "Use duckduckgo_search or duckduckgo_results_json to gather current market data. "
    "to gather current market data, statistics, or news.\n\n"

    "CRITICAL RULES:\n"
    "1. Tool calls are NOT final answers.\n"
    "2. After tool result, you MUST produce final JSON.\n"
    "3. Final output MUST be a single JSON object.\n"
    "4. DO NOT return arrays like [{...}].\n"
    "5. DO NOT wrap output in {\"type\":\"text\"} or similar.\n"
    "6. DO NOT include markdown (no ```json).\n"
    "7. DO NOT include explanations outside JSON.\n\n"

    "FIELD RULES:\n"
    "- trends, key_players, opportunities, risks, critique_responses MUST be arrays of strings.\n"
    "- If no data → use ['data unavailable'] for lists.\n"
    "- market_size, growth_rate, raw_summary MUST be strings.\n\n"

    "FINAL ANSWER FORMAT (STRICT JSON):\n"
    "{\n"
    f"{_schema_hint(ResearchOutput)}\n"
    "}\n"
)

    human = f"""User Query:
{query}

Retrieved Knowledge (RAG):
{rag_context}

Prior Agent Notes (CORAL memory):
{coral_context}

Critiques to address from last round:
{critique_context}

Instructions:
- Include: market size, growth rate, trends, key players, opportunities, risks.
- Reference specific data points from RAG or tool results.
- Address every critique from the last round explicitly.
- Do NOT hallucinate — use "data unavailable" if needed.
- Return ONLY the JSON object described in the system prompt."""

    rt        = _get_runtime()
    tools     = getattr(rt, "tools", []) or []
    base_llm  = getattr(rt, "hf", None) if rt else None
    llm       = _bind(base_llm, tools)

    print(f"[research] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_output = await _llm_invoke_with_tools(llm, tools, _build_messages(system, human))
    raw_output = unwrap_ai_text(raw_output)

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    structured_output = raw_output
    obj, err = _parse_json_response(raw_output, ResearchOutput)
    if obj:
        structured_output = structured_to_markdown(obj)
        print("[research] structured extraction OK")
    else:
        print(f"[research] structured extraction failed (using raw): {err}")

    return {
        "research_output": structured_output,
        "debate_transcript": [{
            "agent":     "research",
            "round":     state["round"],
            "content":   structured_output,
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — Finance Agent
# ─────────────────────────────────────────────────────────────────────────────

async def finance_node(state: AgentState) -> dict:
    """
    Finance analysis agent.

    Call budget:
        LLM call 1  → prompt + optional pricing/benchmark tool call
        Tool call   → at most 1
        LLM call 2  → produces final JSON text
        Pydantic    → local json.loads() + model_validate()
    Total: 2 LLM calls, ≤1 tool call, 0 extra extraction calls.

    Input from state  : query (str), critiques (list[str]), coral_skills (list)
    Output to state   : finance_output (str), debate_transcript entry
    """
    print(f"[finance] round={state['round']}")

    query        = state["query"]
    critiques    = state.get("critiques", [])
    coral_skills = state.get("coral_skills", [])

    critique_context = "\n".join(critiques[-2:]) if critiques else "First round — no critiques yet."
    skills_context   = "\n".join(
        f"- {s.get('name', '')}: {s.get('content', '')[:200]}"
        for s in coral_skills[:3]
    ) if coral_skills else "No reusable skills available."

    system = (
    "You are a finance analyst in a multi-agent AI decision system.\n"
    "You MUST call exactly ONE calculator tool before producing the final JSON. "
    "Use calculator for ROI, total revenue, total cost, net profit, and payback calculations.\n\n"

    "CRITICAL RULES:\n"
    "1. Tool calls are NOT final answers.\n"
    "2. If you call a tool, wait for the tool result, then produce final JSON.\n"
    "3. Final response must be ONLY valid JSON.\n"
    "4. Do not return markdown.\n"
    "5. Do not return explanations outside JSON.\n"
    "6. monthly_projections must contain exactly 12 items.\n"
    "7. financial_risks must contain exactly 3 strings.\n"
    "8. recommendation must be one of: GO, NO-GO, CONDITIONAL GO.\n\n"

    "Use these exact assumptions unless tool results prove otherwise:\n"
    "- Initial Investment: 10000\n"
    "- Starting Monthly Revenue: 5000\n"
    "- Monthly Growth Rate: 0.15\n"
    "- Monthly Operating Cost: 12000\n\n"

    "Return JSON matching this schema:\n"
    "{\n"
    f"{_schema_hint(FinanceOutput)}\n"
    "}\n"
   )

    human = f"""Business Idea:
{query}

Available Reusable Skills (CORAL):
{skills_context}

Critiques to address from last round:
{critique_context}

Assumptions:
- Initial Investment: $10,000
- Starting Monthly Revenue: $5,000
- Monthly Growth Rate: 15%
- Monthly Operating Cost: $12,000

Task:
1. Calculate 12-month revenue projection (compound 15% monthly growth).
2. Calculate total revenue and total cost over 12 months.
3. Calculate net profit.
4. Calculate ROI = (net_profit / total_cost) × 100.
5. Calculate payback period in months (month when cumulative net turns positive).
6. Identify 3 key financial risks.
7. Provide GO / NO-GO / CONDITIONAL GO recommendation.

Return ONLY the JSON object described in the system prompt."""

    rt    = _get_runtime()
    tools = getattr(rt, "tools", []) or []
    base_llm  = getattr(rt, "hf", None) if rt else None
    llm       = _bind(base_llm, tools)

    print(f"[finance] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_output = await _llm_invoke_with_tools(llm, tools, _build_messages(system, human))

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    structured_output = raw_output
    obj, err = _parse_json_response(raw_output, FinanceOutput)
    if obj:
        structured_output = structured_to_markdown(obj)
        print(f"[finance] structured extraction OK — ROI={obj.roi_percent:.1f}% payback={obj.payback_months} months")
    else:
        print(f"[finance] structured extraction failed (using raw): {err}")

    return {
        "finance_output": structured_output,
        "debate_transcript": [{
            "agent":     "finance",
            "round":     state["round"],
            "content":   structured_output,
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — Competitor Agent
# ─────────────────────────────────────────────────────────────────────────────

async def competitor_node(state: AgentState) -> dict:
    """
    Competitor analysis agent.

    Call budget:
        LLM call 1  → prompt + optional competitor search tool call
        Tool call   → at most 1
        LLM call 2  → produces final JSON text
        Pydantic    → local json.loads() + model_validate()
    Total: 2 LLM calls, ≤1 tool call, 0 extra extraction calls.

    Input from state  : query (str), coral_notes (list[str]), critiques (list[str])
    Output to state   : competitor_output (str), competitors_list (list[str]),
                        debate_transcript entry
    """
    print(f"[competitor] round={state['round']}")

    query        = state["query"]
    coral_notes  = state.get("coral_notes", [])
    critiques    = state.get("critiques", [])

    never_worked     = [n for n in coral_notes if "never" in n.lower() or "failed" in n.lower()]
    avoid_context    = "\n".join(never_worked[:3]) if never_worked else "None recorded yet."
    critique_context = "\n".join(critiques[-2:]) if critiques else "First round."

    system = (
        "You are a market research analyst in a multi-agent AI decision system.\n"
        "You MUST call exactly ONE search tool before producing final JSON. "
        "Use duckduckgo_search or duckduckgo_results_json to verify competitors."
        "and to gather accurate market share or funding data.\n"
        "Only name companies you are confident are real.\n\n"
        "After any tool result (or immediately if no tool is needed), "
        "respond with ONLY a JSON object matching this exact schema — "
        "no preamble, no markdown fences:\n"
        "{\n"
        f"{_schema_hint(CompetitorOutput)}\n"
        "}"
    )

    human = f"""Business Idea:
{query}

Approaches to AVOID (CORAL memory — already failed):
{avoid_context}

Critiques to address from last round:
{critique_context}

Task:
1. Identify 3-5 REAL competitors in this space.
2. For each competitor provide: name, description, strengths, weaknesses,
   known market share or funding (state "unknown" if not verifiable).
3. Identify 2-3 genuine market gaps.
4. Suggest a concrete differentiation strategy.

Do NOT fabricate statistics. Use a search tool to verify claims.
Return ONLY the JSON object described in the system prompt."""

    rt    = _get_runtime()
    tools = getattr(rt, "tools", []) or []
    base_llm  = getattr(rt, "hf", None) if rt else None
    llm       = _bind(base_llm, tools)

    print(f"[competitor] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_output = await _llm_invoke_with_tools(llm, tools, _build_messages(system, human))

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    structured_output = raw_output
    competitors_list: list[str] = []

    obj, err = _parse_json_response(raw_output, CompetitorOutput)
    if obj:
        structured_output = structured_to_markdown(obj)
        competitors_list  = [c.name for c in obj.competitors]
        print(f"[competitor] structured OK — competitors={competitors_list} gaps={len(obj.market_gaps)}")
    else:
        print(f"[competitor] structured extraction failed (using raw): {err}")
        # Regex fallback: extract bold names from markdown
        competitors_list = [
            c.strip() for c in re.findall(r"\*\*(.+?)\*\*", raw_output)
            if len(c.strip()) > 2
        ][:5]

    return {
        "competitor_output":  structured_output,
        "competitors_list":   competitors_list,
        "debate_transcript": [{
            "agent":     "competitor",
            "round":     state["round"],
            "content":   structured_output,
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Critic Agent
# ─────────────────────────────────────────────────────────────────────────────

async def critic_node(state: AgentState) -> dict:
    """
    Critic agent — evaluates all three agent outputs.

    Call budget:
        LLM call 1  → prompt + optional fact-check tool call
        Tool call   → at most 1
        LLM call 2  → produces final JSON text
        Pydantic    → local json.loads() + model_validate()
    Total: 2 LLM calls, ≤1 tool call, 0 extra extraction calls.

    Input from state  : research_output (str), finance_output (str),
                        competitor_output (str), coral_notes (list[str]),
                        coral_attempts (list)
    Output to state   : critiques (list[str]), confidence_score (float),
                        best_score (float), evals_since_improvement (int),
                        round (int), debate_transcript entry
    """
    print(f"[critic] round={state['round']} — evaluating outputs")

    # All inputs are clean strings — no nested dicts cross node boundaries
    research   = state.get("research_output",   "[no output]")
    finance    = state.get("finance_output",    "[no output]")
    competitor = state.get("competitor_output", "[no output]")
    past_notes = "\n".join(state.get("coral_notes",    [])[:3])
    past_att   = "\n".join(str(a) for a in state.get("coral_attempts", [])[:3])

    system = (
    "You are a strict startup critic and experienced investor.\n"
    "You may use AT MOST ONE search tool to fact-check claims made by the "
    "research or competitor agents before scoring them.\n\n"

    "CRITICAL RULES:\n"
    "1. Tool calls are NOT final answers.\n"
    "2. After tool result, you MUST produce final JSON.\n"
    "3. Final output MUST be one JSON object only.\n"
    "4. DO NOT return an array.\n"
    "5. DO NOT wrap output in {\"type\":\"text\"} or similar.\n"
    "6. DO NOT include markdown fences.\n"
    "7. DO NOT include explanations outside JSON.\n\n"

    "FIELD RULES:\n"
    "- research_flaws must contain 3-5 strings.\n"
    "- finance_flaws must contain at least 1 string. If no flaw, write ['No specific finance flaws identified.'].\n"
    "- competitor_flaws must contain at least 1 string.\n"
    "- top_risks must contain exactly 3 strings.\n"
    "- confidence_score must be a number between 0.0 and 1.0.\n"
    "- reasoning must be a string.\n\n"

    "FINAL ANSWER FORMAT:\n"
    "{\n"
    f"{_schema_hint(CriticOutput)}\n"
    "}\n"
)

    human = f"""You have received three analyses from specialist agents.
Evaluate them, find flaws, and decide if more research is needed.

=== RESEARCH ANALYSIS ===
{research}

=== FINANCE ANALYSIS ===
{finance}

=== COMPETITOR ANALYSIS ===
{competitor}

=== CORAL MEMORY (past notes) ===
{past_notes or "None yet."}

=== CORAL ATTEMPTS (past scores) ===
{past_att or "None yet."}

Evaluation tasks:
1. List 3-5 specific flaws or missing information in the research.
2. Identify unrealistic assumptions in the finance projections.
3. Challenge the competitor analysis — are the gaps real?
4. Compare with past failures in CORAL memory.
5. List the top 3 risks to this business idea.
6. Give a confidence_score between 0.0 and 1.0:
   0.0-0.4 = Major issues     0.4-0.7 = Acceptable     0.7-0.85 = Good     0.85-1.0 = Excellent

Return ONLY the JSON object described in the system prompt."""

    rt    = _get_runtime()
    tools = getattr(rt, "tools", []) or []
    base_llm  = getattr(rt, "hf", None) if rt else None
    llm       = _bind(base_llm, tools)

    print(f"[critic] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_output = await _llm_invoke_with_tools(llm, tools, _build_messages(system, human))
    raw_output = unwrap_ai_text(raw_output)

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    new_confidence    = 0.5   # safe default
    structured_output = raw_output

    obj, err = _parse_json_response(raw_output, CriticOutput)
    if obj:
        new_confidence    = max(0.0, min(1.0, obj.confidence_score))
        structured_output = structured_to_markdown(obj)
        print(f"[critic] structured OK — confidence={new_confidence:.4f}")
    else:
        print(f"[critic] structured extraction failed — falling back to regex: {err}")
        raw_text = str(raw_output)
        match = re.search(
            r"confidence[_\s]*score[:\s]+([0-9]*\.?[0-9]+)",
            raw_text, re.IGNORECASE,
        )
        if match:
            new_confidence = max(0.0, min(1.0, float(match.group(1))))

    # ── Improvement tracking ──────────────────────────────────────────────────
    prev_best   = state.get("best_score", 0.0)
    improved    = new_confidence > prev_best
    evals_since = 0 if improved else state.get("evals_since_improvement", 0) + 1
    best_score  = max(prev_best, new_confidence)

    return {
        "critiques":               [structured_output],   # clean string inside list
        "confidence_score":        round(new_confidence, 4),
        "best_score":              round(best_score, 4),
        "evals_since_improvement": evals_since,
        "round":                   state["round"] + 1,
        "debate_transcript": [{
            "agent":     "critic",
            "round":     state["round"],
            "content":   structured_output,
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 6 — Heartbeat (CORAL)
# ─────────────────────────────────────────────────────────────────────────────

async def heartbeat_node(state: AgentState) -> dict:
    """
    CORAL heartbeat controller.
    No LLM call — pure memory + routing logic.

    Input from state  : session_id, round, confidence_score, confidence_threshold,
                        max_rounds, evals_since_improvement, critiques (list[str])
    Output to state   : heartbeat_action (str), heartbeat_prompts (list[str]),
                        debate_transcript entry
    """
    from coral.memory import CoralMemory
    from coral.heartbeat import HeartbeatRunner

    session_id = state["session_id"]
    round_num  = state["round"]
    confidence = state["confidence_score"]
    threshold  = state["confidence_threshold"]
    max_rounds = state["max_rounds"]
    stagnation = state["evals_since_improvement"]
    improved   = stagnation == 0

    memory    = CoralMemory(session_id=session_id)
    heartbeat = HeartbeatRunner(memory)

    # critiques is list[str] — last entry is the most recent clean text
    last_critique = state.get("critiques", ["(no critique)"])[-1]
    if isinstance(last_critique, dict):
        last_critique = str(last_critique)

    memory.write_attempt(
        agent_id="critic",
        output=last_critique[:500],
        score=confidence,
        feedback=(
            f"Confidence: {confidence:.2f} | Round: {round_num} | "
            f"Stagnation: {stagnation}"
        ),
        status="improved" if improved else "baseline",
    )

    prompts = heartbeat.record_eval(agent_id="critic", improved=improved)

    if prompts:
        memory.write_note(
            agent_id="critic",
            title=f"Heartbeat round {round_num} — confidence {confidence:.2f}",
            content="\n\n---\n\n".join(prompts),
            subfolder="agent-critic",
        )

    if confidence >= threshold:
        action = "exit"
    elif round_num >= max_rounds:
        action = "exit"
    elif stagnation >= 5:
        action = "pivot"
    else:
        action = "refine"

    print(
        f"[heartbeat] round={round_num} confidence={confidence:.2f} "
        f"stagnation={stagnation} action={action} prompts={len(prompts)}"
    )

    return {
        "heartbeat_action":  action,
        "heartbeat_prompts": prompts,          # list[str] — clean text
        "debate_transcript": [{
            "agent":     "heartbeat",
            "round":     round_num,
            "content":   (
                f"Action: {action} | Confidence: {confidence:.2f} | "
                f"Prompts fired: {len(prompts)}"
            ),
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 7 — CEO Agent
# ─────────────────────────────────────────────────────────────────────────────

async def ceo_node(state: AgentState) -> dict:
    """
    Final decision-maker agent.

    Call budget:
        LLM call 1  → prompt + optional final-validation tool call
        Tool call   → at most 1
        LLM call 2  → produces final JSON text
        Pydantic    → local json.loads() + model_validate()
    Total: 2 LLM calls, ≤1 tool call, 0 extra extraction calls.

    Input from state  : research_output (str), finance_output (str),
                        competitor_output (str), critiques (list[str]),
                        confidence_score (float), round (int), query (str)
    Output to state   : final_decision (str), reasoning_summary (str),
                        debate_transcript entry
    """
    from coral.memory import CoralMemory
    from coral.grader import Grader

    session_id = state["session_id"]
    confidence = state["confidence_score"]
    print(f"[ceo] producing final decision — confidence={confidence:.2f}")

    memory  = CoralMemory(session_id=session_id)
    grader  = Grader()

    leaderboard = memory.get_leaderboard(top_k=3)
    leaderboard_ctx = "\n".join(
        f"  #{i+1} score={a['score']:.2f}: {a['output'][:120]}..."
        for i, a in enumerate(leaderboard)
    ) if leaderboard else "No prior decisions."

    # All inputs from state are already clean strings
    research         = state.get("research_output",   "[unavailable]")
    finance          = state.get("finance_output",    "[unavailable]")
    competitor       = state.get("competitor_output", "[unavailable]")
    critiques        = state.get("critiques", [])
    critique_summary = critiques[-1][:600] if critiques else "No critiques."

    system = (
    "You are the CEO of a venture-backed AI company.\n"
    "You may call AT MOST ONE search tool to do final validation of key claims "
    "before making your investment recommendation.\n\n"

    "CRITICAL RULES:\n"
    "1. Tool calls are NOT final answers.\n"
    "2. After tool result, you MUST produce final JSON.\n"
    "3. Final output MUST be one JSON object only.\n"
    "4. DO NOT return an array.\n"
    "5. DO NOT wrap output in {\"type\":\"text\"} or similar.\n"
    "6. DO NOT include markdown fences.\n"
    "7. DO NOT include explanations outside JSON.\n\n"

    "FIELD RULES:\n"
    "- recommendation must be one of: PROCEED, DO NOT PROCEED, CONDITIONAL PROCEED.\n"
    "- confidence_percent must be a number between 0 and 100.\n"
    "- reasoning must be 3-5 sentences.\n"
    "- key_success_conditions must contain exactly 3 strings.\n"
    "- risk_mitigations must contain exactly 3 strings.\n"
    "- critic_concerns_addressed must contain at least 1 string.\n\n"

    "FINAL ANSWER FORMAT:\n"
    "{\n"
    f"{_schema_hint(CEOOutput)}\n"
    "}\n"
)

    human = f"""=== RESEARCH ===
{research[:800]}

=== FINANCE ===
{finance[:800]}

=== COMPETITOR ANALYSIS ===
{competitor[:800]}

=== CRITIC SUMMARY ===
{critique_summary}

=== TOP PAST DECISIONS (CORAL leaderboard) ===
{leaderboard_ctx}

=== CURRENT STATE ===
- Debate rounds completed: {state["round"]}
- Final confidence score: {confidence:.2f}
- Query: {state["query"]}

Your task:
1. Synthesise all three analyses.
2. Address the critic's top concerns.
3. Make a clear PROCEED / DO NOT PROCEED / CONDITIONAL PROCEED recommendation.
4. State your confidence as a percentage.
5. List 3 key success conditions.
6. List 3 risk mitigations.

Return ONLY the JSON object described in the system prompt."""

    rt    = _get_runtime()
    tools = getattr(rt, "tools", []) or []
    base_llm = (
        getattr(rt, "hf", None) or getattr(rt, "grok", None)
    ) if rt else None
    llm = _bind(base_llm, tools)

    print(f"[ceo] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_output = await _llm_invoke_with_tools(llm, tools, _build_messages(system, human))
    raw_output = unwrap_ai_text(raw_output)

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    structured_output = raw_output
    obj, err = _parse_json_response(raw_output, CEOOutput)
    if obj:
        structured_output = structured_to_markdown(obj)
        print(f"[ceo] structured OK — recommendation={obj.recommendation} confidence={obj.confidence_percent:.1f}%")
    else:
        print(f"[ceo] structured extraction failed (using raw): {err}")

    # ── Grade + CORAL write ───────────────────────────────────────────────────
    grade = grader.grade(
        decision=structured_output,
        critiques=critiques,
        research=research,
    )

    prev_best = state.get("best_score", 0.0)
    memory.write_attempt(
        agent_id="ceo",
        output=structured_output[:800],
        score=grade.score,
        feedback=grade.feedback,
        status="improved" if grade.score > prev_best else "baseline",
    )

    memory.write_note(
        agent_id="ceo",
        title=f"Decision round {state['round']} — grader {grade.score:.2f}",
        content=(
            f"Query: {state['query']}\n\n"
            f"Decision:\n{structured_output}\n\n"
            f"Grade: {grade.feedback}\n"
            f"Breakdown: {grade.breakdown}"
        ),
        subfolder="agent-ceo",
    )

    try:
        from memory.vector_store import add_text
        add_text(
            f"Decision for: {state['query']}\n\n{structured_output}",
            metadata={
                "session_id": session_id,
                "round":      state["round"],
                "confidence": confidence,
                "score":      grade.score,
            },
        )
    except Exception as exc:
        print(f"[ceo] vector store write failed (non-fatal): {exc}")

    return {
        "final_decision": structured_output,      # clean string
        "reasoning_summary": (
            f"Completed {state['round']} debate rounds. "
            f"Agent confidence: {confidence:.2f}. "
            f"Grader score: {grade.score:.2f}. "
            f"Verdict: {grade.feedback}"
        ),
        "debate_transcript": [{
            "agent":     "ceo",
            "round":     state["round"],
            "content":   structured_output,
            "timestamp": time.time(),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 8 — Meta-Eval
# ─────────────────────────────────────────────────────────────────────────────

async def meta_eval_node(state: AgentState) -> dict:
    """
    Post-decision quality evaluation. No LLM call.
    Returns safe empty defaults so state reducers never receive None.
 
    Input from state  : final_decision (str), confidence_score (float),
                        round (int), session_id (str)
    Output to state   : {} with safe defaults (logging only in Phase 2)
    """
    # Safely coerce every field — never trust state values to be non-None
    final   = state.get("final_decision")   or ""
    score   = state.get("confidence_score") or 0.0
    rounds  = state.get("round")            or 0
    session = state.get("session_id")       or "unknown"
 
    print(
        f"[meta_eval] session={session} rounds={rounds} "
        f"confidence={score:.2f} decision_length={len(final)}"
    )
 
    # Return safe defaults so downstream reducers never get None
    return {
        "final_decision":    final   or "",
        "reasoning_summary": state.get("reasoning_summary") or "",
        "coral_notes":       state.get("coral_notes")       or [],
        "coral_attempts":    state.get("coral_attempts")    or [],
        "coral_skills":      state.get("coral_skills")      or [],
        "critiques":         state.get("critiques")         or [],
        "debate_transcript": state.get("debate_transcript") or [],
    }
 