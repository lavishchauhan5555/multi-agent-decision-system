"""
main.py
───────
FastAPI application entry point for the Orchestrator layer.

Start with:
    uvicorn main:app --reload --port 8000

Architecture:
    React (5173) → Node.js (3001) → FastAPI (8000) → LangGraph → Agents
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routes.run import router as run_router
from routes.knowledge import router as knowledge_router
from graph.init import init_agent
from memory.vector_store import cleanup_old_documents



# ─────────────────────────────────────────────────────────────────────────────
# Load environment variables
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()


# ─────────────────────────────────────────────────────────────────────────────
# Ensure CORAL folder structure exists
# ─────────────────────────────────────────────────────────────────────────────
def ensure_coral_dirs():
    dirs = [
        ".coral/public/attempts",
        ".coral/public/notes/synthesis",
        ".coral/public/skills",
        ".coral/private/eval",
    ]

    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    print("[startup] CORAL directory structure ready")





# ─────────────────────────────────────────────────────────────────────────────
# FastAPI lifespan (startup + shutdown)
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n[startup] Starting Orchestrator...")

    # Create CORAL directories
    ensure_coral_dirs()

    # Initialize runtime / LLM models
    try:
        print("[startup] Initializing agent runtime...")
        await init_agent()
        print("[startup] Agent runtime initialized successfully")
    except Exception as e:
        print(f"[startup] Runtime initialization failed: {e}")


    cleanup_old_documents(days=10)    

    # Startup diagnostics
    print(
        f"[startup] GOOGLE_API_KEY={'set' if os.getenv('GOOGLE_API_KEY') else 'MISSING'}"
    )

    print(
        f"[startup] LANGCHAIN_API_KEY={'set' if os.getenv('LANGCHAIN_API_KEY') else 'MISSING'}"
    )

    print("[startup] Orchestrator ready\n")

    yield

    print("\n[shutdown] Orchestrator shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Autonomous Decision Lab — Orchestrator",
    description="CORAL-enhanced multi-agent LangGraph backend",
    version="2.0.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://multi-agent-decision-system.onrender.com",  # Node.js backend
        "https://multi-agent-decision-system.onrender.com",  # React Vite frontend
        "http://localhost:3000",  # CRA frontend
        "*",                      # dev only
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(run_router)
app.include_router(knowledge_router)


# ─────────────────────────────────────────────────────────────────────────────
# Health Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "orchestrator",
        "version": "2.0.0",
        "google_api_key": "set" if os.getenv("GOOGLE_API_KEY") else "missing",
        "langsmith": "enabled" if os.getenv("LANGCHAIN_API_KEY") else "disabled",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Root Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "Autonomous Decision Lab Orchestrator",
        "phase": "2 — FastAPI + LangGraph",
        "status": "running",
        "endpoints": [
            "POST /run",
            "GET /stream/{session_id}",
            "GET /status/{session_id}",
            "GET /knowledge/notes",
            "GET /knowledge/skills",
            "GET /knowledge/leaderboard",
            "GET /health",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Optional local run
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
