"""Model routing + budget configuration for deep research.

All values overridable via env vars loaded through atlas_runtime.config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from atlas_runtime.config import get

DepthTier = Literal["quick", "standard", "deep", "exhaustive"]

# ---------------------------------------------------------------------------
# Model assignments (Flash-only per project constraint)
# ---------------------------------------------------------------------------

CLASSIFIER_MODEL = "gemini-3.1-flash-lite"
LEAD_MODEL = "gemini-3.5-flash"
SUBAGENT_MODEL = "gemini-3.5-flash"
VERIFIER_MODEL = "gemini-3.1-flash-lite"
SYNTHESIZER_MODEL = "gemini-3.5-flash"


def get_model(role: str) -> str:
    """Resolve model for a given role, checking env overrides first."""
    defaults = {
        "classifier": CLASSIFIER_MODEL,
        "lead": LEAD_MODEL,
        "subagent": SUBAGENT_MODEL,
        "verifier": VERIFIER_MODEL,
        "synthesizer": SYNTHESIZER_MODEL,
    }
    env_key = f"DISEASE360_RESEARCH_{role.upper()}_MODEL"
    return get(env_key, defaults.get(role, SUBAGENT_MODEL)) or defaults.get(
        role, SUBAGENT_MODEL
    )


# ---------------------------------------------------------------------------
# Token budgets per tier
# ---------------------------------------------------------------------------

TOKEN_BUDGETS: dict[DepthTier, int] = {
    "quick": 100_000,
    "standard": 500_000,
    "deep": 1_500_000,
    "exhaustive": 3_000_000,
}

WALL_CLOCK_TIMEOUT_SECONDS: dict[DepthTier, int] = {
    "quick": 300,
    "standard": 600,
    "deep": 900,
    "exhaustive": 1500,
}


def get_token_budget(tier: DepthTier) -> int:
    env_key = f"DISEASE360_RESEARCH_BUDGET_{tier.upper()}"
    override = get(env_key)
    if override:
        return int(override)
    return TOKEN_BUDGETS[tier]


def get_timeout(tier: DepthTier) -> int:
    env_key = f"DISEASE360_RESEARCH_TIMEOUT_{tier.upper()}"
    override = get(env_key)
    if override:
        return int(override)
    return WALL_CLOCK_TIMEOUT_SECONDS[tier]


# ---------------------------------------------------------------------------
# Concurrency / effort caps
# ---------------------------------------------------------------------------

MAX_CONCURRENT_SUBAGENTS = 5
MAX_ROUNDS = 3
MAX_TOOL_CALLS_PER_SUBAGENT = 15

BUDGET_EARLY_STOP_THRESHOLD = 0.80


@dataclass(frozen=True)
class TierConfig:
    """Resolved configuration for a single research run."""

    tier: DepthTier
    token_budget: int
    timeout_seconds: int
    max_concurrent: int
    max_rounds: int
    max_tool_calls: int
    early_stop_pct: float

    @property
    def subagent_budget(self) -> int:
        return self.token_budget // self.max_concurrent


def resolve_tier(tier: DepthTier) -> TierConfig:
    max_conc = int(get("DISEASE360_RESEARCH_MAX_CONCURRENT") or MAX_CONCURRENT_SUBAGENTS)
    max_rnd = int(get("DISEASE360_RESEARCH_MAX_ROUNDS") or MAX_ROUNDS)
    max_tc = int(get("DISEASE360_RESEARCH_MAX_TOOL_CALLS") or MAX_TOOL_CALLS_PER_SUBAGENT)
    return TierConfig(
        tier=tier,
        token_budget=get_token_budget(tier),
        timeout_seconds=get_timeout(tier),
        max_concurrent=max_conc,
        max_rounds=max_rnd,
        max_tool_calls=max_tc,
        early_stop_pct=BUDGET_EARLY_STOP_THRESHOLD,
    )
