"""
coral/grader.py  (copied to .coral/private/eval/grader.py at startup)
──────────────────────────────────────────────────────────────────────
Grader — evaluates the quality of a CEO agent decision.
Hidden from all agents. Agents submit decisions and see only the score.

Compatible with AgentManager.memory.write_attempt() —
call grade() and pass the result to write_attempt(score=..., feedback=...).

Scoring rubric (0.0 – 1.0):
  0.2  — Decision is present (not empty)
  0.2  — Contains a clear recommendation (proceed / don't proceed / needs more info)
  0.2  — References at least one specific data point from research/finance/competitor
  0.2  — Addresses at least one critique from the Critic agent
  0.2  — Confidence score is explicitly stated
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class GradeResult:
    score: float            # 0.0 – 1.0
    feedback: str           # human-readable explanation
    breakdown: dict         # per-criterion scores


class Grader:
    """
    Evaluates CEO agent decision output quality.

    Usage in meta/evaluator.py:
        grader = Grader()
        result = grader.grade(
            decision=state["final_decision"],
            critiques=state["critiques"],
            research=state["research_output"],
        )
        memory.write_attempt(
            agent_id="ceo",
            output=state["final_decision"],
            score=result.score,
            feedback=result.feedback,
        )
    """

    # Keywords that suggest a clear recommendation is present
    RECOMMENDATION_KEYWORDS = [
        "proceed", "don't proceed", "do not proceed",
        "recommend", "advised", "should", "go ahead",
        "avoid", "reject", "approved", "declined",
        "needs more info", "insufficient data",
    ]

    def grade(
        self,
        decision: str,
        critiques: Optional[list[str]] = None,
        research: Optional[str] = None,
        finance: Optional[str] = None,
        competitor: Optional[str] = None,
    ) -> GradeResult:
        """
        Score a CEO agent decision on 5 criteria, each worth 0.2 points.
        """
        if not decision or not decision.strip():
            return GradeResult(
                score=0.0,
                feedback="Decision is empty — no output to grade.",
                breakdown={"empty": 0.0},
            )

        breakdown = {}
        total = 0.0

        # ── Criterion 1: Decision is present ─────────────────────────────────
        c1 = 0.2 if len(decision.strip()) > 50 else 0.0
        breakdown["decision_present"] = c1
        total += c1

        # ── Criterion 2: Clear recommendation ────────────────────────────────
        lower = decision.lower()
        c2 = 0.2 if any(kw in lower for kw in self.RECOMMENDATION_KEYWORDS) else 0.0
        breakdown["has_recommendation"] = c2
        total += c2

        # ── Criterion 3: References specific data points ──────────────────────
        # Check for numbers, percentages, dollar amounts, or named entities
        has_data = bool(re.search(r'\$[\d,]+|[\d.]+%|[\d,]+ (billion|million|thousand)|[A-Z][a-z]+\s[A-Z]', decision))
        c3 = 0.2 if has_data else 0.0
        breakdown["references_data"] = c3
        total += c3

        # ── Criterion 4: Addresses critiques ─────────────────────────────────
        c4 = 0.0
        if critiques:
            # Check if any critique keywords appear in the decision
            critique_text = " ".join(critiques).lower()
            critique_words = set(re.findall(r'\b\w{5,}\b', critique_text))
            decision_words = set(re.findall(r'\b\w{5,}\b', lower))
            overlap = len(critique_words & decision_words)
            c4 = 0.2 if overlap >= 3 else 0.1 if overlap >= 1 else 0.0
        else:
            c4 = 0.1   # no critiques to address — partial credit
        breakdown["addresses_critiques"] = c4
        total += c4

        # ── Criterion 5: Confidence score stated ──────────────────────────────
        has_confidence = bool(re.search(r'confidence[:\s]+[\d.]+%?|[\d.]+%\s+confidence|\b(high|medium|low)\s+confidence', lower))
        c5 = 0.2 if has_confidence else 0.0
        breakdown["confidence_stated"] = c5
        total += c5

        # ── Build feedback message ────────────────────────────────────────────
        score = round(min(total, 1.0), 3)
        issues = [k for k, v in breakdown.items() if v == 0.0]
        feedback_parts = [f"Score: {score:.0%}"]
        if issues:
            feedback_parts.append(f"Missing: {', '.join(issues)}")
        if score >= 0.8:
            feedback_parts.append("Strong decision — ready for output.")
        elif score >= 0.6:
            feedback_parts.append("Acceptable — consider another debate round.")
        else:
            feedback_parts.append("Weak decision — needs significant improvement.")

        return GradeResult(
            score=score,
            feedback=" | ".join(feedback_parts),
            breakdown=breakdown,
        )

    def grade_sync(self, **kwargs) -> GradeResult:
        """Synchronous wrapper for use in non-async contexts."""
        return self.grade(**kwargs)