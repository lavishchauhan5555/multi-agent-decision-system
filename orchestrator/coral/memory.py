"""
coral/memory.py
───────────────
CoralMemory — Shared persistent memory hub.

Compatible with orchestrator/graph/nodes.py — every agent node
calls these methods after completing its work:

    memory.write_attempt(agent_id, output, score, feedback)
    memory.write_note(agent_id, title, content, subfolder)
    memory.write_skill(name, description, script, creator)
    memory.get_leaderboard(top_k)
    memory.read_all_notes()
    memory.read_skills()
    memory.increment_eval_count()
    memory.get_eval_count()

Injected into LangGraph nodes via functools.partial in graph/builder.py.
"""

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import shutil


# ── Root path — relative to orchestrator/ working directory ─────────────────
CORAL_ROOT = Path(".coral/public")


class CoralMemory:
    """
    Shared persistent memory hub for all CORAL agents.
    Thread-safe for read operations.
    Write operations use unique filenames (hash-keyed) so concurrent
    agents never collide.
    """

    def __init__(self, session_id: str, clean_old: bool = False):
        self.session_id = session_id

        if clean_old:
            self.clear_old_memory_keep_latest()
        else:
            self._ensure_dirs()

    # ── Directory bootstrap ──────────────────────────────────────────────────
    def _ensure_dirs(self):
        dirs = [
            CORAL_ROOT / "attempts",
            CORAL_ROOT / "notes" / "synthesis",
            CORAL_ROOT / "notes" / "never-worked",
            CORAL_ROOT / "skills",
            CORAL_ROOT / "heartbeat",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ── Attempts ─────────────────────────────────────────────────────────────
    def write_attempt(
        self,
        agent_id: str,
        output: str,
        score: float,
        feedback: str,
        status: str = "baseline",
        parent_hash: Optional[str] = None,
    ) -> str:
        """
        Write one evaluation attempt to .coral/public/attempts/{hash}.json
        Returns the commit hash (8-char SHA1).

        status options: "improved" | "regressed" | "baseline" | "crashed"
        """
        content = f"{agent_id}{output}{datetime.now(timezone.utc).isoformat()}"
        commit_hash = hashlib.sha1(content.encode()).hexdigest()[:8]

        record = {
            "commit_hash":  commit_hash,
            "agent_id":     agent_id,
            "session_id":   self.session_id,
            "output":       output,
            "score":        round(score, 4),
            "feedback":     feedback,
            "status":       status,
            "parent_hash":  parent_hash,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        }

        path = CORAL_ROOT / "attempts" / f"{commit_hash}.json"
        path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
           

        # Also increment global eval counter
        self.increment_eval_count()

        return commit_hash
    


   

    def clear_old_memory_keep_latest(self):
        """
        Keep latest previous run memory.
        Delete older attempts, notes, skills, heartbeat.
        Current new run will then add fresh memory.
        """

        self._ensure_dirs()

        attempts_dir = CORAL_ROOT / "attempts"

        # Find latest previous session_id from attempts
        latest_session_id = None
        latest_timestamp = ""

        for f in attempts_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                ts = data.get("timestamp", "")
                if ts > latest_timestamp:
                    latest_timestamp = ts
                    latest_session_id = data.get("session_id")
            except Exception:
                try:
                    f.unlink()
                except OSError:
                    pass

        # If no previous memory exists, nothing to clean
        if not latest_session_id:
            return

        # Delete attempts not from latest session
        for f in attempts_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                if data.get("session_id") != latest_session_id:
                    f.unlink()
            except Exception:
                try:
                    f.unlink()
                except OSError:
                    pass

        # Delete notes not from latest session
        notes_dir = CORAL_ROOT / "notes"
        if notes_dir.exists():
            for f in notes_dir.rglob("*.md"):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if f"session_id: {latest_session_id}" not in text:
                        f.unlink()
                except Exception:
                    try:
                        f.unlink()
                    except OSError:
                        pass

        # Delete all skills except latest session skills
        skills_dir = CORAL_ROOT / "skills"
        if skills_dir.exists():
            for skill_folder in skills_dir.iterdir():
                try:
                    skill_md = skill_folder / "SKILL.md"
                    if not skill_md.exists():
                        shutil.rmtree(skill_folder)
                        continue

                    text = skill_md.read_text(encoding="utf-8", errors="replace")
                    if f"session_id: {latest_session_id}" not in text:
                        shutil.rmtree(skill_folder)
                except Exception:
                    try:
                        shutil.rmtree(skill_folder)
                    except OSError:
                        pass

        # Heartbeat usually has no session_id, so safest is delete it
        heartbeat_dir = CORAL_ROOT / "heartbeat"
        if heartbeat_dir.exists():
            shutil.rmtree(heartbeat_dir)
            heartbeat_dir.mkdir(parents=True, exist_ok=True)

        self._ensure_dirs()
    
    










    def get_leaderboard(self, top_k: int = 10) -> list[dict]:
        """
        Return top-k attempts sorted by score descending.
        Called by CEO agent before making final decision.
        """
        attempts = []

        for f in (CORAL_ROOT / "attempts").glob("*.json"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                attempts.append(json.loads(text))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                print(f"[coral] skipping bad attempt file {f}: {exc}")

        return sorted(
            attempts,
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:top_k]

    def get_attempt(self, commit_hash: str) -> Optional[dict]:
        """Fetch a single attempt by hash. Used by Critic for comparison."""
        path = CORAL_ROOT / "attempts" / f"{commit_hash}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def get_session_attempts(self) -> list[dict]:
        """Return all attempts for this session only."""
        all_attempts = self.get_leaderboard(top_k=9999)
        return [a for a in all_attempts if a.get("session_id") == self.session_id]

    # ── Notes ─────────────────────────────────────────────────────────────────
    def write_note(
        self,
        agent_id: str,
        title: str,
        content: str,
        subfolder: str = "",
    ) -> Path:
        """
        Write a Markdown note to .coral/public/notes/{subfolder}/{slug}.md
        Called by reflect heartbeat after every evaluation.

        subfolder examples:
            ""               → notes/
            "synthesis"      → notes/synthesis/
            "never-worked"   → notes/never-worked/  (Critic writes here)
            "agent-1"        → notes/agent-1/
        """
        folder = CORAL_ROOT / "notes"
        if subfolder:
            folder = folder / subfolder
        folder.mkdir(parents=True, exist_ok=True)

        # URL-safe slug from title
        slug = "".join(
            c if c.isalnum() or c == "-" else "-"
            for c in title.lower().replace(" ", "-")
        )[:50]

        # Add timestamp to avoid collisions between agents
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        filename = f"{slug}-{ts}.md"

        frontmatter = (
            f"---\n"
            f"creator: {agent_id}\n"
            f"session_id: {self.session_id}\n"
            f"created: {datetime.now(timezone.utc).isoformat()}\n"
            f"---\n\n"
        )
        path = folder / filename
        path.write_text(frontmatter + f"# {title}\n\n{content}")
        return path

    def read_all_notes(self, subfolder: str = "") -> list[dict]:
        """
        Return all notes, newest first.
        Agents call this at the start of each round to load prior knowledge.

        subfolder="" → all notes recursively
        subfolder="never-worked" → only failed-approach notes (used by Critic)
        """
        root = CORAL_ROOT / "notes"
        if subfolder:
            root = root / subfolder

        notes = []
        if not root.exists():
            return notes

        for f in sorted(root.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                notes.append({
                    "path":    str(f.relative_to(CORAL_ROOT / "notes")),
                    "content": f.read_text(),
                    "mtime":   f.stat().st_mtime,
                })
            except OSError:
                pass

        return notes[:100]   # cap at 100 to protect context window

    def update_connections_map(self, content: str):
        """Overwrite connections.md — called by consolidate heartbeat."""
        path = CORAL_ROOT / "notes" / "connections.md"
        path.write_text(f"# Cross-agent connection map\n\nUpdated: {datetime.now(timezone.utc).isoformat()}\n\n{content}")

    def update_open_questions(self, content: str):
        """Overwrite open-questions.md — called by consolidate heartbeat."""
        path = CORAL_ROOT / "notes" / "open-questions.md"
        path.write_text(f"# Open questions and gaps\n\nUpdated: {datetime.now(timezone.utc).isoformat()}\n\n{content}")

    # ── Skills ────────────────────────────────────────────────────────────────
    def write_skill(
        self,
        name: str,
        description: str,
        script: str,
        creator: str,
        results: Optional[str] = None,
    ) -> Path:
        """
        Write a reusable skill to .coral/public/skills/{name}/
        Called by consolidate heartbeat when a validated technique is promoted.

        name        → skill folder name (e.g. "roi-calculator")
        description → what it does and when to use it
        script      → executable Python code
        creator     → agent_id that created it
        results     → optional benchmark results
        """
        folder = CORAL_ROOT / "skills" / name
        folder.mkdir(parents=True, exist_ok=True)
        scripts_dir = folder / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        skill_md = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"creator: {creator}\n"
            f"session_id: {self.session_id}\n"
            f"created: {datetime.now(timezone.utc).isoformat()}\n"
            f"---\n\n"
            f"# {name}\n\n"
            f"## What it does\n{description}\n\n"
        )
        if results:
            skill_md += f"## Results\n{results}\n\n"
        skill_md += "## When to use it\nSee description above.\n"

        (folder / "SKILL.md").write_text(skill_md)
        (scripts_dir / "run_skill.py").write_text(script)
        return folder

    def read_skills(self) -> list[dict]:
        """
        Return all available skills.
        Called by Finance and Research agents at the start of each round.
        """
        skills_dir = CORAL_ROOT / "skills"
        skills = []
        if not skills_dir.exists():
            return skills

        for skill_folder in sorted(skills_dir.iterdir()):
            skill_md = skill_folder / "SKILL.md"
            if skill_md.exists():
                scripts = list((skill_folder / "scripts").glob("*.py")) if (skill_folder / "scripts").exists() else []
                skills.append({
                    "name":    skill_folder.name,
                    "content": skill_md.read_text(),
                    "scripts": [s.name for s in scripts],
                })
        return skills

    # ── Eval counter ──────────────────────────────────────────────────────────
    def increment_eval_count(self) -> int:
        """Thread-safe global eval counter used by HeartbeatRunner."""
        counter_path = CORAL_ROOT / "eval_count"
        current = 0
        if counter_path.exists():
            try:
                current = int(counter_path.read_text().strip())
            except ValueError:
                current = 0
        new_count = current + 1
        counter_path.write_text(str(new_count))
        return new_count

    def get_eval_count(self) -> int:
        """Return current global eval count."""
        counter_path = CORAL_ROOT / "eval_count"
        if not counter_path.exists():
            return 0
        try:
            return int(counter_path.read_text().strip())
        except ValueError:
            return 0

    # ── Snapshot (for AgentManager) ──────────────────────────────────────────
    def snapshot(self) -> dict:
        """
        Return a summary of current memory state.
        Used by AgentManager for health monitoring and dashboard.
        """
        return {
            "session_id":    self.session_id,
            "eval_count":    self.get_eval_count(),
            "attempts":      len(list((CORAL_ROOT / "attempts").glob("*.json"))),
            "notes":         len(list((CORAL_ROOT / "notes").rglob("*.md"))),
            "skills":        len(list((CORAL_ROOT / "skills").iterdir())) if (CORAL_ROOT / "skills").exists() else 0,
            "leaderboard":   self.get_leaderboard(top_k=3),
        }