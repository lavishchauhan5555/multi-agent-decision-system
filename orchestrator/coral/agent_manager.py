"""
coral/agent_manager.py
──────────────────────
AgentManager — manages the full lifecycle of CORAL agents.

Responsibilities:
  - start_all()       create workspaces + launch agent tasks
  - monitor_loop()    poll for new attempts, fire heartbeats, detect stagnation
  - stop_all()        graceful shutdown
  - resume()          restore from sessions.json

Compatible with graph/builder.py — AgentManager is instantiated once per
/run request and passed into node functions via functools.partial.

In Phase 2 the nodes are stubs — AgentManager wires the memory + heartbeat
objects that Phase 3 agents will actually call.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Callable

from coral.memory import CoralMemory
from coral.heartbeat import HeartbeatRunner, HeartbeatConfig
from coral.workspace import WorkspaceManager

CORAL_ROOT  = Path(".coral")
PUBLIC_ROOT = CORAL_ROOT / "public"


# ── Agent handle ─────────────────────────────────────────────────────────────

class AgentHandle:
    """
    Lightweight container for a running agent's state.
    In Phase 3 this wraps the asyncio.Task for each LangChain agent.
    """
    def __init__(self, agent_id: str, task: Optional[asyncio.Task] = None):
        self.agent_id   = agent_id
        self.task       = task
        self.alive      = True
        self.start_time = time.time()
        self.last_eval  = time.time()

    def is_done(self) -> bool:
        if self.task is None:
            return False
        return self.task.done()

    def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
        self.alive = False


# ── AgentManager ─────────────────────────────────────────────────────────────

class AgentManager:
    """
    Orchestrates all CORAL agents for one decision run.

    Usage in graph/builder.py (Phase 3):
        manager = AgentManager(session_id="abc-123", agent_ids=["research","finance","competitor"])
        await manager.start_all(query="Should I start a SaaS?")
        # ... graph runs ...
        await manager.stop_all()

    In Phase 2 (current):
        manager = AgentManager(session_id=session_id)
        # Injects memory + heartbeat into node functions via partial
        research_node_with_memory = partial(research_node, manager=manager)
    """

    def __init__(
        self,
        session_id: str,
        agent_ids: Optional[list[str]] = None,
        heartbeat_config: Optional[HeartbeatConfig] = None,
    ):
        self.session_id = session_id
        self.agent_ids  = agent_ids or ["research", "finance", "competitor", "critic", "ceo"]

        # Core CORAL components
        self.memory    = CoralMemory(session_id)
        self.heartbeat = HeartbeatRunner(self.memory, heartbeat_config)
        self.workspace = WorkspaceManager()

        # Agent tracking
        self._handles:       dict[str, AgentHandle] = {}
        self._event_queue:   asyncio.Queue = asyncio.Queue()
        self._running:       bool = False
        self._monitor_task:  Optional[asyncio.Task] = None

        # Callbacks
        self._on_event: Optional[Callable] = None   # SSE push hook

    # ── Setup ────────────────────────────────────────────────────────────────
    def setup_workspaces(self, task_name: str = "Autonomous Decision Lab", task_description: str = ""):
        """
        Create isolated workspaces for all agents.
        Call this before start_all().
        """
        self.workspace.create_all_workspaces(
            agent_ids=self.agent_ids,
            task_name=task_name,
            task_description=task_description,
        )
        

    # ── Start ────────────────────────────────────────────────────────────────
    async def start_all(self, query: str = ""):
        """
        Start all agents and the background monitor loop.
        In Phase 3: spawns asyncio.Tasks for each LangChain agent.
        In Phase 2: just initialises handles so graph nodes can reference them.
        """
        self._running = True
        self.setup_workspaces(task_description=query)

        for agent_id in self.agent_ids:
            handle = AgentHandle(agent_id=agent_id)
            self._handles[agent_id] = handle
            

        # Start background monitor
        self._monitor_task = asyncio.create_task(self._monitor_loop())
       

    # ── Monitor loop ─────────────────────────────────────────────────────────
    async def _monitor_loop(self):
        """
        Runs every 5 seconds.
        - Checks for new attempt files written since last poll
        - Fires heartbeat prompts when thresholds are hit
        - Detects dead agents and restarts them
        - Pushes status events to SSE queue
        """
        last_attempt_count = 0
        last_check_time = time.time()

        while self._running:
            try:
                await asyncio.sleep(5)

                # Count new attempts since last check
                attempts_dir = PUBLIC_ROOT / "attempts"
                current_count = len(list(attempts_dir.glob("*.json"))) if attempts_dir.exists() else 0

                if current_count > last_attempt_count:
                    new_evals = current_count - last_attempt_count
                    
                    last_attempt_count = current_count

                    # Fire heartbeat for each agent that is active
                    for agent_id, handle in self._handles.items():
                        if not handle.alive:
                            continue
                        prompts = self.heartbeat.record_eval(
                            agent_id=agent_id,
                            improved=(self.memory.get_eval_count() % 3 != 0),  # simulate
                        )
                        if prompts:
                            
                            await self._event_queue.put({
                                "type":     "heartbeat",
                                "agent_id": agent_id,
                                "prompts":  prompts,
                                "timestamp": time.time(),
                            })

                # Detect stagnation across all agents
                hb_status = self.heartbeat.get_status()
                # for agent_id, stag in hb_status["stagnation_counts"].items():
                #     if stag >= 5:
                #         print(f"[Monitor] Agent {agent_id} stagnant for {stag} evals — pivot recommended")

                # Push a status snapshot every 30s
                if time.time() - last_check_time > 30:
                    await self._event_queue.put({
                        "type":      "status",
                        "snapshot":  self.memory.snapshot(),
                        "heartbeat": hb_status,
                        "timestamp": time.time(),
                    })
                    last_check_time = time.time()

            except asyncio.CancelledError:
                break


    # ── Event queue ───────────────────────────────────────────────────────────
    async def get_next_event(self, timeout: float = 5.0) -> Optional[dict]:
        """
        Pop the next event from the monitor queue.
        Called by the SSE route to push live updates to React.
        """
        try:
            return await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    # ── Stop ─────────────────────────────────────────────────────────────────
    async def stop_all(self):
        """Graceful shutdown — cancel all agent tasks and monitor."""
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        for handle in self._handles.values():
            handle.cancel()

        # Save session IDs for resume
        sessions_path = PUBLIC_ROOT / "sessions.json"
        try:
            sessions = json.loads(sessions_path.read_text()) if sessions_path.exists() else {}
            sessions[self.session_id] = {
                "agent_ids":  self.agent_ids,
                "stopped_at": time.time(),
            }
            sessions_path.write_text(json.dumps(sessions, indent=2))
        except Exception as exc:
            print(f"[AgentManager] Failed to save sessions: {exc}")

        # print(f"[AgentManager] All agents stopped — session={self.session_id}")

    # ── Resume ────────────────────────────────────────────────────────────────
    async def resume(self, session_id: str):
        """
        Resume a previous run from sessions.json.
        Validates saved sessions and restarts with prior context.
        """
        sessions_path = PUBLIC_ROOT / "sessions.json"
        if not sessions_path.exists():
            # print(f"[AgentManager] No sessions.json found — starting fresh")
            return

        sessions = json.loads(sessions_path.read_text())
        if session_id not in sessions:
            # print(f"[AgentManager] Session {session_id} not found — starting fresh")
            return

        saved = sessions[session_id]
        self.agent_ids = saved.get("agent_ids", self.agent_ids)
        # print(f"[AgentManager] Resuming session {session_id} with agents: {self.agent_ids}")

        # Load prior context from memory
        snapshot = self.memory.snapshot()
        # print(f"[AgentManager] Prior context: {snapshot['attempts']} attempts, {snapshot['notes']} notes")

    # ── Status ────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        """Return full status for dashboard and GET /health endpoint."""
        return {
            "session_id":   self.session_id,
            "running":      self._running,
            "agents":       {
                aid: {
                    "alive":      h.alive,
                    "uptime_s":   round(time.time() - h.start_time, 1),
                }
                for aid, h in self._handles.items()
            },
            "memory":    self.memory.snapshot(),
            "heartbeat": self.heartbeat.get_status(),
        }