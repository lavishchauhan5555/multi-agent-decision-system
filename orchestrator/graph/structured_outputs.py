"""
graph/structured_outputs.py
───────────────────────────
Pydantic structured-output models for every agent node.
Provides a helper that wraps a LangChain chat model with
.with_structured_output() so callers get typed objects back.

Usage
-----
    from graph.structured_outputs import get_structured_llm, ResearchOutput

    llm = get_structured_llm(base_llm, ResearchOutput)
    result: ResearchOutput = await llm.ainvoke(messages)
    print(result.market_size)

Supported models
----------------
    Gemini  (ChatGoogleGenerativeAI)  — method="function_calling"
    Grok    (ChatOpenAI via Groq)     — method="json_schema"

Both providers support .with_structured_output() natively in LangChain ≥ 0.2.
"""

from __future__ import annotations

from typing import Any, List, Optional, Type, TypeVar

from pydantic import BaseModel, Field, field_validator, AliasChoices ,model_validator
import asyncio, json, re, time
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# TYPE VAR
# ─────────────────────────────────────────────────────────────────────────────

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Research agent output
# ─────────────────────────────────────────────────────────────────────────────
# class ResearchOutput(BaseModel):
#     market_size: str = Field(
#         default="data unavailable",
#         description="Total addressable market size with source or 'data unavailable'."
#     )

#     growth_rate: str = Field(
#         default="data unavailable",
#         description="Annual market growth rate or 'data unavailable'."
#     )

#     trends: List[str] = Field(default_factory=list)
#     key_players: List[str] = Field(default_factory=list)
#     opportunities: List[str] = Field(default_factory=list)
#     risks: List[str] = Field(default_factory=list)

#     critique_responses: Optional[List[str]] = Field(default_factory=list)

#     raw_summary: str = Field(
#         default="data unavailable",
#         description="2-3 sentence plain-language summary."
#     )

#     @field_validator(
#         "trends",
#         "key_players",
#         "opportunities",
#         "risks",
#         "critique_responses",
#         mode="before",
#     )
#     @classmethod
#     def normalize_list(cls, value: Any):
#         if value is None:
#             return []

#         if isinstance(value, list):
#             return [str(v).strip() for v in value if str(v).strip()]

#         if isinstance(value, str):
#             return [
#                 item.strip()
#                 for item in value.replace(";", ",").split(",")
#                 if item.strip()
#             ]

#         return []

