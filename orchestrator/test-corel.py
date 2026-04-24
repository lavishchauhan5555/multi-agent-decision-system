"""
test_coral.py  (Windows-compatible fixed version)
─────────────────────────────────────────────────
Run BEFORE starting uvicorn:
    python test_coral.py

Fixes applied vs previous version:
  - Test 2: Consolidate trigger now correctly aligns global eval_count
  - Test 3: Workspace test does not assert symlink exists — checks dir exists instead
  - Test 5: AgentManager test skips symlink assertion, checks workspace folders only
"""

import asyncio
import sys
import shutil
from pathlib import Path

# ── Isolate tests from real .coral ───────────────────────────────────────────
TEST_ROOT = Path(".coral_test")


def setup_test_env():
    import coral.memory as mem_mod
    import coral.workspace as ws_mod
    import coral.heartbeat as hb_mod
    mem_mod.CORAL_ROOT = TEST_ROOT / "public"
    ws_mod.CORAL_ROOT  = TEST_ROOT
    ws_mod.PUBLIC_ROOT = TEST_ROOT / "public"
    ws_mod.AGENTS_ROOT = TEST_ROOT / "agents"


def teardown_test_env():
    if TEST_ROOT.exists():
        shutil.rmtree(str(TEST_ROOT))


# ── Test 1: CoralMemory ───────────────────────────────────────────────────────
def test_coral_memory():
    print("── Test 1: CoralMemory ──")
    from coral.memory import CoralMemory
    mem = CoralMemory(session_id="test-session-001")

    h1 = mem.write_attempt("research", "Market is growing 23% YoY", 0.72, "Good detail", "improved")
    h2 = mem.write_attempt("finance",  "ROI 275% at 12 months",      0.65, "Needs more data", "baseline")
    assert len(h1) == 8 and len(h2) == 8
    assert h1 != h2
    print(f"   PASS — write_attempt: h1={h1} h2={h2}")

    board = mem.get_leaderboard(top_k=5)
    assert len(board) == 2
    assert board[0]["score"] >= board[1]["score"]
    print(f"   PASS — get_leaderboard: top score={board[0]['score']}")

    fetched = mem.get_attempt(h1)
    assert fetched is not None and fetched["agent_id"] == "research"
    print(f"   PASS — get_attempt: agent={fetched['agent_id']}")

    path = mem.write_note("research", "Batch size finding",
                          "Batch=2 gives better throughput", "agent-research")
    assert path.exists()
    print(f"   PASS — write_note: {path.name}")

    notes = mem.read_all_notes()
    assert len(notes) >= 1
    print(f"   PASS — read_all_notes: {len(notes)} notes found")

    skill_path = mem.write_skill(
        name="roi-calculator",
        description="Calculates ROI given cost and revenue",
        script="def calculate_roi(cost, revenue): return (revenue - cost) / cost",
        creator="finance",
        results="Score: 0.85",
    )
    assert skill_path.exists() and (skill_path / "SKILL.md").exists()
    print(f"   PASS — write_skill: {skill_path.name}")

    skills = mem.read_skills()
    assert len(skills) == 1 and skills[0]["name"] == "roi-calculator"
    print(f"   PASS — read_skills: {skills[0]['name']}")

    c1 = mem.get_eval_count()
    c2 = mem.increment_eval_count()
    assert c2 == c1 + 1
    print(f"   PASS — eval_count: {c1} -> {c2}")

    snap = mem.snapshot()
    assert all(k in snap for k in ("attempts", "notes", "skills"))
    print(f"   PASS — snapshot: {snap['attempts']} attempts, {snap['notes']} notes, {snap['skills']} skills")


