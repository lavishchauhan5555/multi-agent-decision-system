from graph.tools import get_mcp_tools
from graph.models import build_agent
from graph.runtime import RUNTIME


async def init_agent():
    print("── Initializing runtime ──")
    client, tools = await get_mcp_tools()
    _, llm_hf, llm_genai, llm_grok = await build_agent(tools)

    RUNTIME.client = client
    RUNTIME.tools  = tools
    RUNTIME.hf     = llm_hf
    RUNTIME.gemini = llm_genai
    RUNTIME.grok   = llm_grok

    return RUNTIME