class ResearchOutput(BaseModel):
    market_size: str = Field(
        default="data unavailable",
        description="Detailed market size with numbers, region, year, and source context if available."
    )

    growth_rate: str = Field(
        default="data unavailable",
        description="Detailed growth rate, CAGR, adoption trend, or 'data unavailable'."
    )

    trends: List[str] = Field(default_factory=list)
    key_players: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)

    critique_responses: Optional[List[str]] = Field(default_factory=list)

    evidence_points: List[str] = Field(default_factory=list)

    raw_summary: str = Field(
        default="data unavailable",
        description="150-220 word plain-language research summary."
    )

    @field_validator(
        "trends",
        "key_players",
        "opportunities",
        "risks",
        "critique_responses",
        "evidence_points",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []

    @field_validator("market_size", "growth_rate", "raw_summary", mode="before")
    @classmethod
    def normalize_string(cls, value: Any):
        if value is None:
            return "data unavailable"
        text = str(value).strip()
        return text if text else "data unavailable"

    @model_validator(mode="after")
    def fill_and_trim_lists(self):
        def normalize(items, minimum, maximum, label):
            items = items or []
            items = [str(x).strip() for x in items if str(x).strip()]

            while len(items) < minimum:
                items.append(f"{label} unavailable")

            return items[:maximum]

        self.trends = normalize(self.trends, 5, 7, "trend")
        self.key_players = normalize(self.key_players, 5, 8, "key player")
        self.opportunities = normalize(self.opportunities, 4, 6, "opportunity")
        self.risks = normalize(self.risks, 4, 6, "risk")
        self.evidence_points = normalize(self.evidence_points, 3, 6, "evidence")
        self.critique_responses = normalize(
            self.critique_responses,
            1,
            6,
            "No prior critique to address."
        )

        return self    

# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — Finance agent output
# ─────────────────────────────────────────────────────────────────────────────

class MonthlyProjection(BaseModel):
    month: int = Field(description="Month number 1-12.")
    revenue: float = Field(description="Projected revenue in USD.")
    cost: float = Field(description="Operating cost in USD.")
    net: float = Field(description="Net profit/loss for this month in USD.")

    @field_validator("revenue", "cost", "net", mode="before")
    @classmethod
    def clean_money(cls, value: Any):
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()
        return value


class FinanceOutput(BaseModel):
    initial_investment: float = Field(description="Initial investment in USD.")

    monthly_projections: List[MonthlyProjection] = Field(
        description="Exactly 12 monthly projections.",
        min_length=12,
        max_length=12,
    )

    total_revenue: float = Field(description="Total 12-month revenue.")
    total_cost: float = Field(description="Total 12-month cost.")
    net_profit: float = Field(description="total_revenue - total_cost.")
    roi_percent: float = Field(description="(net_profit / total_cost) * 100.")

    payback_months: Optional[float] = Field(
        default=None,
        description="Month when cumulative net becomes positive. None if never.",
    )

    financial_risks: List[str] = Field(
        description="Exactly 3 financial risks.",
        min_length=3,
        max_length=3,
    )

    recommendation: str = Field(
        description="GO, NO-GO, or CONDITIONAL GO with short reason."
    )

    critique_responses: Optional[List[str]] = Field(default_factory=list)

    @field_validator(
        "initial_investment",
        "total_revenue",
        "total_cost",
        "net_profit",
        "roi_percent",
        "payback_months",
        mode="before",
    )
    @classmethod
    def clean_number(cls, value: Any):
        if value is None:
            return None

        if isinstance(value, str):
            value = (
                value.replace("$", "")
                .replace(",", "")
                .replace("%", "")
                .strip()
            )

            if value.lower() in ["none", "null", "never", "n/a"]:
                return None

        return value

    @field_validator("financial_risks", "critique_responses", mode="before")
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []


# ─────────────────────────────────────────────────────────────────────────────
# Competitor Schema
# ─────────────────────────────────────────────────────────────────────────────

class Competitor(BaseModel):
    name: str = Field(default="unknown", description="Real company name.")
    description: str = Field(default="data unavailable")

    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)

    # ❗ remove Optional → always string
    market_share_or_funding: str = Field(default="unknown")

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []

    @field_validator("market_share_or_funding", mode="before")
    @classmethod
    def normalize_string(cls, value: Any):
        if value is None:
            return "unknown"
        text = str(value).strip()
        return text if text else "unknown"

    @model_validator(mode="after")
    def fill_lists(self):
        def fill(items, minimum, maximum, label):
            items = items or []
            items = [str(x).strip() for x in items if str(x).strip()]

            while len(items) < minimum:
                items.append(f"{label} unavailable")

            return items[:maximum]

        self.strengths = fill(self.strengths, 2, 3, "strength")
        self.weaknesses = fill(self.weaknesses, 2, 3, "weakness")

        return self

