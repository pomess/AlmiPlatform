"""Pydantic models for the deep research pipeline state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Classification (output of the classifier stage)
# ---------------------------------------------------------------------------

class QueryType(str, Enum):
    SPECIFIC_FACT = "specific_fact"
    COMPARISON = "comparison"
    BROAD_SURVEY = "broad_survey"
    TREND_ANALYSIS = "trend_analysis"
    TECHNICAL_DEBUG = "technical_debug"
    MARKET_OPPORTUNITY_SCAN = "market_opportunity_scan"
    ACADEMIC_SYNTHESIS = "academic_synthesis"


class Domain(str, Enum):
    AI_ML = "ai_ml"
    SOFTWARE_ENG = "software_eng"
    MARKET = "market"
    SCIENTIFIC = "scientific"
    NEWS = "news"
    GENERAL = "general"


class Classification(BaseModel):
    query_type: QueryType
    domain: Domain
    depth_tier: Literal["quick", "standard", "deep", "exhaustive"]
    ambiguity_score: float = Field(ge=0.0, le=1.0)
    suggested_clarifications: list[str] = Field(default_factory=list, max_length=3)
    estimated_subagents: int = Field(ge=1, le=10)
    estimated_tokens: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Research brief
# ---------------------------------------------------------------------------

class ResearchBrief(BaseModel):
    title: str
    objective: str
    scope: str
    constraints: list[str] = Field(default_factory=list)
    output_format: str = "markdown"


# ---------------------------------------------------------------------------
# Subagent spec (passed from lead to subagent dispatch)
# ---------------------------------------------------------------------------

class SubagentSpec(BaseModel):
    name: str
    objective: str
    output_format: str = "markdown findings file"
    source_allowlist: list[str] = Field(default_factory=list)
    max_tool_calls: int = 15
    boundaries: str = ""


# ---------------------------------------------------------------------------
# Artifacts & citations
# ---------------------------------------------------------------------------

class Citation(BaseModel):
    index: int = 0
    url: str
    title: str = ""
    span: str = ""
    verified: bool = False
    live: bool = True
    wayback_url: str | None = None
    nli_verdict: Literal["entails", "contradicts", "not_mentioned", "unchecked"] = (
        "unchecked"
    )


class Artifact(BaseModel):
    path: str
    summary: str
    citation_count: int = 0
    source_agent: str = ""


# ---------------------------------------------------------------------------
# Verification report
# ---------------------------------------------------------------------------

class VerificationReport(BaseModel):
    total_citations: int = 0
    verified_count: int = 0
    hallucinated_urls: list[str] = Field(default_factory=list)
    dead_urls: list[str] = Field(default_factory=list)
    wayback_substituted: list[str] = Field(default_factory=list)
    low_confidence_claims: list[str] = Field(default_factory=list)
    contested_claims: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class BudgetReport(BaseModel):
    ceiling: int = 0
    used: int = 0
    early_stopped: bool = False
    pct_used: float = 0.0
    stages_completed: list[str] = Field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# Progress events (emitted via on_progress callback)
# ---------------------------------------------------------------------------

class ProgressEvent(BaseModel):
    stage: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

class ResearchReport(BaseModel):
    markdown: str
    citations: list[Citation] = Field(default_factory=list)
    verification: VerificationReport = Field(default_factory=VerificationReport)
    tokens_used: dict[str, int] = Field(default_factory=dict)
    budget: BudgetReport = Field(default_factory=BudgetReport)
    classification: Classification | None = None
    brief: ResearchBrief | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_id: str = ""


# ---------------------------------------------------------------------------
# Run status (for fire-and-forget mode)
# ---------------------------------------------------------------------------

class RunStatus(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    progress: list[ProgressEvent] = Field(default_factory=list)
    report: ResearchReport | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
