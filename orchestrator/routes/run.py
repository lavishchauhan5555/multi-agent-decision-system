"""
routes/run.py
─────────────
FastAPI endpoints:
  POST /run                   start a new agent run
  GET  /stream/{session_id}   SSE event stream
  GET  /status/{session_id}   quick status check

Stream lifecycle:
  1. POST /run       → spawns background task, returns session_id + stream_url
  2. GET  /stream/…  → client opens SSE connection, reads events until DONE/ERROR
  3. On __done__ or __error__ the generator yields the final event, then returns.
     Returning from an async generator closes the HTTP response body, which
     signals EOF to the client — no extra sentinel frame needed.
  4. Session is removed from active_sessions immediately after graph finishes
     (not after a 5-minute sleep).  A short grace window (10 s) is kept so
     any in-flight /status poll still sees the session as "completed".
"""

import asyncio
import json
import uuid
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from graph.builder import graph
from graph.state import AgentState
from coral.memory import CoralMemory

router = APIRouter()

# ── Session registry ──────────────────────────────────────────────────────────
# session_id → {"queue": asyncio.Queue, "status": "running"|"done"|"error"}
active_sessions: dict[str, dict] = {}

# How long (seconds) to keep a finished session in the registry so that
# any /status poll that arrives just after completion still gets a reply.
_SESSION_TTL_AFTER_DONE = 10


# ── Request schema ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    query:      str
    max_rounds: Optional[int]   = 2
    threshold:  Optional[float] = 0.85


# ─────────────────────────────────────────────────────────────────────────────
# POST /run
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run")
async def start_run(payload: RunRequest, background: BackgroundTasks):
    session_id = str(uuid.uuid4())
    memory = CoralMemory(session_id=session_id, clean_old=True)

    q: asyncio.Queue = asyncio.Queue()
    active_sessions[session_id] = {"queue": q, "status": "running"}

    initial_state: AgentState = {
    "query":                   payload.query,
    "session_id":              session_id,
    "round":                   0,
    "max_rounds":              payload.max_rounds,
    "confidence_score":        0.0,
    "confidence_threshold":    payload.threshold,
    "evals_since_improvement": 0,
    "best_score":              0.0,
 
    # ── Always str, never None ────────────────────────────────────────────
    "research_output":         "",
    "finance_output":          "",
    "competitor_output":       "",
    "final_decision":          "",
    "reasoning_summary":       "",
    "heartbeat_action":        "refine",
 
    # ── Always list, never None ───────────────────────────────────────────
    "competitors_list":        [],
    "critiques":               [],
    "debate_transcript":       [],
    "coral_notes":             [],
    "coral_attempts":          [],
    "coral_skills":            [],
    "heartbeat_prompts":       [],
 
    # ── Cache — cached_result is the only Optional ─────────────────────────
    "cached_result":           None,
    "cache_score":             0.0,
}

    async def execute():
        session = active_sessions.get(session_id)
        if session is None:
            return

        try:
            async for event in graph.astream(initial_state):
                node_name   = list(event.keys())[0]
                node_output = event[node_name]

                await q.put({
                    "session_id": session_id,
                    "node":       node_name,
                    "round":      node_output.get("round", 0),
                    "timestamp":  time.time(),
                    "data":       node_output,
                })

            # ── Graph finished cleanly ────────────────────────────────────
            session["status"] = "done"
            await q.put({
                "session_id": session_id,
                "node":       "__done__",
                "timestamp":  time.time(),
                "data":       {},
            })

        except Exception as exc:
            # ── Graph raised an unhandled exception ───────────────────────
            session["status"] = "error"
            await q.put({
                "session_id": session_id,
                "node":       "__error__",
                "timestamp":  time.time(),
                "data":       {"error": str(exc)},
            })

        finally:
            # ── Short TTL so in-flight /status polls still resolve ─────────
            # Remove immediately; sleep only if session still registered.
            await asyncio.sleep(_SESSION_TTL_AFTER_DONE)
            active_sessions.pop(session_id, None)

    background.add_task(execute)

    return {
        "session_id": session_id,
        "status":     "started",
        "stream_url": f"/stream/{session_id}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /stream/{session_id}  — SSE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stream/{session_id}")
async def stream_run(session_id: str):
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    q: asyncio.Queue = session["queue"]

    async def event_generator():
        KEEPALIVE_INTERVAL = 5.0     # check every 5 sec
        MAX_IDLE_TIME = 30.0         # break after 30 sec no data

        last_event_time = time.time()

        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_INTERVAL)
                
                last_event_time = time.time()  # ✅ reset timer

                yield f"data: {json.dumps(event, default=str)}\n\n"

                if event.get("node") in ("__done__", "__error__"):
                    break

            except asyncio.TimeoutError:
                if time.time() - last_event_time > MAX_IDLE_TIME:
                    print(f"[stream] idle timeout reached for {session_id}")

                    session["status"] = "error"

                    yield f"data: {json.dumps({
                        'session_id': session_id,
                        'node': '__timeout__',
                        'timestamp': time.time(),
                        'data': {
                            'error': 'Stream closed because graph sent no events for 30 seconds'
                        }
                    }, default=str)}\n\n"

                    break

                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering
            "Connection":        "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /status/{session_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status/{session_id}")
async def get_status(session_id: str):
    session = active_sessions.get(session_id)
    if not session:
        return {
            "session_id": session_id,
            "active":     False,
            "status":     "expired_or_not_found",
            "queue_size": 0,
        }
    return {
        "session_id": session_id,
        "active":     session["status"] == "running",
        "status":     session["status"],           # "running" | "done" | "error"
        "queue_size": session["queue"].qsize(),
    }