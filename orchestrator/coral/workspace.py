"""
coral/workspace.py
──────────────────
WorkspaceManager — creates isolated per-agent workspaces.

Windows-compatible: uses directory junctions (mklink /J) first,
falls back to shutil.copytree if junctions fail (no admin rights).

Each agent gets:
  .coral/agents/agent-{N}/
    .claude/notes   -> junction/copy -> .coral/public/notes/
    .claude/skills  -> junction/copy -> .coral/public/skills/
    .coral_dir      -> breadcrumb file
    CORAL.md        -> auto-generated agent instruction file
    workspace/      -> agent private working directory
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

CORAL_ROOT  = Path(".coral")
PUBLIC_ROOT = CORAL_ROOT / "public"
AGENTS_ROOT = CORAL_ROOT / "agents"

IS_WINDOWS = sys.platform == "win32"

CORAL_MD_TEMPLATE = """# Task: {task_name}

{task_description}

## How this works

You are {agent_id}, one of {total_agents} agents working on this task.
Each agent has its own private workspace but you all share .coral/public/
where attempts, notes, and skills are visible to everyone.

## Orientation (do this before writing any code)

1. Check the leaderboard — which attempts scored highest?
2. Read notes in .claude/notes/ — what have other agents learned?
3. Check skills in .claude/skills/ — what reusable tools are available?
4. Check notes/never-worked/ — what approaches have already failed?

## Workflow loop

Plan -> Implement -> Evaluate -> Write note -> Repeat

After EVERY evaluation:
- Write a note to .claude/notes/{agent_id}/ capturing what you learned
- If you discover something reusable, write a skill to .claude/skills/
- If you plateau for 5 rounds, try a fundamentally different approach

## Ground rules

- You are fully autonomous. Do not ask for permission.
- Never modify .coral/ directly - use the memory API only.
- Eval early and often. One idea per eval.

You are {agent_id}.
""".strip()


class WorkspaceManager:
    """
    Creates and manages isolated per-agent workspaces.
    Fully compatible with Windows, macOS, and Linux.

    Link strategy (tried in order):
      1. Windows directory junction  (mklink /J, no admin needed)
      2. Unix symlink                (Linux / macOS)
      3. Plain directory copy        (ultimate fallback)
    """

    def __init__(self):
        self._ensure_root_dirs()

    def _ensure_root_dirs(self):
        dirs = [
            PUBLIC_ROOT / "attempts",
            PUBLIC_ROOT / "notes" / "synthesis",
            PUBLIC_ROOT / "notes" / "never-worked",
            PUBLIC_ROOT / "skills",
            PUBLIC_ROOT / "heartbeat",
            AGENTS_ROOT,
            CORAL_ROOT / "private" / "eval",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        eval_count = PUBLIC_ROOT / "eval_count"
        if not eval_count.exists():
            eval_count.write_text("0")

        sessions = PUBLIC_ROOT / "sessions.json"
        if not sessions.exists():
            sessions.write_text("{}")

    # ── Cross-platform link helper ────────────────────────────────────────────
    def _safe_link(self, target: Path, link: Path):
        """
        Create a link/junction/copy from link -> target.
        Never raises — always falls back gracefully.
        """
        if link.exists() or link.is_symlink():
            return

        target_abs = target.resolve()
        link.parent.mkdir(parents=True, exist_ok=True)

        # 1. Windows junction (no admin privilege required)
        if IS_WINDOWS:
            try:
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J",
                     str(link.resolve()), str(target_abs)],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    return
            except Exception:
                pass
            # Junction failed -> copy
            self._mirror_copy(target_abs, link)
            return

        # 2. Unix symlink
        try:
            os.symlink(target_abs, link)
            return
        except OSError:
            pass

        # 3. Copy fallback
        self._mirror_copy(target_abs, link)

    def _mirror_copy(self, target: Path, link: Path):
        """Copy target directory contents into link directory."""
        if link.exists():
            return
        if target.exists():
            shutil.copytree(str(target), str(link), dirs_exist_ok=True)
        else:
            link.mkdir(parents=True, exist_ok=True)

    def sync_workspace(self, agent_id: str):
        """
        Refresh agent .claude/notes and .claude/skills from shared public folder.
        Call at the start of each agent node on Windows when using copy-fallback.
        """
        agent_dir  = AGENTS_ROOT / agent_id
        claude_dir = agent_dir / ".claude"

        for folder in ("notes", "skills"):
            src  = PUBLIC_ROOT / folder
            dest = claude_dir / folder
            if src.exists() and dest.exists():
                for src_file in src.rglob("*"):
                    if src_file.is_file():
                        rel      = src_file.relative_to(src)
                        dst_file = dest / rel
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        if not dst_file.exists() or \
                           src_file.stat().st_mtime > dst_file.stat().st_mtime:
                            shutil.copy2(str(src_file), str(dst_file))

    # ── Workspace creation ────────────────────────────────────────────────────
    def create_agent_workspace(
        self,
        agent_id: str,
        task_name: str = "Autonomous Decision Lab",
        task_description: str = "Analyze the query and produce a decision.",
        total_agents: int = 3,
    ) -> Path:
        """Create isolated workspace for one agent. Returns workspace path."""
        agent_dir     = AGENTS_ROOT / agent_id
        claude_dir    = agent_dir / ".claude"
        workspace_dir = agent_dir / "workspace"

        agent_dir.mkdir(parents=True, exist_ok=True)
        claude_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Link or copy shared folders
        self._safe_link((PUBLIC_ROOT / "notes").resolve(),  claude_dir / "notes")
        self._safe_link((PUBLIC_ROOT / "skills").resolve(), claude_dir / "skills")

        # Breadcrumb
        (agent_dir / ".coral_dir").write_text(str(CORAL_ROOT.resolve()))

        # CORAL.md instruction file
        (agent_dir / "CORAL.md").write_text(
            CORAL_MD_TEMPLATE.format(
                task_name=task_name,
                task_description=task_description,
                agent_id=agent_id,
                total_agents=total_agents,
            )
        )

        return agent_dir

    def create_all_workspaces(
        self,
        agent_ids: list,
        task_name: str = "Autonomous Decision Lab",
        task_description: str = "Analyze the query and produce a decision.",
    ) -> dict:
        """Create workspaces for all agents. Returns {agent_id: path}."""
        total = len(agent_ids)
        return {
            aid: self.create_agent_workspace(
                agent_id=aid,
                task_name=task_name,
                task_description=task_description,
                total_agents=total,
            )
            for aid in agent_ids
        }

    def get_workspace_path(self, agent_id: str) -> Path:
        return AGENTS_ROOT / agent_id / "workspace"

    def workspace_exists(self, agent_id: str) -> bool:
        return (AGENTS_ROOT / agent_id).exists()

    def list_workspaces(self) -> list:
        if not AGENTS_ROOT.exists():
            return []
        return [d.name for d in AGENTS_ROOT.iterdir() if d.is_dir()]

    def teardown_workspace(self, agent_id: str):
        """Remove an agent workspace."""
        agent_dir = AGENTS_ROOT / agent_id
        if agent_dir.exists():
            shutil.rmtree(str(agent_dir))