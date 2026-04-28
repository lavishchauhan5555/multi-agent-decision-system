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
    - Pydantic     : PydanticOutputParser.parse() — NO extra LLM call
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
from datetime import datetime

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
# HELPERS function only for resherch node
# ─────────────────────────────────────────────────────────────────────────────

async def _run_one_research_search(tools: list, query: str) -> str:
    """
    Enforces exactly one research search call.
    Does not depend on the LLM choosing a tool.
    """
    search_tool = next(
        (
            t for t in tools
            if getattr(t, "name", None) in ["duckduckgo_results_json", "duckduckgo_search"]
        ),
        None
    )

    if search_tool is None:
        return "Search tool unavailable."

    search_query = (
        f"{query} market size CAGR growth trends competitors key players 2026"
    )

    try:
        if hasattr(search_tool, "ainvoke"):
            result = await search_tool.ainvoke({"query": search_query})
        else:
            result = await asyncio.to_thread(search_tool.invoke, {"query": search_query})

        text = unwrap_ai_text(result)
        return text[:8000]

    except Exception as exc:
        return f"Search failed: {exc}"
    


# ─────────────────────────────────────────────────────────────────────────────
# Helper: exactly one current competitor search
# ─────────────────────────────────────────────────────────────────────────────

async def _run_one_competitor_search(tools: list, query: str) -> str:
    current_year = datetime.now().year

    search_tool = next(
        (
            t for t in tools
            if getattr(t, "name", None) in [
                "duckduckgo_results_json",
                "duckduckgo_search",
            ]
        ),
        None,
    )

    if search_tool is None:
        return "Search tool unavailable."

    search_query = (
        f"{query} real competitors market share funding alternatives "
        f"startups companies {current_year}"
    )

    try:
        payload = {"query": search_query}

        if hasattr(search_tool, "ainvoke"):
            result = await asyncio.wait_for(search_tool.ainvoke(payload), timeout=30)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(search_tool.invoke, payload),
                timeout=30,
            )

        text = unwrap_ai_text(result)
        return text[:8000]

    except asyncio.TimeoutError:
        return "Search failed: timeout"
    except Exception as exc:
        return f"Search failed: {exc}"    



# ─────────────────────────────────────────────────────────────────────────────
# Helper: for citric node
# ─────────────────────────────────────────────────────────────────────────────


async def _run_one_critic_fact_check(tools: list, query: str, research: str, competitor: str) -> str:
    search_tool = next(
        (
            t for t in tools
            if getattr(t, "name", None) in ["duckduckgo_results_json", "duckduckgo_search"]
        ),
        None,
    )

    if search_tool is None:
        return "Fact-check search unavailable."

    fact_query = (
        f"{query} market size competitors funding growth risks latest evidence"
    )

    try:
        payload = {"query": fact_query}

        if hasattr(search_tool, "ainvoke"):
            result = await asyncio.wait_for(search_tool.ainvoke(payload), timeout=30)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(search_tool.invoke, payload),
                timeout=30,
            )

        return unwrap_ai_text(result)[:6000]

    except asyncio.TimeoutError:
        return "Fact-check search timed out."
    except Exception as exc:
        return f"Fact-check search failed: {exc}"
    
# ─────────────────────────────────────────────────────────────────────────────
# HELPERS:ceo node helper
# ─────────────────────────────────────────────────────────────────────────────


async def _run_one_ceo_validation_search(tools: list, query: str) -> str:
    search_tool = next(
        (
            t for t in tools
            if getattr(t, "name", None) in ["duckduckgo_results_json", "duckduckgo_search"]
        ),
        None,
    )

    if search_tool is None:
        return "Final validation search unavailable."

    search_query = (
        f"{query} market opportunity risks competitors funding growth latest validation"
    )

    try:
        payload = {"query": search_query}

        if hasattr(search_tool, "ainvoke"):
            result = await asyncio.wait_for(search_tool.ainvoke(payload), timeout=30)
        else:
            result = await asyncio.wait_for(
                asyncio.to_thread(search_tool.invoke, payload),
                timeout=30,
            )

        return unwrap_ai_text(result)[:6000]

    except asyncio.TimeoutError:
        return "Final validation search timed out."
    except Exception as exc:
        return f"Final validation search failed: {exc}"    


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# def _safe_content(response) -> str:
#     """Extract a plain string from any LangChain response object."""
#     if response is None:
#         return "[ERROR] LLM returned None"

#     from pydantic import BaseModel as PydanticBase
#     if isinstance(response, PydanticBase):
#         return structured_to_markdown(response)

#     if hasattr(response, "content"):
#         content = response.content
#         if isinstance(content, list):
#             parts = [
#                 block.get("text", "") if isinstance(block, dict) else str(block)
#                 for block in content
#             ]
#             return "\n".join(p for p in parts if p).strip()
#         return content or ""

#     return str(response)
def _safe_content(response) -> str:
    if response is None:
        return "[ERROR] LLM returned None"

    content = getattr(response, "content", None)

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(block))

        text = "\n".join(parts).strip()
        if text:
            return text

    usage = getattr(response, "usage_metadata", None)
    if usage:
        return "[ERROR] LLM returned usage metadata but no content"

    return str(response)