class CompetitorOutput(BaseModel):
    competitors: List[Competitor] = Field(default_factory=list)
    market_gaps: List[str] = Field(default_factory=list)
    differentiation_strategy: str = Field(default="data unavailable")

    # ❗ REMOVE Optional → prevents null
    approaches_to_avoid: List[str] = Field(default_factory=list)
    critique_responses: List[str] = Field(default_factory=list)

    evidence_points: List[str] = Field(default_factory=list)

    @field_validator(
        "market_gaps",
        "approaches_to_avoid",
        "critique_responses",
        "evidence_points",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []

    @field_validator("differentiation_strategy", mode="before")
    @classmethod
    def normalize_string(cls, value: Any):
        if value is None:
            return "data unavailable"
        text = str(value).strip()
        return text if text else "data unavailable"

    @model_validator(mode="after")
    def fill_missing(self):
        def fill(items, minimum, maximum, label):
            items = items or []
            items = [str(x).strip() for x in items if str(x).strip()]

            while len(items) < minimum:
                items.append(f"{label} unavailable")

            return items[:maximum]

        # ✅ ensure 3–5 competitors
        self.competitors = self.competitors[:5]
        while len(self.competitors) < 3:
            self.competitors.append(
                Competitor(
                    name="unknown",
                    description="competitor unavailable",
                    strengths=["strength unavailable", "strength unavailable"],
                    weaknesses=["weakness unavailable", "weakness unavailable"],
                    market_share_or_funding="unknown",
                )
            )

        self.market_gaps = fill(self.market_gaps, 2, 3, "market gap")
        self.approaches_to_avoid = fill(
            self.approaches_to_avoid,
            1,
            5,
            "No failed approach recorded"
        )
        self.critique_responses = fill(
            self.critique_responses,
            1,
            5,
            "No prior critique to address"
        )
        self.evidence_points = fill(self.evidence_points, 3, 6, "evidence")

        return self

# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Critic agent output
# ─────────────────────────────────────────────────────────────────────────────
class CriticOutput(BaseModel):
    research_flaws: List[str] = Field(default_factory=list)
    finance_flaws: List[str] = Field(default_factory=list)
    competitor_flaws: List[str] = Field(default_factory=list)
    top_risks: List[str] = Field(default_factory=list)

    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = Field(default="No reasoning provided.")

    @field_validator(
        "research_flaws",
        "finance_flaws",
        "competitor_flaws",
        "top_risks",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]
        return []

    @field_validator("reasoning", mode="before")
    @classmethod
    def normalize_reasoning(cls, value: Any):
        if value is None:
            return "No reasoning provided."
        text = str(value).strip()
        return text if text else "No reasoning provided."

    @model_validator(mode="after")
    def fill_and_trim(self):
        def fill(items, minimum, maximum, label):
            items = items or []
            while len(items) < minimum:
                items.append(label)
            return items[:maximum]

        self.research_flaws = fill(
            self.research_flaws,
            3,
            5,
            "Research evidence is incomplete or insufficiently validated."
        )
        self.finance_flaws = fill(
            self.finance_flaws,
            1,
            5,
            "No specific finance flaws identified."
        )
        self.competitor_flaws = fill(
            self.competitor_flaws,
            1,
            5,
            "No specific competitor flaws identified."
        )
        self.top_risks = fill(
            self.top_risks,
            3,
            3,
            "General execution risk."
        )

        self.confidence_score = max(0.0, min(1.0, float(self.confidence_score)))
        return self
# ─────────────────────────────────────────────────────────────────────────────
# NODE 7 — CEO agent output
# ─────────────────────────────────────────────────────────────────────────────


class CEOOutput(BaseModel):
    recommendation: str = Field(
        default="CONDITIONAL PROCEED",
        description="One of: PROCEED, DO NOT PROCEED, CONDITIONAL PROCEED."
    )

    confidence_percent: float = Field(default=50.0, ge=0.0, le=100.0)

    reasoning: str = Field(default="Decision requires further validation.")

    key_success_conditions: List[str] = Field(default_factory=list)
    risk_mitigations: List[str] = Field(default_factory=list)
    critic_concerns_addressed: List[str] = Field(default_factory=list)

    @field_validator(
        "key_success_conditions",
        "risk_mitigations",
        "critic_concerns_addressed",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value: Any):
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []

    @field_validator("recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, value: Any):
        text = str(value or "").strip().upper()

        if text in ["GO", "PROCEED", "YES"]:
            return "PROCEED"

        if text in ["NO-GO", "NO GO", "DO NOT PROCEED", "DON'T PROCEED", "NO"]:
            return "DO NOT PROCEED"

        if text in ["CONDITIONAL GO", "CONDITIONAL PROCEED", "MAYBE"]:
            return "CONDITIONAL PROCEED"

        return "CONDITIONAL PROCEED"

    @field_validator("reasoning", mode="before")
    @classmethod
    def normalize_reasoning(cls, value: Any):
        if value is None:
            return "Decision requires further validation."
        text = str(value).strip()
        return text if text else "Decision requires further validation."

    @model_validator(mode="after")
    def fill_required_lists(self):
        def fill(items, minimum, maximum, label):
            items = items or []
            items = [str(x).strip() for x in items if str(x).strip()]

            while len(items) < minimum:
                items.append(label)

            return items[:maximum]

        self.key_success_conditions = fill(
            self.key_success_conditions,
            3,
            3,
            "Validate assumptions with real customer and market data."
        )

        self.risk_mitigations = fill(
            self.risk_mitigations,
            3,
            3,
            "Reduce risk through staged rollout and milestone-based funding."
        )

        self.critic_concerns_addressed = fill(
            self.critic_concerns_addressed,
            1,
            5,
            "Critic concerns require further validation."
        )

        self.confidence_percent = max(0.0, min(100.0, float(self.confidence_percent)))

        return self
# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER-AWARE STRUCTURED LLM FACTORY
# ─────────────────────────────────────────────────────────────────────────────

# Maps provider class name → best .with_structured_output() method
_PROVIDER_METHOD: dict[str, str] = {
    "ChatGoogleGenerativeAI": "function_calling",   # Gemini
    "ChatOpenAI":             "json_schema",         # Groq (OpenAI-compat)
    "ChatAnthropic":          "function_calling",    # Claude (fallback)
}

_FALLBACK_METHOD = "function_calling"


def get_structured_llm(base_llm: Any, schema: Type[T]) -> Any:
    """
    Wrap a LangChain chat model with .with_structured_output(schema).

    Selects the correct method automatically based on the provider:
        Gemini  → method="function_calling"
        Grok    → method="json_schema"
        Claude  → method="function_calling"

    Args:
        base_llm:  Any LangChain chat model instance.
        schema:    A Pydantic BaseModel subclass (e.g. ResearchOutput).

    Returns:
        A runnable that returns instances of `schema` from .ainvoke().
        Returns None if base_llm is None (safe stub path).

    Example:
        llm = get_structured_llm(rt.genai, ResearchOutput)
        result: ResearchOutput = await llm.ainvoke(messages)
    """
    if base_llm is None:
        return None

    provider = type(base_llm).__name__
    method = _PROVIDER_METHOD.get(provider, _FALLBACK_METHOD)

    try:
        return base_llm.with_structured_output(schema, method=method)
    except TypeError:
        # Older LangChain versions don't accept method= kwarg
        return base_llm.with_structured_output(schema)



def get_pydantic_parser(schema: Type[T]) -> Any:
    """Return a LangChain PydanticOutputParser for a structured output schema."""
    from langchain_core.output_parsers import PydanticOutputParser
    return PydanticOutputParser(pydantic_object=schema)


def get_format_instructions(schema: Type[T]) -> str:
    """Return parser-backed formatting instructions for prompts."""
    return get_pydantic_parser(schema).get_format_instructions()


def structured_to_markdown(obj: BaseModel) -> str:
    """
    Convert any structured output Pydantic object to a readable
    markdown string so it can be stored in debate_transcript / CORAL memory.

    Falls back to JSON if the model has no custom fields to render.
    """
    lines: list[str] = []
    for field_name, field_info in obj.model_fields.items():
        value = getattr(obj, field_name, None)
        if value is None:
            continue
        title = field_name.replace("_", " ").title()
        if isinstance(value, list):
            lines.append(f"**{title}**")
            for item in value:
                if isinstance(item, BaseModel):
                    lines.append(f"  - {item.model_dump()}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(value, BaseModel):
            lines.append(f"**{title}**")
            lines.append(f"  {value.model_dump()}")
        else:
            lines.append(f"**{title}:** {value}")
    return "\n".join(lines) if lines else obj.model_dump_json(indent=2)