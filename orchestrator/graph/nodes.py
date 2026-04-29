from __future__ import annotations
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
import os
import time
from typing import Any
from datetime import datetime

from langsmith import Client as LangSmithClient
from db.mongo import get_collection

from graph.state import AgentState
from graph.structured_outputs import (
    ResearchOutput,
    FinanceOutput,
    CompetitorOutput,
    CriticOutput,
    CEOOutput,
    MonthlyProjection,
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
    # print(f"[parser] calling PydanticOutputParser for {model_class.__name__}")

    if not raw or not isinstance(raw, str):
        return None, "Empty or non-string input"

    try:
        from langchain_core.output_parsers import PydanticOutputParser
    except Exception as exc:
        return None, f"PydanticOutputParser import failed: {exc}"

    parser = PydanticOutputParser(pydantic_object=model_class)
    text = unwrap_ai_text(raw).strip()

    last_err = "Unknown parse error"

    #  Try full response first
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

            #  Skip null, arrays, strings, numbers
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
    from agents.prompt_loader import load_prompt, load_stuck_prompt



    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        system = await load_stuck_prompt("research") or await load_prompt("research")
    else:
        system = await load_prompt("research")  # eval → base priority

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



    # Append dynamic context to whatever prompt was loaded
    schema = _schema_hint(ResearchOutput)

    system += f"""
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    📦 OUTPUT FORMAT
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {{
    {schema}
    }}
    """

    
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
    from agents.prompt_loader import load_prompt, load_stuck_prompt

    is_stuck = (state.get("evals_since_improvement") or 0) >= 5

    system = (
        await load_stuck_prompt("finance")
        if is_stuck
        else await load_prompt("finance")
    )

    query = state["query"]
    critiques = state.get("critiques", [])
    coral_skills = state.get("coral_skills", [])

    critique_context = "\n".join(critiques[-2:]) if critiques else "First round — no critiques yet."

    skills_context = "\n".join(
        f"- {s.get('name', '')}: {s.get('content', '')[:200]}"
        for s in coral_skills[:3]
        if isinstance(s, dict)
    ) if coral_skills else "No reusable skills available."

    # ─────────────────────────────────────────
    # 1. Assumptions
    # ─────────────────────────────────────────
    assumptions = {
        "initial_investment": float(state.get("initial_investment", 10000.0)),
        "starting_revenue": float(state.get("starting_revenue", 5000.0)),
        "monthly_growth_rate": float(state.get("monthly_growth_rate", 0.15)),
        "monthly_fixed_cost": float(state.get("monthly_fixed_cost", 12000.0)),
        "gross_margin": float(state.get("gross_margin", 0.75)),
        "estimated_cac": float(state.get("estimated_cac", 800.0)),
    }

    initial_investment = assumptions["initial_investment"]
    starting_revenue = assumptions["starting_revenue"]
    growth = assumptions["monthly_growth_rate"]
    fixed_cost = assumptions["monthly_fixed_cost"]
    margin = assumptions["gross_margin"]

    # ─────────────────────────────────────────
    # 2. Deterministic calculations
    # ─────────────────────────────────────────
    monthly_dicts = []
    cumulative = -initial_investment
    payback_months = None
    max_burn = 0.0

    for month in range(1, 13):
        revenue = round(starting_revenue * ((1 + growth) ** (month - 1)), 2)
        gross_profit = round(revenue * margin, 2)
        cost = round(fixed_cost, 2)
        net = round(gross_profit - cost, 2)

        cumulative += net

        if net < 0:
            max_burn = max(max_burn, abs(net))

        if payback_months is None and cumulative >= 0:
            payback_months = float(month)

        monthly_dicts.append({
            "month": month,
            "revenue": revenue,
            "cost": cost,
            "net": net,
        })

    # totals
    total_revenue = round(sum(m["revenue"] for m in monthly_dicts), 2)
    operating_cost = round(sum(m["cost"] for m in monthly_dicts), 2)
    total_cost = round(operating_cost + initial_investment, 2)
    net_profit = round(sum(m["net"] for m in monthly_dicts) - initial_investment, 2)
    roi_percent = round((net_profit / total_cost) * 100, 2) if total_cost else 0.0

    # ✅ convert to Pydantic models (FIX)
    monthly_models = [
        MonthlyProjection.model_validate(m)
        for m in monthly_dicts
    ]

    base_finance_json = {
        "initial_investment": initial_investment,
        "monthly_projections": monthly_models,
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "payback_months": payback_months,
    }

    # ─────────────────────────────────────────
    # 3. Recommendation
    # ─────────────────────────────────────────
    if net_profit > 0 and roi_percent >= 20:
        rec = "GO — strong profitability and ROI"
    elif net_profit > 0:
        rec = "CONDITIONAL GO — profitable but optimize further"
    else:
        rec = "NO-GO — not financially viable"

    # ─────────────────────────────────────────
    # 4. Fallback object (ALREADY CORRECT TYPE)
    # ─────────────────────────────────────────
    fallback_obj = FinanceOutput(
        **base_finance_json,
        financial_risks=[
            f"Payback risk: {payback_months}",
            f"Burn risk: {max_burn}",
            "CAC not fully modeled",
        ],
        recommendation=rec,
        critique_responses=[
            "Used deterministic calculations",
            "Ensured correct ROI formula",
            "Included risk analysis",
        ],
    )

    # ─────────────────────────────────────────
    # 5. LLM (optional)
    # ─────────────────────────────────────────
    obj = fallback_obj
    rt = _get_runtime()
    llm = getattr(rt, "hf", None) if rt else None

    if llm:
        try:
            response = await llm.ainvoke(_build_messages(system, query))
            raw = unwrap_ai_text(_safe_content(response))

            parsed, err = _parse_json_response(raw, FinanceOutput)

            if parsed:
                obj = parsed

                # ✅ FORCE correct types again
                obj.monthly_projections = monthly_models
                obj.initial_investment = initial_investment
                obj.total_revenue = total_revenue
                obj.total_cost = total_cost
                obj.net_profit = net_profit
                obj.roi_percent = roi_percent
                obj.payback_months = payback_months

        except Exception:
            obj = fallback_obj

    # ─────────────────────────────────────────
    # 6. Output
    # ─────────────────────────────────────────
    return {
        "finance_output": structured_to_markdown(obj),
        "finance_json": obj.model_dump(),  # ✅ NO WARNINGS NOW
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — Production Competitor Agent
# ─────────────────────────────────────────────────────────────────────────────

async def competitor_node(state: AgentState) -> dict:
    from agents.prompt_loader import load_prompt, load_stuck_prompt
    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        system = await load_stuck_prompt("competitor") or await load_prompt("competitor")
    else:
        system = await load_prompt("competitor")  # eval → base priority
   

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


     # Append dynamic context to whatever prompt was loaded
    schema = _schema_hint(CompetitorOutput)

    system += f"""

    {{
    {schema}
    }}
    """
    

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
    from agents.prompt_loader import load_prompt, load_stuck_prompt
    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        system = await load_stuck_prompt("critic") or await load_prompt("critic")
    else:
        system = await load_prompt("critic")  # eval → base priority
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

        # Append dynamic context to whatever prompt was loaded
        schema = _schema_hint(CriticOutput)

        system += f"""

        {{
        {schema}
        }}
        """

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
    import asyncio
    from coral.memory import CoralMemory
    from coral.heartbeat import HeartbeatRunner
    from db.mongo import get_collection

    session_id = state["session_id"]
    round_num  = state["round"]
    confidence = state["confidence_score"]
    threshold  = state["confidence_threshold"]
    max_rounds = state["max_rounds"]
    stagnation = state["evals_since_improvement"]
    improved   = stagnation == 0

    memory    = CoralMemory(session_id=session_id)
    heartbeat = HeartbeatRunner(memory)

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

    # ── Routing ───────────────────────────────────────────────────────────────
    if confidence >= threshold:
        action = "exit"
    elif round_num >= max_rounds:
        action = "exit"
    elif stagnation >= 5:
        action = "pivot"
    else:
        action = "refine"

    # ── On pivot: activate existing stuck prompts in MongoDB ──────────────────
    if action == "pivot":
        AGENTS = ["research", "finance", "competitor", "critic", "ceo"]

        async def _activate_stuck_prompt(agent_id: str) -> None:
            try:
                col = await get_collection("prompts")

                # Deactivate ALL prompts for this agent first
                await col.update_many(
                    {"agentId": agent_id},
                    {"$set": {"active": False}},
                )

                # Activate the stuck prompt only (latest version)
                result = await col.find_one_and_update(
                    {"agentId": agent_id, "promptType": "stuck"},
                    {"$set": {"active": True}},
                    sort=[("version", -1)],
                )
                if result:
                    print(f"[heartbeat] stuck prompt activated — {agent_id} v{result.get('version', '?')}")
                else:
                    print(f"[heartbeat] no stuck prompt found for {agent_id} — staying on current")
            except Exception as exc:
                print(f"[heartbeat] stuck activation failed for {agent_id}: {exc}")

        await asyncio.gather(*[_activate_stuck_prompt(aid) for aid in AGENTS])

    # print(
    #     f"[heartbeat] round={round_num} confidence={confidence:.2f} "
    #     f"stagnation={stagnation} action={action} prompts={len(prompts)}"
    # )

    return {
        "heartbeat_action":  action,
        "heartbeat_prompts": prompts,
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
    from agents.prompt_loader import load_prompt, load_stuck_prompt
    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        system = await load_stuck_prompt("ceo") or await load_prompt("ceo")
    else:
        system = await load_prompt("ceo")  # eval → base priority

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

        # Append dynamic context to whatever prompt was loaded
        schema = _schema_hint(CEOOutput)

        system += f"""

         {{
        {schema}
        }}
         """


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
# NODE 8 — Meta-Eval inside this all logic of this node is added
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
 
META_EVAL_SCORE_THRESHOLD = 0.72   # matches Session.threshold default (0.85 is CEO; 0.72 for meta-eval quality)
LANGSMITH_PROJECT         = os.getenv("LANGCHAIN_PROJECT", "autonomous-decision-lab")
 
# Agent IDs whose prompts may be optimized
OPTIMIZABLE_AGENTS = ["research", "finance", "competitor", "critic", "ceo"]
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 1. LangSmith fetch
# ─────────────────────────────────────────────────────────────────────────────
 
def _fetch_langsmith_metrics(session_id: str) -> dict[str, Any]:
    try:
        ls = LangSmithClient()
        runs = list(ls.list_runs(
            project_name=LANGSMITH_PROJECT,
            run_name=session_id,
            limit=1,
        ))
        if not runs:
            return {}
        run = runs[0]
        latency_ms = (
            int((run.end_time - run.start_time).total_seconds() * 1000)
            if run.end_time and run.start_time else 0
        )
        return {
            "latency_ms":        latency_ms,
            "total_tokens":      getattr(run, "total_tokens", 0) or 0,
            "prompt_tokens":     getattr(run, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(run, "completion_tokens", 0) or 0,
            "run_id":            str(run.id),
        }
    except Exception as exc:
        print(f"[meta_eval] langsmith fetch failed: {exc}")
        return {}
 
# ─────────────────────────────────────────────────────────────────────────────
# 2. Evaluation Agent  — reasoning quality score
# ─────────────────────────────────────────────────────────────────────────────

 
async def _run_evaluation_agent(
    state: AgentState,
    final_decision: str,
    reasoning_summary: str,
    critiques: list,
    confidence_score: float,
) -> dict[str, Any]:
    """
    Calls the LLM to score the final decision.
    Returns score dict with overall_score key.
    """
    from agents.prompt_loader import load_prompt, load_stuck_prompt
    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        _EVAL_SYSTEM = await load_stuck_prompt("meta_eval") or await load_prompt("meta_eval")
    else:
        _EVAL_SYSTEM = await load_prompt("meta_eval")  # eval → base priority
    rt = _get_runtime()
    llm = (
        getattr(rt, "hf", None)
        or getattr(rt, "gemini", None)
        or getattr(rt, "grok", None)
    ) if rt else None
 
    fallback = {
        "reasoning_quality": confidence_score,
        "consistency":       confidence_score,
        "accuracy":          confidence_score,
        "completeness":      confidence_score,
        "overall_score":     confidence_score,
        "feedback":          "Fallback score — LLM unavailable.",
    }
 
    if llm is None:
        return fallback
 
    critique_sample = (critiques[-1][:500] if critiques else "None")
 
    human = f"""
Final Decision (truncated to 1200 chars):
{final_decision[:1200]}
 
Reasoning Summary:
{reasoning_summary[:400]}
 
Last Critique:
{critique_sample}
 
Critic Confidence Score: {confidence_score:.2f}
 
Evaluate the decision and return JSON only.
"""
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(_build_messages(_EVAL_SYSTEM, human)),
            timeout=40,
        )
        raw = unwrap_ai_text(_safe_content(response))
        import json, re
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        # Ensure overall_score exists
        if "overall_score" not in parsed:
            vals = [v for k, v in parsed.items() if isinstance(v, float)]
            parsed["overall_score"] = round(sum(vals) / len(vals), 4) if vals else confidence_score
        return parsed
    except Exception as exc:
        print(f"[meta_eval] evaluation agent failed: {exc}")
        return fallback
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 3. Prompt Optimization Agent
# ─────────────────────────────────────────────────────────────────────────────
 
async def _run_prompt_optimization_agent(
    state: AgentState,
    agent_id: str,
    current_prompt: str,
    eval_feedback: str,
    eval_scores: dict,
    query: str,
) -> str | None:
    """
    Rewrites the system prompt for agent_id.
    Returns the new prompt string, or None on failure.
    """
    from agents.prompt_loader import load_prompt, load_stuck_prompt
    # Detect stuck — use stuck prompt if available
    is_stuck = (state.get("evals_since_improvement") or 0) >= 5
    
    if is_stuck:
        _PROMPT_OPT_SYSTEM = await load_stuck_prompt("prompt_optimizer") or await load_prompt("prompt_optimizer")
    else:
        _PROMPT_OPT_SYSTEM = await load_prompt("prompt_optimizer")  # eval → base priority
    rt = _get_runtime()
    llm = (
        getattr(rt, "grok", None)
        or getattr(rt, "gemini", None)
        or getattr(rt, "hf", None)
    ) if rt else None
 
    if llm is None:
        print(f"[prompt_opt] LLM unavailable — skipping optimization for {agent_id}")
        return None
 
    score_summary = ", ".join(f"{k}={v:.2f}" for k, v in eval_scores.items() if k != "feedback")
 
    human = f"""
Agent ID: {agent_id}
 
Original Query that triggered low score:
{query[:400]}
 
Evaluation Scores: {score_summary}
Evaluation Feedback: {eval_feedback}
 
Current System Prompt:
{current_prompt[:3000]}
 
Rewrite the system prompt to address the evaluation feedback.
Return ONLY the new prompt text.
"""
    try:
        response = await asyncio.wait_for(
            llm.ainvoke(_build_messages(_PROMPT_OPT_SYSTEM, human)),
            timeout=60,
        )
        new_prompt = unwrap_ai_text(_safe_content(response)).strip()
        return new_prompt if len(new_prompt) > 50 else None
    except Exception as exc:
        print(f"[prompt_opt] failed for {agent_id}: {exc}")
        return None
 
 
async def _save_optimized_prompt_to_mongo(
    agent_id: str,
    new_prompt: str,
    eval_score: float,
) -> None:
    """
    Mirrors the Prompt schema from models/index.js:
      agentId, version (auto-incremented), content, score, active
    Deactivates all previous versions for this agent, then inserts v+1.
    """
    try:
        col = await get_collection("prompts")
 
        # Find current max version for this agent
        latest = await col.find_one(
            {"agentId": agent_id},
            sort=[("version", -1)],
        )
        next_version = (latest["version"] + 1) if latest else 1
 
        # Deactivate all old versions
        await col.update_many(
            {"agentId": agent_id},
            {"$set": {"active": False}},
        )
 
        # Insert new version
        await col.insert_one({
            "agentId":   agent_id,
            "promptType": "eval",
            "version":   next_version,
            "content":   new_prompt,
            "score":     eval_score,
            "active":    True,
            "createdAt": time.time(),
            "updatedAt": time.time(),
        })
        print(f"[prompt_opt] saved {agent_id} v{next_version} score={eval_score:.2f}")
    except Exception as exc:
        print(f"[prompt_opt] mongo save failed for {agent_id}: {exc}")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 4. Store result to MongoDB  (Session + Leaderboard)
# ─────────────────────────────────────────────────────────────────────────────
 
async def _store_result(state: AgentState, eval_scores: dict, ls_metrics: dict) -> None:
    """
    Updates the Session document and writes a Leaderboard entry.
    Mirrors Session and Leaderboard schemas from models/index.js.
    """
    session_id    = state.get("session_id") or "unknown"
    final         = state.get("final_decision") or ""
    overall_score = eval_scores.get("overall_score", 0.0)
 
    try:
        sessions = await get_collection("sessions")
        await sessions.update_one(
            {"sessionId": session_id},
            {"$set": {
                "status":          "done",
                "confidenceScore": state.get("confidence_score", 0.0),
                "bestScore":       max(state.get("best_score", 0.0), overall_score),
                "finalDecision":   final[:2000],
                "completedAt":     time.time(),
                "updatedAt":       time.time(),
                # store LangSmith metrics as extra fields
                "latencyMs":       ls_metrics.get("latency_ms", 0),
                "totalTokens":     ls_metrics.get("total_tokens", 0),
            }},
            upsert=False,
        )
    except Exception as exc:
        print(f"[meta_eval] session update failed: {exc}")
 
    try:
        lb = await get_collection("leaderboards")
        await lb.insert_one({
            "sessionId": session_id,
            "query":     state.get("query", ""),
            "score":     overall_score,
            "decision":  final[:500],
            "rounds":    state.get("round", 0),
            "agentId":   "meta_eval",
            "output":    {
                "eval_scores": eval_scores,
                "ls_metrics":  ls_metrics,
            },
            "feedback":  eval_scores.get("feedback", ""),
            "createdAt": time.time(),
            "updatedAt": time.time(),
        })
    except Exception as exc:
        print(f"[meta_eval] leaderboard insert failed: {exc}")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# NODE 8 — Main entry point
# ─────────────────────────────────────────────────────────────────────────────
 
async def meta_eval_node(state: AgentState) -> dict:
    from coral.memory import CoralMemory
    from coral.grader import Grader
    """
    Post-decision quality evaluation node.

    Pipeline:
      1. LangSmith fetch  — latency + tokens (fallback: local timer)
      2. Evaluation Agent — reasoning quality score (4 dimensions)
      3. Threshold check
         ├─ below  → Prompt Optimization Agent → save new prompt v+1 to MongoDB
         └─ above  → store result only
      4. Update Session + Leaderboard in MongoDB
      5. Return safe state defaults (no reducer ever receives None)
    """

    # ── Safe coercions ───────────────────────────────────────────────────────
    final             = state.get("final_decision")      or ""
    confidence_score  = float(state.get("confidence_score") or 0.0)
    rounds            = state.get("round")               or 0
    session_id        = state.get("session_id")          or "unknown"
    query             = state.get("query")               or ""
    critiques         = state.get("critiques")           or []
    reasoning_summary = state.get("reasoning_summary")   or ""

    # ── Step 1: LangSmith metrics (local timer fallback) ─────────────────────
    _node_start = time.time()

    ls_metrics = _fetch_langsmith_metrics(session_id)

    if not ls_metrics:
        ls_metrics = {
            "latency_ms":        int((time.time() - _node_start) * 1000),
            "total_tokens":      0,
            "prompt_tokens":     0,
            "completion_tokens": 0,
            "run_id":            session_id,
        }

    # print(
    #     f"[meta_eval] session={session_id} rounds={rounds} "
    #     f"confidence={confidence_score:.2f} "
    #     f"latency={ls_metrics.get('latency_ms', 'N/A')}ms "
    #     f"tokens={ls_metrics.get('total_tokens', 'N/A')}"
    # )

    # ── Step 2: Evaluation Agent ─────────────────────────────────────────────
    eval_scores = await _run_evaluation_agent(
        state             = state,
        final_decision    = final,
        reasoning_summary = reasoning_summary,
        critiques         = critiques,
        confidence_score  = confidence_score,
    )
    overall_score = float(eval_scores.get("overall_score", confidence_score))
    eval_feedback = eval_scores.get("feedback", "")

    # print(
    #     f"[meta_eval] eval overall={overall_score:.2f} "
    #     f"threshold={META_EVAL_SCORE_THRESHOLD} feedback='{eval_feedback}'"
    # )

    # ── Step 3: Threshold branch ─────────────────────────────────────────────
    if overall_score < META_EVAL_SCORE_THRESHOLD:
        # print(f"[meta_eval] score below threshold — running prompt optimization")

        async def _optimize_one(agent_id: str) -> None:
            try:
                col = await get_collection("prompts")
                doc = await col.find_one(
                    {"agentId": agent_id, "active": True},
                    sort=[("version", -1)],
                )
                current_prompt = doc["content"] if doc else f"You are the {agent_id} agent."
            except Exception:
                current_prompt = f"You are the {agent_id} agent."

            new_prompt = await _run_prompt_optimization_agent(
                state          = state,
                agent_id       = agent_id,
                current_prompt = current_prompt,
                eval_feedback  = eval_feedback,
                eval_scores    = eval_scores,
                query          = query,
            )
            if new_prompt:
                await _save_optimized_prompt_to_mongo(agent_id, new_prompt, overall_score)

        await asyncio.gather(*[_optimize_one(aid) for aid in OPTIMIZABLE_AGENTS])
    else:
        print(f"[meta_eval] score above threshold — storing result only")

    # ── Step 4: Store result ─────────────────────────────────────────────────
    await _store_result(state, eval_scores, ls_metrics)

    # ── Step 5: Safe state return ────────────────────────────────────────────
    existing_transcript = state.get("debate_transcript") or []



    session_id = state["session_id"]
    memory = CoralMemory(session_id=session_id)
    grader = Grader()

    final_decision = state.get("final_decision", "")
    critiques = state.get("critiques", [])
    research = state.get("research_output", "")

    # ── Evaluate decision ─────────────────────────────────────────
    grade = grader.grade(
        decision=final_decision,
        critiques=critiques,
        research=research,
    )

    score = grade.score
    # print(f"[meta_eval] score={score:.2f}")

    # ── ✅ WRITE SKILL ONLY IF GOOD RESULT ─────────────────────────
    if score >= 0.75:
        try:
            skill_name = f"decision-strategy-{session_id[:6]}"

            skill_description = (
                "High-performing decision strategy derived from successful agent collaboration. "
                "This approach integrates research validation, financial reasoning, competitor analysis, "
                "and critic feedback to produce strong decisions."
            )

            skill_script = f"""
def apply_strategy(input_data):
    # Derived from successful run
    return {{
        "query": "{state.get("query", "")}",
        "confidence": {state.get("confidence_score", 0)},
        "score": {score},
        "recommendation": "Reuse this structured reasoning approach for similar startup decisions."
    }}
"""

            memory.write_skill(
                name=skill_name,
                description=skill_description,
                script=skill_script,
                creator="meta_eval",
                results=f"Score={score}, session={session_id}"
            )

            # print(f"[meta_eval]  skill created: {skill_name}")

        except Exception as exc:
            print("")

    else:
        print("")


 


    return {
        "final_decision":    final or "",
        "reasoning_summary": reasoning_summary or "",
        "coral_notes":       state.get("coral_notes")    or [],
        "coral_attempts":    state.get("coral_attempts") or [],
        "coral_skills":      state.get("coral_skills")   or [],
        "critiques":         state.get("critiques")      or [],
        "debate_transcript": existing_transcript + [{
            "agent":     "meta_eval",
            "round":     rounds,
            "content": (
                f"Eval Score: {overall_score:.2f} | "
                f"Feedback: {eval_feedback} | "
                f"Latency: {ls_metrics.get('latency_ms', 'N/A')}ms | "
                f"Tokens: {ls_metrics.get('total_tokens', 'N/A')}"
            ),
            "timestamp": time.time(),
        }],
    }