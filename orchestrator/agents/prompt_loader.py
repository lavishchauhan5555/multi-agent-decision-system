# agents/prompt_loader.py
from db.mongo import get_collection

async def load_prompt(agent_id: str) -> str:
    """
    Priority: eval (active) → base → hardcoded fallback
    """
    col = await get_collection("prompts")
    
    # 1. Try active eval prompt first (latest optimized)
    doc = await col.find_one(
        {"agentId": agent_id, "promptType": "eval", "active": True},
        sort=[("version", -1)],
    )
    if doc:
        return doc["content"]
    
    # 2. Fall back to base prompt
    doc = await col.find_one(
        {"agentId": agent_id, "promptType": "base", "active": True},
    )
    if doc:
        return doc["content"]
    
    # 3. Hardcoded fallback (should never reach here)
    return f"You are the {agent_id} agent. Be thorough and accurate."


async def load_stuck_prompt(agent_id: str) -> str | None:
    col = await get_collection("prompts")
    doc = await col.find_one(
        {"agentId": agent_id, "promptType": "stuck", "active": True},
        sort=[("version", -1)],
    )
    return doc["content"] if doc else None