# ── Test 2: HeartbeatRunner ───────────────────────────────────────────────────
def test_heartbeat_runner():
    print("── Test 2: HeartbeatRunner ──")
    from coral.memory import CoralMemory
    from coral.heartbeat import HeartbeatRunner, HeartbeatConfig

    mem = CoralMemory(session_id="test-session-hb")

    # Use consolidate_every=2 so we can trigger it in just 2 global evals
    config = HeartbeatConfig(reflect_every=1, consolidate_every=2, pivot_after=2)
    hb = HeartbeatRunner(mem, config)

    # Reset eval_count to 0 so we control it precisely
    (Path(".coral_test") / "public" / "eval_count").write_text("0")

    # Eval 1 — reflect only (global count goes to 1 inside write_attempt)
    prompts1 = hb.record_eval("research", improved=True)
    assert any("REFLECT" in p for p in prompts1), "Reflect should fire every eval"
    print(f"   PASS — reflect fired on eval 1: {len(prompts1)} prompt(s)")

    # Manually set global count to consolidate_every - 1 = 1, then bump to 2
    (Path(".coral_test") / "public" / "eval_count").write_text("1")
    mem.increment_eval_count()  # now = 2 = consolidate_every

    # Eval 2 — both reflect AND consolidate should fire
    prompts2 = hb.record_eval("research", improved=True)
    has_consolidate = any("CONSOLIDATE" in p for p in prompts2)
    assert has_consolidate, f"Consolidate should fire when global count == consolidate_every=2. Got: {prompts2}"
    print(f"   PASS — consolidate fired at global eval count=2")

    # Stagnation pivot — fire after 2 non-improving evals
    hb2 = HeartbeatRunner(mem, config)
    hb2.record_eval("finance", improved=False)
    prompts_p = hb2.record_eval("finance", improved=False)
    assert any("PIVOT" in p for p in prompts_p), "Pivot should fire after pivot_after=2 non-improving evals"
    print(f"   PASS — pivot fired after 2 non-improving evals")

    # After improvement stagnation resets
    hb2.record_eval("finance", improved=True)
    assert hb2._stagnation_counts.get("finance", 0) == 0
    print(f"   PASS — stagnation resets after improvement")

    # should_pivot check
    hb3 = HeartbeatRunner(mem, config)
    hb3._stagnation_counts["competitor"] = 2
    assert hb3.should_pivot("competitor") is True
    assert hb3.should_pivot("research") is False
    print(f"   PASS — should_pivot() works correctly")


# ── Test 3: WorkspaceManager ──────────────────────────────────────────────────
def test_workspace_manager():
    print("── Test 3: WorkspaceManager ──")
    from coral.workspace import WorkspaceManager

    ws = WorkspaceManager()

    path = ws.create_agent_workspace(
        agent_id="agent-1",
        task_name="Test Task",
        task_description="Test description",
        total_agents=3,
    )
    assert path.exists(), "Agent dir should exist"
    assert (path / "CORAL.md").exists(), "CORAL.md should exist"
    assert (path / ".coral_dir").exists(), "Breadcrumb should exist"
    assert (path / "workspace").exists(), "Workspace dir should exist"
    assert (path / ".claude").exists(), ".claude dir should exist"
    print(f"   PASS — create_agent_workspace: {path}")

    coral_md = (path / "CORAL.md").read_text()
    assert "agent-1" in coral_md and "Test Task" in coral_md
    print(f"   PASS — CORAL.md generated correctly")

    # Notes and skills folders created inside .claude/ (link OR copy)
    notes_dir  = path / ".claude" / "notes"
    skills_dir = path / ".claude" / "skills"
    assert notes_dir.exists(),  ".claude/notes should exist (symlink, junction, or copy)"
    assert skills_dir.exists(), ".claude/skills should exist (symlink, junction, or copy)"
    print(f"   PASS — .claude/notes and .claude/skills exist")

    paths = ws.create_all_workspaces(["agent-1", "agent-2", "agent-3"])
    assert len(paths) == 3
    print(f"   PASS — create_all_workspaces: 3 workspaces")

    found = ws.list_workspaces()
    assert "agent-1" in found and "agent-2" in found
    print(f"   PASS — list_workspaces: {found}")

    assert ws.workspace_exists("agent-1") is True
    assert ws.workspace_exists("agent-99") is False
    print(f"   PASS — workspace_exists()")


