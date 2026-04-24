"""
coral/heartbeat.py
──────────────────
HeartbeatRunner — CORAL's three heartbeat types.

Called inside heartbeat_node() in graph/nodes.py after every Critic evaluation.
Returns a list of prompt strings to inject into the next agent round.

Three heartbeat types (from CORAL paper):
  REFLECT     — every eval        → agent writes a note capturing what it learned
  CONSOLIDATE — every 10 evals    → agent synthesizes notes + promotes skills
  PIVOT       — 5 non-improving   → agent abandons current approach, tries something new

Compatible with CoralMemory — HeartbeatRunner reads eval_count from memory.
"""

from dataclasses import dataclass, field
from typing import Optional
from coral.memory import CoralMemory


# ── Heartbeat prompt templates (injected into agent context) ─────────────────

REFLECT_PROMPT = """
=== HEARTBEAT: REFLECT ===
Pause and reflect on your most recent evaluation before continuing.

1. Review your last attempt — what specific change caused improvement or regression?
2. What surprised you? Surprises reveal gaps in your mental model.
3. What is ONE concrete thing to try next, and what do you predict will happen?
4. Write a note to .coral/public/notes/{agent_id}/ capturing these insights.

Be specific — avoid vague statements like "try a different approach."
Example good note title: "Batch-size-2 reduces latency but increases variance"
""".strip()

CONSOLIDATE_PROMPT = """
=== HEARTBEAT: CONSOLIDATE ===
Pause your current work. Synthesize the shared knowledge base.

Required steps:
1. Read ALL notes in .coral/public/notes/
2. For any topic with 3+ notes, write a synthesis note in notes/synthesis/
   — state the top conclusion upfront, cite specific attempts as evidence
3. Update notes/connections.md with cross-agent patterns you notice
4. Update notes/open-questions.md with unresolved contradictions
5. Promote any well-validated technique to .coral/public/skills/
   — only promote if you have at least 2 successful attempts as evidence

Goal: make the shared knowledge base MORE useful for all agents.
""".strip()

PIVOT_PROMPT = """
=== HEARTBEAT: PIVOT ===
You have not improved in {n} consecutive evaluations. You are stuck.
Do NOT continue tweaking the same approach.

Required steps:
1. Run: review the leaderboard — what is the core idea behind the top 3 attempts?
2. Inspect attempts from OTHER agents — what approach are they using?
3. Choose a FUNDAMENTALLY different direction:
   — different algorithm family, different problem formulation, different representation
4. Write a note to notes/never-worked/ documenting what you abandoned and why
5. Start from the best-scoring attempt as your base, not from your current state

Remember: the goal is not to find the best tweak.
It is to find a better mountain to climb entirely.
""".strip()


# ── Heartbeat config dataclass ────────────────────────────────────────────────

@dataclass
class HeartbeatConfig:
    reflect_every:     int = 1    # fire reflect every N evals (per agent)
    consolidate_every: int = 10   # fire consolidate every N evals (global)
    pivot_after:       int = 5    # fire pivot after N non-improving evals (per agent)


# ── HeartbeatRunner ───────────────────────────────────────────────────────────

class HeartbeatRunner:
    """
    Monitors eval counts and stagnation, fires heartbeat prompts at the
    right moments.

    Usage inside heartbeat_node() in graph/nodes.py:
        runner = HeartbeatRunner(memory)
        prompts = runner.record_eval(
            agent_id="research",
            improved=(new_confidence > old_confidence),
        )
        # prompts is a list of strings — inject into next agent system prompt
    """

    def __init__(
        self,
        memory: CoralMemory,
        config: Optional[HeartbeatConfig] = None,
    ):
        self.memory = memory
        self.config = config or HeartbeatConfig()

        # Per-agent tracking
        self._agent_eval_counts:    dict[str, int] = {}
        self._stagnation_counts:    dict[str, int] = {}
        self._pivot_cooldowns:      dict[str, int] = {}   # prevents re-firing immediately

    def record_eval(self, agent_id: str, improved: bool) -> list[str]:
        """
        Call this after every agent evaluation.

        Args:
            agent_id:  which agent just finished (e.g. "research", "critic")
            improved:  True if this eval beat the previous best score

        Returns:
            List of heartbeat prompt strings to inject into the next round.
            Empty list if no heartbeat fires this round.
        """
        # Update per-agent eval count
        self._agent_eval_counts[agent_id] = self._agent_eval_counts.get(agent_id, 0) + 1
        agent_count = self._agent_eval_counts[agent_id]

        # Update stagnation counter
        if improved:
            self._stagnation_counts[agent_id] = 0
            self._pivot_cooldowns[agent_id] = 0
        else:
            self._stagnation_counts[agent_id] = self._stagnation_counts.get(agent_id, 0) + 1

        stagnation = self._stagnation_counts.get(agent_id, 0)

        # Read global eval count from filesystem (shared across agents)
        global_count = self.memory.get_eval_count()

        prompts: list[str] = []

        # ── 1. REFLECT — every eval ──────────────────────────────────────────
        if agent_count % self.config.reflect_every == 0:
            prompts.append(
                REFLECT_PROMPT.replace("{agent_id}", agent_id)
            )

        # ── 2. CONSOLIDATE — every 10 global evals ───────────────────────────
        if global_count > 0 and global_count % self.config.consolidate_every == 0:
            prompts.append(CONSOLIDATE_PROMPT)

        # ── 3. PIVOT — 5+ non-improving evals, with cooldown ─────────────────
        cooldown = self._pivot_cooldowns.get(agent_id, 0)
        if (
            stagnation >= self.config.pivot_after
            and stagnation % self.config.pivot_after == 0
            and cooldown == 0
        ):
            prompts.append(
                PIVOT_PROMPT.replace("{n}", str(stagnation))
            )
            # Set cooldown: don't re-fire pivot for another pivot_after evals
            self._pivot_cooldowns[agent_id] = self.config.pivot_after
        elif cooldown > 0:
            self._pivot_cooldowns[agent_id] = cooldown - 1

        return prompts

    def get_status(self) -> dict:
        """
        Return current heartbeat state for AgentManager health monitoring.
        """
        return {
            "agent_eval_counts": dict(self._agent_eval_counts),
            "stagnation_counts": dict(self._stagnation_counts),
            "global_eval_count": self.memory.get_eval_count(),
            "config": {
                "reflect_every":     self.config.reflect_every,
                "consolidate_every": self.config.consolidate_every,
                "pivot_after":       self.config.pivot_after,
            },
        }

    def should_pivot(self, agent_id: str) -> bool:
        """
        Quick check — used by route_debate_loop in graph/edges.py
        to decide whether to inject a pivot before re-running agents.
        """
        return self._stagnation_counts.get(agent_id, 0) >= self.config.pivot_after