def _extract_json_candidates(text: str) -> list[str]:
    """Extract possible JSON objects from text using markdown stripping + brace counting."""
    clean = re.sub(r"```(?:json)?\s*", "", text.strip())
    clean = re.sub(r"```", "", clean).strip()

    # ✅ Prefer full outer JSON object first
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return [clean]
    except Exception:
        pass

    candidates: list[str] = []
    i = 0

    while i < len(clean):
        if clean[i] == "{":
            depth = 0
            in_string = False
            escape = False
            start = i

            for j in range(i, len(clean)):
                ch = clean[j]

                if escape:
                    escape = False
                    continue

                if ch == "\\":
                    escape = True
                    continue

                if ch == '"':
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1

                    if depth == 0:
                        candidate = clean[start:j + 1]

                        # ✅ Only keep JSON objects, skip null/list/string/etc
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                candidates.append(candidate)
                        except Exception:
                            pass

                        i = j + 1
                        break
            else:
                break
        else:
            i += 1

    candidates.sort(key=len, reverse=True)
    return candidates


def _parse_json_response(raw: str, model_class):
    print(f"[parser] calling PydanticOutputParser for {model_class.__name__}")

    if not raw or not isinstance(raw, str):
        return None, "Empty or non-string input"

    try:
        from langchain_core.output_parsers import PydanticOutputParser
    except Exception as exc:
        return None, f"PydanticOutputParser import failed: {exc}"

    parser = PydanticOutputParser(pydantic_object=model_class)
    text = unwrap_ai_text(raw).strip()

    last_err = "Unknown parse error"

    # ✅ Try full response first
    try:
        parsed_json = json.loads(text)
        if isinstance(parsed_json, dict):
            return parser.parse(text), None
    except Exception as exc:
        last_err = str(exc)

    candidates = _extract_json_candidates(text)

    if not candidates:
        return None, f"No JSON object found in response: {text[:160]}"

    for candidate in candidates:
        try:
            parsed_json = json.loads(candidate)

            # ✅ Skip null, arrays, strings, numbers
            if not isinstance(parsed_json, dict):
                continue

            return parser.parse(candidate), None

        except Exception as exc:
            last_err = str(exc)

    return None, f"All JSON candidates failed validation. Last error: {last_err}"

def _schema_hint(model_class) -> str:
    """
    Build parser-backed format instructions for prompts.
    The actual parsing is done by PydanticOutputParser in _parse_json_response().
    """
    try:
        from langchain_core.output_parsers import PydanticOutputParser
        return PydanticOutputParser(pydantic_object=model_class).get_format_instructions()
    except Exception:
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
        for i, r in results:
            score = getattr(r, "score", None)
            text = getattr(r, "text", None)
            if not text and hasattr(r, "node"):
                text = r.node.get_content()
                print(f"[rag_retrieve] result {i+1} score={score}")
                print(f"[rag_retrieve] text preview={text[:200] if text else 'NO TEXT'}")
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
                content = _safe_content(first_response)

                try:
                    maybe = json.loads(content)
                    if isinstance(maybe, dict) and maybe.get("name") in tool_map:
                        tool_name = maybe["name"]
                        tool_args = maybe.get("arguments") or maybe.get("args") or {}

                        print(f"[tool_loop] parsed fake tool call selected='{tool_name}'")

                        tool_output = await _invoke_tool(tool_map[tool_name], tool_args)
                        print(f"[tool_loop] '{tool_name}' -> {tool_output[:160]}...")

                        from langchain_core.messages import HumanMessage

                        followup = list(messages)
                        followup.append(HumanMessage(content=f"""
            Tool result for {tool_name}:
            {tool_output}

            Now return ONLY the final JSON object matching the schema.
            Do NOT call tools again.
            """))

                        final_response = await _llm_call(followup)
                        return _safe_content(final_response)

                except Exception:
                    pass

                return content
        
 
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

        # Force the second model response to be final JSON content, not another tool call.
        try:
            from langchain_core.messages import HumanMessage
            followup.append(HumanMessage(content=(
                "Tool result received. Do NOT call any more tools. "
                "Return ONLY the final JSON object that matches the schema."
            )))
        except Exception:
            pass
 
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
CACHE_THRESHOLD = 0.70

