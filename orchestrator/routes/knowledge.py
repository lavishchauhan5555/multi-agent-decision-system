"""
routes/knowledge.py
───────────────────
Read-only endpoints that expose CORAL shared persistent memory
to the React frontend via the Node.js backend.

  GET /knowledge/notes        → list all agent notes
  GET /knowledge/skills       → list all reusable skills
  GET /knowledge/leaderboard  → top-k attempts by score
"""

import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/knowledge")

CORAL_ROOT = Path(".coral/public")


@router.get("/notes")
async def list_notes():
    notes_dir = CORAL_ROOT / "notes"
    if not notes_dir.exists():
        return {"notes": []}

    notes = []
    for f in sorted(notes_dir.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        notes.append({
            "path":    str(f.relative_to(CORAL_ROOT)),
            "content": f.read_text(),
            "size":    f.stat().st_size,
        })
    return {"notes": notes[:50]}   # cap at 50


@router.get("/skills")
async def list_skills():
    skills_dir = CORAL_ROOT / "skills"
    if not skills_dir.exists():
        return {"skills": []}

    skills = []
    for skill_folder in sorted(skills_dir.iterdir()):
        skill_md = skill_folder / "SKILL.md"
        if skill_md.exists():
            skills.append({
                "name":    skill_folder.name,
                "content": skill_md.read_text(),
            })
    return {"skills": skills}


@router.get("/leaderboard")
async def get_leaderboard(top_k: int = 10):
    attempts_dir = CORAL_ROOT / "attempts"
    if not attempts_dir.exists():
        return {"attempts": []}

    attempts = []
    for f in attempts_dir.glob("*.json"):
        try:
            attempts.append(json.loads(f.read_text()))
        except Exception:
            pass

    sorted_attempts = sorted(attempts, key=lambda x: x.get("score", 0), reverse=True)
    return {"attempts": sorted_attempts[:top_k]}