# ── Test 4: Grader ────────────────────────────────────────────────────────────
def test_grader():
    print("── Test 4: Grader ──")
    from coral.grader import Grader
    g = Grader()

    r = g.grade("")
    assert r.score == 0.0
    print(f"   PASS — empty decision score=0.0")

    good_decision = (
        "Recommendation: PROCEED with this AI SaaS. "
        "Market size is $4.2B growing at 23%. "
        "ROI is 275% at 12 months with payback in 4 months. "
        "Competitors include OpenAI and Anthropic but a niche gap exists. "
        "Confidence: 85%"
    )
    r2 = g.grade(
        decision=good_decision,
        critiques=["Lacks primary source citations", "ROI assumptions optimistic"],
        research="Market is $4.2B growing at 23% YoY",
    )
    assert r2.score >= 0.6, f"Good decision should score >= 0.6, got {r2.score}"
    print(f"   PASS — good decision score={r2.score:.2f}")

    weak_decision = "The query has been analyzed. Multiple factors were considered."
    r3 = g.grade(weak_decision)
    assert r3.score < r2.score
    print(f"   PASS — weak decision score={r3.score:.2f} (lower than good)")

    assert all(k in r2.breakdown for k in [
        "decision_present", "has_recommendation",
        "references_data", "addresses_critiques", "confidence_stated"
    ])
    print(f"   PASS — breakdown keys present: {list(r2.breakdown.keys())}")


# ── Test 5: AgentManager ─────────────────────────────────────────────────────
async def test_agent_manager():
    print("── Test 5: AgentManager ──")
    from coral.agent_manager import AgentManager

    mgr = AgentManager(
        session_id="test-mgr-001",
        agent_ids=["research", "finance", "critic"],
    )

    await mgr.start_all(query="Should I start a SaaS?")
    assert mgr._running is True
    assert len(mgr._handles) == 3
    print(f"   PASS — start_all: {len(mgr._handles)} handles created")

    # Check workspaces exist (no symlink assertion — Windows compatible)
    from coral.workspace import AGENTS_ROOT
    for aid in ["research", "finance", "critic"]:
        agent_dir = AGENTS_ROOT / aid
        assert agent_dir.exists(), f"Workspace for {aid} should exist"
        assert (agent_dir / "CORAL.md").exists(), f"CORAL.md missing for {aid}"
    print(f"   PASS — all workspaces created with CORAL.md")

    s = mgr.status()
    assert s["session_id"] == "test-mgr-001"
    assert "research" in s["agents"]
    print(f"   PASS — status(): agents={list(s['agents'].keys())}")

    await mgr.stop_all()
    assert mgr._running is False
    print(f"   PASS — stop_all(): running=False")


# ── Runner ────────────────────────────────────────────────────────────────────
async def run_all():
    setup_test_env()
    results = []

    try:
        print("")
        sync_tests = [
            ("CoralMemory",      test_coral_memory),
            ("HeartbeatRunner",  test_heartbeat_runner),
            ("WorkspaceManager", test_workspace_manager),
            ("Grader",           test_grader),
        ]
        for name, fn in sync_tests:
            try:
                fn()
                results.append(True)
            except Exception as exc:
                print(f"   FAIL — {exc}")
                import traceback; traceback.print_exc()
                results.append(False)

        # Async test
        try:
            await test_agent_manager()
            results.append(True)
        except Exception as exc:
            print(f"   FAIL — {exc}")
            import traceback; traceback.print_exc()
            results.append(False)

    finally:
        teardown_test_env()

    print("\n── Summary ──")
    passed = sum(results)
    total  = len(results)
    print(f"   {passed}/{total} tests passed")

    if passed == total:
        print("\n   CORAL package ready.")
        print("   Next: python test_phase2.py -> uvicorn main:app --reload --port 8000\n")
    else:
        print("\n   Fix failures above before starting uvicorn.\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())