async def cache_check_node(state: AgentState) -> dict:
    query = state["query"]
    print(f"[cache_check] query='{query[:60]}...'")

    try:
        from memory.vector_store import get_index
        index = get_index()

        if index is None:
            print("[cache_check] Vector store unavailable — CACHE MISS")
            return {"cached_result": None, "cache_score": 0.0}

        retriever = index.as_retriever(similarity_top_k=1)
        results = await asyncio.to_thread(retriever.retrieve, query)

        if results:
            top = results[0]
            score = getattr(top, "score", None) or 0.0

            text = getattr(top, "text", None)
            if not text and hasattr(top, "node"):
                text = top.node.get_content()

            print(f"[cache_check] top score={score:.4f}")
            print(f"[cache_check] threshold={CACHE_THRESHOLD}")
            print(f"[cache_check] text preview={text[:300] if text else 'NO TEXT'}")

            if score >= CACHE_THRESHOLD:
                print("[cache_check] CACHE HIT")
                return {
                    "cached_result": text,
                    "cache_score": round(score, 4),
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
        Pydantic    → local PydanticOutputParser.parse()
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

    rt        = _get_runtime()
    tools     = getattr(rt, "tools", []) or []
    base_llm  = getattr(rt, "hf", None) if rt else None
    # 🔴 ADD THIS HERE
    if base_llm is None:
        return {
            "research_output": "[STUB] Research LLM not configured",
            "debate_transcript": [{
                "agent": "research",
                "round": state["round"],
                "content": "[STUB] Research LLM not configured",
                "timestamp": time.time(),
            }],
        }
    search_context = await _run_one_research_search(tools, query)

    system = (
    "You are a senior research analyst in a multi-agent AI decision system.\n"
    "You produce deep, structured, decision-grade market intelligence.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🔧 TOOL USAGE\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "- You will receive external search data in the prompt.\n"
    "- DO NOT call tools yourself.\n"
    "- Use provided search results + RAG as primary sources.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🧠 INFORMATION PRIORITY\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "1. RAG knowledge (most reliable)\n"
    "2. Search results (for freshness)\n"
    "3. CORAL memory (for improvements)\n\n"

    "- Never hallucinate missing data.\n"
    "- If unsure → return 'data unavailable'.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ CRITIQUE HANDLING\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "- You MUST address ALL critiques explicitly.\n"
    "- Each critique must map to one improvement.\n"
    "- Add explanations inside 'critique_responses'.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📊 DEPTH REQUIREMENTS (STRICT)\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Minimum output quality:\n"

    "- market_size: 2-4 detailed sentences with numbers.\n"
    "- growth_rate: 2-3 sentences with CAGR or trend.\n"
    "- trends: EXACTLY 6 items, each 15-30 words.\n"
    "- key_players: EXACTLY 6 real companies.\n"
    "- opportunities: EXACTLY 5 items (problem + business angle).\n"
    "- risks: EXACTLY 5 items (cause + impact).\n"
    "- evidence_points: 3-6 factual insights (numbers, stats, facts).\n"
    "- raw_summary: 150-220 words.\n\n"

    "🚫 If any section is too short or generic → output is INVALID.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📊 QUALITY RULES\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "- Use real-world data when possible.\n"
    "- Avoid generic phrases like 'market is growing'.\n"
    "- Each bullet must contain reasoning or data.\n"
    "- Avoid repetition across fields.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🚫 OUTPUT RULES (CRITICAL)\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "1. Return ONLY a single JSON object.\n"
    "2. No markdown, no explanations.\n"
    "3. No extra text before or after JSON.\n"
    "4. Do NOT wrap JSON in arrays.\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📌 FIELD RULES\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "- trends, key_players, opportunities, risks, critique_responses, evidence_points → arrays of strings\n"
    "- market_size, growth_rate, raw_summary → strings\n"
    "- If missing → use 'data unavailable' or ['data unavailable']\n\n"

    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📦 OUTPUT FORMAT\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "{\n"
    f"{_schema_hint(ResearchOutput)}\n"
    "}"
    )

    human = f"""
    User Query:
    {query}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    📚 RAG CONTEXT
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {rag_context}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🌐 SEARCH RESULTS
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {search_context}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🧠 CORAL MEMORY
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {coral_context}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ CRITIQUES
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {critique_context}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🎯 TASK
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Generate complete market research covering:

    • Market size  
    • Growth rate  
    • Trends  
    • Key players  
    • Opportunities  
    • Risks  
    • Evidence-backed insights  

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ IMPORTANT
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Use RAG first, search second.
    - Do NOT ignore search results.
    - Do NOT produce short answers.
    - Every field must meet depth requirements.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🚫 FINAL INSTRUCTION
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Return ONLY valid JSON.
    """


    # llm       = _bind(base_llm, tools)

    # print(f"[research] llm={type(llm).__name__ if llm else 'STUB'} tools={[t.name for t in tools]}")

    raw_response = await base_llm.ainvoke(_build_messages(system, human))


    raw_output = _safe_content(raw_response)

    raw_output = _safe_content(raw_response)

    # ── Local Pydantic parse — zero extra LLM calls ───────────────────────────
    structured_output = raw_output
    obj, err = _parse_json_response(raw_output, ResearchOutput)
    if obj:
        structured_output = structured_to_markdown(obj)
        
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
    print(f"[finance] round={state['round']}")

    query = state["query"]
    critiques = state.get("critiques", [])
    coral_skills = state.get("coral_skills", [])

    critique_context = "\n".join(critiques[-2:]) if critiques else "First round — no critiques yet."

    skills_context = "\n".join(
        f"- {s.get('name', '')}: {s.get('content', '')[:200]}"
        for s in coral_skills[:3]
        if isinstance(s, dict)
    ) if coral_skills else "No reusable skills available."

    # ─────────────────────────────────────────────────────────────────────
    # 1. Finance assumptions
    # These can come from state later if frontend provides them.
    # ─────────────────────────────────────────────────────────────────────

    assumptions = {
        "initial_investment": float(state.get("initial_investment", 10000.0)),
        "starting_revenue": float(state.get("starting_revenue", 5000.0)),
        "monthly_growth_rate": float(state.get("monthly_growth_rate", 0.15)),
        "monthly_fixed_cost": float(state.get("monthly_fixed_cost", 12000.0)),
        "gross_margin": float(state.get("gross_margin", 0.75)),
        "estimated_cac": float(state.get("estimated_cac", 800.0)),
        "months": 12,
    }

    initial_investment = assumptions["initial_investment"]
    starting_revenue = assumptions["starting_revenue"]
    monthly_growth_rate = assumptions["monthly_growth_rate"]
    monthly_fixed_cost = assumptions["monthly_fixed_cost"]
    gross_margin = assumptions["gross_margin"]
    estimated_cac = assumptions["estimated_cac"]

    # ─────────────────────────────────────────────────────────────────────
    # 2. Deterministic calculations
    # No LLM arithmetic.
    # ─────────────────────────────────────────────────────────────────────

    monthly_projections = []
    cumulative_cashflow = -initial_investment
    payback_months = None
    break_even_month = None
    max_monthly_burn = 0.0

    for month in range(1, 13):
        revenue = round(starting_revenue * ((1 + monthly_growth_rate) ** (month - 1)), 2)

        # Gross-profit-aware model
        gross_profit = round(revenue * gross_margin, 2)
        cost = round(monthly_fixed_cost, 2)
        net = round(gross_profit - cost, 2)

        cumulative_cashflow = round(cumulative_cashflow + net, 2)

        if net < 0:
            max_monthly_burn = max(max_monthly_burn, abs(net))

        if break_even_month is None and net >= 0:
            break_even_month = month

        if payback_months is None and cumulative_cashflow >= 0:
            payback_months = float(month)

        monthly_projections.append({
            "month": month,
            "revenue": revenue,
            "cost": cost,
            "net": net,
        })

    total_revenue = round(sum(m["revenue"] for m in monthly_projections), 2)
    operating_cost = round(sum(m["cost"] for m in monthly_projections), 2)

    total_cost = round(operating_cost + initial_investment, 2)

    # Net profit after operating costs + initial investment
    net_profit = round(sum(m["net"] for m in monthly_projections) - initial_investment, 2)

    roi_percent = round((net_profit / total_cost) * 100, 2) if total_cost else 0.0

    estimated_runway_needed = round(initial_investment + max_monthly_burn * 6, 2)

    base_finance_json = {
        "initial_investment": initial_investment,
        "monthly_projections": monthly_projections,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "payback_months": payback_months,
    }

    # ─────────────────────────────────────────────────────────────────────
    # 3. Deterministic recommendation
    # ─────────────────────────────────────────────────────────────────────

    if net_profit > 0 and roi_percent >= 20 and payback_months is not None:
        deterministic_recommendation = (
            "GO — positive net profit, ROI above 20%, and payback visible within 12 months."
        )
    elif net_profit > 0 and payback_months is not None:
        deterministic_recommendation = (
            "CONDITIONAL GO — profitable, but ROI and payback quality should be improved before aggressive scaling."
        )
    elif net_profit < 0 and payback_months is None:
        deterministic_recommendation = (
            "NO-GO — projected 12-month ROI is negative and payback is not reached."
        )
    else:
        deterministic_recommendation = (
            "CONDITIONAL GO — proceed only after reducing fixed costs, validating CAC, and improving payback."
        )

    # ─────────────────────────────────────────────────────────────────────
    # 4. Safe deterministic fallback object
    # ─────────────────────────────────────────────────────────────────────

    fallback_obj = FinanceOutput(
        **base_finance_json,
        financial_risks=[
            (
                f"Payback risk: payback_months={payback_months}, meaning the business "
                "does not clearly recover its initial investment within the modeled period."
            ),
            (
                f"CAC risk: estimated CAC is ${estimated_cac}, but customer acquisition cost "
                "is not directly deducted from monthly projections, so real profit may be lower."
            ),
            (
                f"Burn risk: maximum monthly burn is approximately ${max_monthly_burn}, "
                f"so estimated runway needed is about ${estimated_runway_needed}."
            ),
        ],
        recommendation=deterministic_recommendation,
        critique_responses=[
            "Used deterministic calculations for all financial numbers instead of relying on LLM arithmetic.",
            "Included initial investment in total cost and ROI calculation.",
            "Added gross-margin-aware net calculation, payback risk, CAC risk, burn risk, and runway context.",
        ],
    )

    # ─────────────────────────────────────────────────────────────────────
    # 5. LLM only enriches risks/recommendation text
    # It must not change numbers.
    # ─────────────────────────────────────────────────────────────────────

    system = (
        "You are a senior startup finance analyst in a multi-agent AI decision system.\n"
        "You MUST NOT call tools.\n"
        "You MUST NOT perform new calculations.\n"
        "Use the provided deterministic finance calculations exactly.\n\n"

        "CRITICAL RULES:\n"
        "1. Return ONLY valid JSON.\n"
        "2. No markdown.\n"
        "3. No explanation outside JSON.\n"
        "4. Do not call calculator, search, Python, or any tool.\n"
        "5. monthly_projections must contain exactly 12 items.\n"
        "6. Do not change any numeric values.\n"
        "7. financial_risks must contain exactly 3 detailed strings.\n"
        "8. critique_responses must be an array of strings.\n"
        "9. recommendation must be one of: GO, NO-GO, CONDITIONAL GO, followed by a short reason.\n\n"

        "DECISION LOGIC:\n"
        "- If ROI is negative and payback_months is null, prefer NO-GO.\n"
        "- If profit is positive but risk is high, use CONDITIONAL GO.\n"
        "- Use GO only when profit, ROI, and payback are strong.\n\n"

        "Return JSON matching this schema:\n"
        f"{_schema_hint(FinanceOutput)}"
    )

    human = f"""
Business Idea:
{query}

Available Reusable Skills:
{skills_context}

Critiques to Address:
{critique_context}

Assumptions Used:
{json.dumps(assumptions, indent=2)}

Extra Deterministic Metrics:
{json.dumps({
    "break_even_month": break_even_month,
    "max_monthly_burn": max_monthly_burn,
    "estimated_runway_needed": estimated_runway_needed,
    "operating_cost": operating_cost,
    "gross_margin": gross_margin,
    "estimated_cac": estimated_cac
}, indent=2)}

Deterministic Finance Calculations:
{json.dumps(base_finance_json, indent=2)}

Required:
Return a complete FinanceOutput JSON object.

You MUST use the exact numeric values from Deterministic Finance Calculations.
Only improve:
- financial_risks
- recommendation
- critique_responses
"""

    # ─────────────────────────────────────────────────────────────────────
    # 6. Runtime model
    # IMPORTANT: build_agent() must store plain models, not bind_tools().
    # ─────────────────────────────────────────────────────────────────────

    rt = _get_runtime()
    base_llm = getattr(rt, "hf", None) if rt else None

    print(
        f"[finance] llm={type(base_llm).__name__ if base_llm else 'STUB'} "
        "tools=DISABLED_FOR_FINANCE"
    )

    obj = fallback_obj

    if base_llm is not None:
        try:
            response = await asyncio.wait_for(
                base_llm.ainvoke(_build_messages(system, human)),
                timeout=60,
            )

            raw_output = unwrap_ai_text(_safe_content(response))
            print("[finance] raw_output preview:", raw_output[:500])

            parsed_obj, err = _parse_json_response(raw_output, FinanceOutput)

            if parsed_obj:
                obj = parsed_obj

                # Safety: force deterministic numbers even if LLM changed them
                obj.initial_investment = base_finance_json["initial_investment"]
                obj.monthly_projections = base_finance_json["monthly_projections"]
                obj.total_revenue = base_finance_json["total_revenue"]
                obj.total_cost = base_finance_json["total_cost"]
                obj.net_profit = base_finance_json["net_profit"]
                obj.roi_percent = base_finance_json["roi_percent"]
                obj.payback_months = base_finance_json["payback_months"]

            else:
                print(f"[finance] LLM structured parse failed, using fallback: {err}")
                obj = fallback_obj

        except Exception as exc:
            print(f"[finance] LLM failed, using fallback: {exc}")
            obj = fallback_obj

    # ─────────────────────────────────────────────────────────────────────
    # 7. Final output
    # ─────────────────────────────────────────────────────────────────────

    structured_output = structured_to_markdown(obj)



    return {
        "finance_output": structured_output,

        # Optional but useful for frontend/CEO/critic if your AgentState allows it
        "finance_json": obj.model_dump(),

        "debate_transcript": [{
            "agent": "finance",
            "round": state["round"],
            "content": structured_output,
            "timestamp": time.time(),
        }],
    }




# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — Production Competitor Agent
# ─────────────────────────────────────────────────────────────────────────────

async def competitor_node(state: AgentState) -> dict:
   

    query = state["query"]
    coral_notes = state.get("coral_notes", [])
    critiques = state.get("critiques", [])

    never_worked = [
        n for n in coral_notes
        if isinstance(n, str) and ("never" in n.lower() or "failed" in n.lower())
    ]

    avoid_context = "\n".join(never_worked[:3]) if never_worked else "None recorded yet."
    critique_context = "\n".join(critiques[-2:]) if critiques else "First round — no critiques yet."

    rt = _get_runtime()
    tools = getattr(rt, "tools", []) or []

    # Use plain model. Do NOT use bound tool model here.
    base_llm = getattr(rt, "hf", None) if rt else None

    if base_llm is None:
        fallback_obj = CompetitorOutput(
            competitors=[],
            market_gaps=[],
            differentiation_strategy="Competitor LLM not configured.",
            approaches_to_avoid=["No failed approach recorded"],
            critique_responses=["Competitor analysis used fallback because LLM was unavailable."],
            evidence_points=["Search and LLM unavailable."],
        )

        structured_output = structured_to_markdown(fallback_obj)

        return {
            "competitor_output": structured_output,
            "competitors_list": [c.name for c in fallback_obj.competitors],
            "debate_transcript": [{
                "agent": "competitor",
                "round": state["round"],
                "content": structured_output,
                "timestamp": time.time(),
            }],
        }

    search_context = await _run_one_competitor_search(tools, query)

    current_year = datetime.now().year

    system = (
        "You are a senior competitive intelligence analyst in a multi-agent AI decision system.\n"
        "You produce current, evidence-backed competitor analysis for startup decisions.\n\n"

        "TOOL RULES:\n"
        "- You will receive external search results in the prompt.\n"
        "- DO NOT call tools yourself.\n"
        "- Use the provided search results to verify current competitors.\n\n"

        "CURRENTNESS RULES:\n"
        f"- Prefer data from {current_year - 1} and {current_year}.\n"
        "- Avoid outdated competitors unless they are still active and relevant.\n"
        "- If market share or funding is not verifiable, use 'unknown'.\n\n"

        "STRICT COMPETITOR RULES:\n"
        "- Only include real companies.\n"
        "- Do not invent market share, funding, or traction.\n"
        "- Each competitor must have 2-3 strengths and 2-3 weaknesses.\n"
        "- Identify 3-5 competitors.\n"
        "- Identify 2-3 market gaps.\n"
        "- differentiation_strategy must be 2-4 detailed sentences.\n"
        "- evidence_points must include 3-6 specific facts from search/RAG.\n\n"

        "CRITIQUE RULES:\n"
        "- Address every critique explicitly in critique_responses.\n"
        "- Use approaches_to_avoid from CORAL memory.\n\n"

        "OUTPUT RULES:\n"
        "- Return ONLY valid JSON.\n"
        "- No markdown.\n"
        "- No explanation outside JSON.\n"
        "- Do not wrap JSON in an array.\n\n"

        "Return JSON matching this schema:\n"
        f"{_schema_hint(CompetitorOutput)}"
    )

    human = f"""
Business Idea:
{query}

Current Search Results:
{search_context}

Approaches to Avoid from CORAL Memory:
{avoid_context}

Critiques to Address:
{critique_context}

Task:
Generate a production-grade competitor analysis.

Required:
- 3-5 real competitors
- 2-3 strengths per competitor
- 2-3 weaknesses per competitor
- market_share_or_funding if verifiable, otherwise "unknown"
- 2-3 market gaps
- 2-4 sentence differentiation strategy
- approaches_to_avoid as list
- critique_responses as list
- evidence_points as list

Return ONLY valid JSON.
"""



    fallback_obj = CompetitorOutput(
        competitors=[],
        market_gaps=[
            "Reliable competitor data unavailable from model output.",
            "Manual validation required before final business decision.",
        ],
        differentiation_strategy=(
            "Use a focused niche strategy until competitor positioning is verified. "
            "Avoid broad positioning without validated market evidence."
        ),
        approaches_to_avoid=[avoid_context],
        critique_responses=[
            "Used fallback because structured competitor parsing failed."
        ],
        evidence_points=[
            search_context[:300] if search_context else "Search data unavailable.",
            "Market share or funding should be treated as unknown unless verifiable.",
            "Competitor list requires validation from current sources.",
        ],
    )

    try:
        response = await asyncio.wait_for(
            base_llm.ainvoke(_build_messages(system, human)),
            timeout=60,
        )

        raw_output = unwrap_ai_text(_safe_content(response))

        # ("[compprintetitor] raw_output preview:", raw_output[:500])

        obj, err = _parse_json_response(raw_output, CompetitorOutput)

        if not obj:
            # print(f"[competitor] structured extraction failed, using fallback: {err}")
            obj = fallback_obj
        else:
            print(
                f"[competitor] structured OK — competitors="
                f"{[c.name for c in obj.competitors]} gaps={len(obj.market_gaps)}"
            )

    except Exception as exc:
        # print(f"[competitor] LLM failed, using fallback: {exc}")
        obj = fallback_obj

    structured_output = structured_to_markdown(obj)
    competitors_list = [c.name for c in obj.competitors if c.name != "unknown"]

    return {
        "competitor_output": structured_output,
        "competitors_list": competitors_list,

        # Optional if your AgentState allows this
        "competitor_json": obj.model_dump(),

        "debate_transcript": [{
            "agent": "competitor",
            "round": state["round"],
            "content": structured_output,
            "timestamp": time.time(),
        }],
    }




# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Critic Agent
# ─────────────────────────────────────────────────────────────────────────────

async def critic_node(state: AgentState) -> dict:
    # print(f"[critic] round={state['round']} — evaluating outputs")

    research = state.get("research_output", "[no output]")
    finance = state.get("finance_output", "[no output]")
    competitor = state.get("competitor_output", "[no output]")

    query = state.get("query", "")
    past_notes = "\n".join(state.get("coral_notes", [])[:3])
    past_att = "\n".join(str(a) for a in state.get("coral_attempts", [])[:3])

    rt = _get_runtime()
    tools = getattr(rt, "tools", []) or []
    base_llm = (
        getattr(rt, "gemini", None)
        or getattr(rt, "grok", None)
        or getattr(rt, "hf", None)
    ) if rt else None

    fact_check_context = await _run_one_critic_fact_check(
        tools=tools,
        query=query,
        research=research,
        competitor=competitor,
    )

    fallback_obj = CriticOutput(
        research_flaws=[
            "Research claims require stronger source validation before decision-making.",
            "Market sizing may not be specific enough to the target customer segment.",
            "Customer adoption assumptions need clearer evidence."
        ],
        finance_flaws=[
            "Finance model depends on simplified assumptions and may not fully include CAC, churn, and scaling costs."
        ],
        competitor_flaws=[
            "Competitor positioning may be incomplete without direct comparison against active alternatives."
        ],
        top_risks=[
            "Market demand may be weaker than assumed.",
            "Unit economics may worsen after CAC, churn, and operational scaling costs.",
            "Competitors may respond quickly with better pricing or distribution."
        ],
        confidence_score=0.45,
        reasoning=(
            "Fallback critic output used because the critic model was unavailable or failed. "
            "The decision should not proceed without validating research, finance, and competitor assumptions."
        ),
    )

    if base_llm is None:
        obj = fallback_obj
    else:
        system = (
            "You are a strict startup critic, investment committee reviewer, and risk analyst.\n"
            "You evaluate research, finance, and competitor outputs for decision quality.\n\n"

            "TOOL RULES:\n"
            "- You already received fact-check data in the prompt.\n"
            "- DO NOT call tools yourself.\n\n"

            "EVALUATION STANDARD:\n"
            "- Be skeptical and specific.\n"
            "- Penalize unsupported market-size claims.\n"
            "- Penalize unrealistic finance assumptions.\n"
            "- Penalize weak competitor validation.\n"
            "- Reward only evidence-backed, internally consistent analysis.\n\n"

            "CONFIDENCE SCORING:\n"
            "- 0.00-0.30 = severe flaws, unreliable decision.\n"
            "- 0.31-0.50 = major gaps remain.\n"
            "- 0.51-0.70 = usable but needs another refinement round.\n"
            "- 0.71-0.84 = strong but not final-grade.\n"
            "- 0.85-1.00 = investment-grade confidence.\n\n"

            "STRICT OUTPUT RULES:\n"
            "- Return ONLY valid JSON.\n"
            "- No markdown.\n"
            "- No explanation outside JSON.\n"
            "- Never return null for list fields.\n"
            "- Use [] or ['data unavailable'] for missing list values.\n\n"

            "FIELD REQUIREMENTS:\n"
            "- research_flaws: 3-5 strings.\n"
            "- finance_flaws: 1-5 strings.\n"
            "- competitor_flaws: 1-5 strings.\n"
            "- top_risks: exactly 3 strings.\n"
            "- confidence_score: float between 0.0 and 1.0.\n"
            "- reasoning: 3-5 sentence string.\n\n"

            "Return JSON matching this schema:\n"
            f"{_schema_hint(CriticOutput)}"
        )

        human = f"""
Business Idea:
{query}

=== RESEARCH ANALYSIS ===
{research}

=== FINANCE ANALYSIS ===
{finance}

=== COMPETITOR ANALYSIS ===
{competitor}

=== FACT-CHECK CONTEXT ===
{fact_check_context}

=== CORAL MEMORY ===
{past_notes or "None yet."}

=== CORAL ATTEMPTS ===
{past_att or "None yet."}

Task:
Evaluate whether the current outputs are strong enough for decision-making.

You must:
1. Identify 3-5 research flaws.
2. Identify finance flaws around CAC, churn, ROI, payback, burn, assumptions, and scalability.
3. Identify competitor flaws around realness, positioning, market gaps, and differentiation.
4. List exactly 3 top risks.
5. Assign confidence_score using the scoring rubric.
6. Explain reasoning in 3-5 sentences.

Return ONLY valid JSON.
"""

        # print(
        #     f"[critic] llm={type(base_llm).__name__} "
        #     "tools=MANUAL_FACT_CHECK_ONLY"
        # )

        try:
            response = await asyncio.wait_for(
                base_llm.ainvoke(_build_messages(system, human)),
                timeout=60,
            )

            raw_output = unwrap_ai_text(_safe_content(response))
            # print("[critic] raw_output preview:", raw_output[:500])

            parsed_obj, err = _parse_json_response(raw_output, CriticOutput)

            if parsed_obj:
                obj = parsed_obj
            else:
                # print(f"[critic] structured extraction failed, using fallback: {err}")
                obj = fallback_obj

        except Exception as exc:
            # print(f"[critic] LLM failed, using fallback: {exc}")
            obj = fallback_obj

    new_confidence = max(0.0, min(1.0, obj.confidence_score))
    structured_output = structured_to_markdown(obj)

    prev_best = state.get("best_score", 0.0)
    improved = new_confidence > prev_best
    evals_since = 0 if improved else state.get("evals_since_improvement", 0) + 1
    best_score = max(prev_best, new_confidence)

    # print(f"[critic] structured OK — confidence={new_confidence:.4f}")

    return {
        "critiques": [structured_output],
        "confidence_score": round(new_confidence, 4),
        "best_score": round(best_score, 4),
        "evals_since_improvement": evals_since,
        "round": state["round"] + 1,
        "critic_json": obj.model_dump(),
        "debate_transcript": [{
            "agent": "critic",
            "round": state["round"],
            "content": structured_output,
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

    # print(
    #     f"[heartbeat] round={round_num} confidence={confidence:.2f} "
    #     f"stagnation={stagnation} action={action} prompts={len(prompts)}"
    # )

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
    Production CEO node.
    Manual validation search + plain LLM call + deterministic fallback.
    """

    from coral.memory import CoralMemory
    from coral.grader import Grader

    session_id = state["session_id"]
    confidence = float(state.get("confidence_score", 0.5))

    # (f"[ceo] producing finprintal decision — confidence={confidence:.2f}")

    research = state.get("research_output", "[unavailable]")
    finance = state.get("finance_output", "[unavailable]")
    competitor = state.get("competitor_output", "[unavailable]")
    critiques = state.get("critiques", [])
    query = state.get("query", "")

    critique_summary = critiques[-1][:1000] if critiques else "No critiques."

    memory = CoralMemory(session_id=session_id)
    grader = Grader()

    try:
        leaderboard = memory.get_leaderboard(top_k=3)
        leaderboard_ctx = "\n".join(
            f"#{i + 1} score={a['score']:.2f}: {a['output'][:120]}..."
            for i, a in enumerate(leaderboard)
        ) if leaderboard else "No prior decisions."
    except Exception as exc:
        # (f"[ceo] leaderboard read failed: {exc}")
        leaderboard_ctx = "Leaderboard unavailable."

    rt = _get_runtime()
    tools = getattr(rt, "tools", []) or []

    # Prefer stronger model for final decision, but must be plain model.
    base_llm = (
        getattr(rt, "grok", None)
        or getattr(rt, "gemini", None)
        or getattr(rt, "hf", None)
    ) if rt else None

    validation_context = await _run_one_ceo_validation_search(tools, query)

    # Deterministic fallback recommendation from critic confidence
    if confidence >= 0.85:
        fallback_recommendation = "PROCEED"
        fallback_confidence = round(confidence * 100, 1)
    elif confidence >= 0.65:
        fallback_recommendation = "CONDITIONAL PROCEED"
        fallback_confidence = round(confidence * 100, 1)
    else:
        fallback_recommendation = "DO NOT PROCEED"
        fallback_confidence = round(confidence * 100, 1)

    fallback_obj = CEOOutput(
        recommendation=fallback_recommendation,
        confidence_percent=fallback_confidence,
        reasoning=(
            "The final decision is based on the critic confidence score and the combined research, finance, and competitor outputs. "
            "The opportunity requires stronger validation before major investment because several assumptions may still be unproven. "
            "Execution should proceed only if the team can validate demand, unit economics, and differentiation with real customers."
        ),
        key_success_conditions=[
            "Validate customer demand through paid pilots or signed letters of intent.",
            "Prove unit economics with controlled CAC, churn, gross margin, and payback targets.",
            "Demonstrate defensible differentiation against active competitors in the target segment.",
        ],
        risk_mitigations=[
            "Use staged rollout with milestone-based funding instead of full upfront expansion.",
            "Track CAC, retention, contribution margin, and payback monthly before scaling.",
            "Limit initial launch scope to one niche customer segment or geography.",
        ],
        critic_concerns_addressed=[
            "Addressed critic concerns by conditioning the decision on validation of research, finance, and competitor assumptions."
        ],
    )

    if base_llm is None:
        obj = fallback_obj
    else:
        system = (
            "You are the CEO and investment committee chair of a venture-backed AI company.\n"
            "You make the final go/no-go decision using research, finance, competitor analysis, critic feedback, and validation context.\n\n"

            "TOOL RULES:\n"
            "- You already received final validation search context in the prompt.\n"
            "- DO NOT call tools yourself.\n\n"

            "DECISION STANDARD:\n"
            "- Be commercially realistic and conservative.\n"
            "- Do not recommend PROCEED unless evidence, finance, and differentiation are strong.\n"
            "- If critic confidence is below 0.65, prefer DO NOT PROCEED or CONDITIONAL PROCEED.\n"
            "- If finance shows negative ROI/no payback, avoid PROCEED unless there is a strong staged-validation plan.\n"
            "- If competitor differentiation is weak, avoid PROCEED.\n\n"

            "RECOMMENDATION RULES:\n"
            "- recommendation must be exactly one of: PROCEED, DO NOT PROCEED, CONDITIONAL PROCEED.\n"
            "- confidence_percent must be between 0 and 100.\n"
            "- reasoning must be 3-5 sentences.\n"
            "- key_success_conditions must contain exactly 3 strings.\n"
            "- risk_mitigations must contain exactly 3 strings.\n"
            "- critic_concerns_addressed must contain 1-5 strings.\n\n"

            "NULL SAFETY RULE:\n"
            "- Never return null for any field.\n"
            "- Use [] or ['data unavailable'] for missing list fields.\n"
            "- Use 'data unavailable' for missing string fields.\n\n"

            "STRICT OUTPUT RULES:\n"
            "- Return ONLY valid JSON.\n"
            "- No markdown.\n"
            "- No explanation outside JSON.\n"
            "- Do not wrap JSON in an array.\n\n"

            "Return JSON matching this schema:\n"
            f"{_schema_hint(CEOOutput)}"
        )

        human = f"""
Business Idea:
{query}

=== RESEARCH ANALYSIS ===
{research[:1500]}

=== FINANCE ANALYSIS ===
{finance[:1500]}

=== COMPETITOR ANALYSIS ===
{competitor[:1500]}

=== CRITIC SUMMARY ===
{critique_summary}

=== FINAL VALIDATION CONTEXT ===
{validation_context}

=== TOP PAST DECISIONS FROM CORAL ===
{leaderboard_ctx}

=== CURRENT STATE ===
- Debate rounds completed: {state.get("round", 0)}
- Critic confidence score: {confidence:.2f}

Task:
Make the final investment/startup decision.

You must:
1. Synthesize research, finance, competitor analysis, and critic feedback.
2. Address critic concerns directly.
3. Choose PROCEED, DO NOT PROCEED, or CONDITIONAL PROCEED.
4. Set confidence_percent based on evidence quality and critic confidence.
5. Provide exactly 3 key success conditions.
6. Provide exactly 3 risk mitigations.

Return ONLY valid JSON.
"""

        # print(
        #     f"[ceo] llm={type(base_llm).__name__ if base_llm else 'STUB'} "
        #     "tools=MANUAL_VALIDATION_ONLY"
        # )

        try:
            response = await asyncio.wait_for(
                base_llm.ainvoke(_build_messages(system, human)),
                timeout=60,
            )

            raw_output = unwrap_ai_text(_safe_content(response))
            # print("[ceo] raw_output preview:", raw_output[:500])

            parsed_obj, err = _parse_json_response(raw_output, CEOOutput)

            if parsed_obj:
                obj = parsed_obj
            else:
                # print(f"[ceo] structured extraction failed, using fallback: {err}")
                obj = fallback_obj

        except Exception as exc:
            # print(f"[ceo] LLM failed, using fallback: {exc}")
            obj = fallback_obj

    structured_output = structured_to_markdown(obj)

    try:
        grade = grader.grade(
            decision=structured_output,
            critiques=critiques,
            research=research,
        )
    except Exception as exc:
        # print(f"[ceo] grading failed: {exc}")

        class _FallbackGrade:
            score = confidence
            feedback = "Fallback grade used because grader failed."
            breakdown = {}

        grade = _FallbackGrade()

    prev_best = state.get("best_score", 0.0)

    try:
        memory.write_attempt(
            agent_id="ceo",
            output=structured_output[:800],
            score=grade.score,
            feedback=grade.feedback,
            status="improved" if grade.score > prev_best else "baseline",
        )
    except Exception as exc:
        print(f"[ceo] memory write_attempt failed: {exc}")

    try:
        memory.write_note(
            agent_id="ceo",
            title=f"Decision round {state.get('round', 0)} — grader {grade.score:.2f}",
            content=(
                f"Query: {query}\n\n"
                f"Decision:\n{structured_output}\n\n"
                f"Grade: {grade.feedback}\n"
                f"Breakdown: {grade.breakdown}"
            ),
            subfolder="agent-ceo",
        )
    except Exception as exc:
        print(f"[ceo] memory write_note failed: {exc}")

    try:
        from memory.vector_store import add_text
        add_text(
            f"Decision for: {query}\n\n{structured_output}",
            metadata={
                "session_id": session_id,
                "round": state.get("round", 0),
                "confidence": confidence,
                "score": grade.score,
                "recommendation": obj.recommendation,
            },
        )
    except Exception as exc:
        print(f"[ceo] vector store write failed: {exc}")

    # print(
    #     f"[ceo] structured OK — recommendation={obj.recommendation} "
    #     f"confidence={obj.confidence_percent:.1f}%"
    # )

    return {
        "final_decision": structured_output,
        "ceo_json": obj.model_dump(),
        "reasoning_summary": (
            f"Completed {state.get('round', 0)} debate rounds. "
            f"Agent confidence: {confidence:.2f}. "
            f"Grader score: {grade.score:.2f}. "
            f"Recommendation: {obj.recommendation}."
        ),
        "debate_transcript": [{
            "agent": "ceo",
            "round": state.get("round", 0),
            "content": structured_output,
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
 
    # print(
    #     f"[meta_eval] session={session} rounds={rounds} "
    #     f"confidence={score:.2f} decision_length={len(final)}"
    # )
 
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
 
