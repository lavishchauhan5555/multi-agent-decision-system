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

from pydantic import BaseModel, Field, field_validator, AliasChoices

# ─────────────────────────────────────────────────────────────────────────────
# TYPE VAR
# ─────────────────────────────────────────────────────────────────────────────

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Research agent output
# ─────────────────────────────────────────────────────────────────────────────
class ResearchOutput(BaseModel):
    market_size: str = Field(
        default="data unavailable",
        description="Total addressable market size with source or 'data unavailable'."
    )

    growth_rate: str = Field(
        default="data unavailable",
        description="Annual market growth rate or 'data unavailable'."
    )

    trends: List[str] = Field(default_factory=list)
    key_players: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)

    critique_responses: Optional[List[str]] = Field(default_factory=list)

    raw_summary: str = Field(
        default="data unavailable",
        description="2-3 sentence plain-language summary."
    )

    @field_validator(
        "trends",
        "key_players",
        "opportunities",
        "risks",
        "critique_responses",
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
# NODE 4 — Competitor agent output
# ─────────────────────────────────────────────────────────────────────────────

class Competitor(BaseModel):
    name: str = Field(description="Real company name.")
    description: str = Field(description="One sentence describing what they do.")

    strengths: List[str] = Field(
        description="2-3 competitive strengths.",
        min_length=1
    )

    weaknesses: List[str] = Field(
        description="2-3 competitive weaknesses.",
        min_length=1
    )

    market_share_or_funding: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("market_share_or_funding", "market_share"),
        description="Known market share % or funding round. Omit if unknown.",
    )

    @field_validator("strengths", "weaknesses", mode="before")
    @classmethod
    def convert_string_to_list(cls, value: Any):
        if isinstance(value, list):
            return value

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return value


class CompetitorOutput(BaseModel):
    competitors: List[Competitor] = Field(
        description="3-5 real competitors.",
        min_length=1
    )

    market_gaps: List[str] = Field(
        description="2-3 genuine gaps the proposed business can exploit.",
        min_length=1,
    )

    differentiation_strategy: str = Field(
        description="Concrete differentiation approach in 2-4 sentences."
    )

    approaches_to_avoid: Optional[List[str]] = Field(
        default_factory=list,
        description="Strategies to avoid based on CORAL 'never-worked' memory.",
    )

    critique_responses: Optional[List[str]] = Field(
        default_factory=list,
        description="Point-by-point responses to competitor critiques from the last round.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Critic agent output
# ─────────────────────────────────────────────────────────────────────────────

class CriticOutput(BaseModel):
    research_flaws: List[str] = Field(default_factory=list)
    finance_flaws: List[str] = Field(default_factory=list)
    competitor_flaws: List[str] = Field(default_factory=list)

    top_risks: List[str] = Field(
        default_factory=list,
        min_length=3,
        max_length=3,
    )

    confidence_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
    )

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
            cleaned = [str(v).strip() for v in value if str(v).strip()]
            return cleaned

        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        return []

    @field_validator("finance_flaws", mode="after")
    @classmethod
    def ensure_finance_flaw(cls, value):
        if not value:
            return ["No specific finance flaws identified."]
        return value

    @field_validator("research_flaws", mode="after")
    @classmethod
    def ensure_research_flaw(cls, value):
        if not value:
            return ["No specific research flaws identified."]
        return value

    @field_validator("competitor_flaws", mode="after")
    @classmethod
    def ensure_competitor_flaw(cls, value):
        if not value:
            return ["No specific competitor flaws identified."]
        return value

    @field_validator("top_risks", mode="after")
    @classmethod
    def ensure_three_risks(cls, value):
        value = value or []

        while len(value) < 3:
            value.append("General execution risk.")

        return value[:3]


# ─────────────────────────────────────────────────────────────────────────────
# NODE 7 — CEO agent output
# ─────────────────────────────────────────────────────────────────────────────


class CEOOutput(BaseModel):
    recommendation: str = Field(
        default="CONDITIONAL PROCEED",
        description="One of: PROCEED, DO NOT PROCEED, or CONDITIONAL PROCEED."
    )

    confidence_percent: float = Field(
        default=50.0,
        ge=0.0,
        le=100.0,
    )

    reasoning: str = Field(default="Decision requires further validation.")

    key_success_conditions: List[str] = Field(
        default_factory=list,
        min_length=3,
        max_length=3,
    )

    risk_mitigations: List[str] = Field(
        default_factory=list,
        min_length=3,
        max_length=3,
    )

    critic_concerns_addressed: List[str] = Field(
        default_factory=list,
        min_length=1,
    )

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

    @field_validator("key_success_conditions", mode="after")
    @classmethod
    def ensure_three_conditions(cls, value):
        value = value or []
        while len(value) < 3:
            value.append("Validate assumptions with real customer and market data.")
        return value[:3]

    @field_validator("risk_mitigations", mode="after")
    @classmethod
    def ensure_three_mitigations(cls, value):
        value = value or []
        while len(value) < 3:
            value.append("Reduce risk through staged rollout and milestone-based funding.")
        return value[:3]

    @field_validator("critic_concerns_addressed", mode="after")
    @classmethod
    def ensure_concern(cls, value):
        if not value:
            return ["Critic concerns require further validation."]
        return value

    @field_validator("recommendation", mode="before")
    @classmethod
    def normalize_recommendation(cls, value):
        text = str(value or "").strip().upper()

        if text in ["GO", "PROCEED"]:
            return "PROCEED"

        if text in ["NO-GO", "NO GO", "DO NOT PROCEED", "DON'T PROCEED"]:
            return "DO NOT PROCEED"

        if text in ["CONDITIONAL GO", "CONDITIONAL PROCEED"]:
            return "CONDITIONAL PROCEED"

        return "CONDITIONAL PROCEED"

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