"""Main orchestrator: classifier -> brief -> lead -> verifier -> synthesizer.

Maintains a TokenMeter, enforces hard caps, handles budget early-stop,
wall-clock timeouts, and progress callbacks.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .cache import RunCache
from .classifier import classify_and_brief, classify_query, write_research_brief
from .config import DepthTier, TierConfig, resolve_tier
from . import debug_dump
from .filesystem import VirtualFS
from .lead import build_lead_agent
from .state import (
    BudgetReport,
    Citation,
    ProgressEvent,
    ResearchReport,
    VerificationReport,
)
from .synthesizer import synthesize_report
from .url_whitelist import URLWhitelist
from .verifier import verify_findings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token meter
# ---------------------------------------------------------------------------


@dataclass
class TokenMeter:
    """Tracks token usage across the entire research run."""

    ceiling: int = 500_000
    used: int = 0
    per_stage: dict[str, int] = field(default_factory=dict)
    early_stopped: bool = False

    def record(self, stage: str, tokens: int) -> None:
        self.used += tokens
        self.per_stage[stage] = self.per_stage.get(stage, 0) + tokens

    @property
    def pct_used(self) -> float:
        if self.ceiling <= 0:
            return 0.0
        return self.used / self.ceiling

    def should_early_stop(self, threshold: float = 0.80) -> bool:
        return self.pct_used >= threshold


# ---------------------------------------------------------------------------
# Progress emitter
# ---------------------------------------------------------------------------


async def _emit(
    callback: Callable[[ProgressEvent], Any] | None,
    stage: str,
    message: str,
    **detail: Any,
) -> None:
    log.info("[research] %s | %s", stage, message)
    if callback:
        event = ProgressEvent(stage=stage, message=message, detail=detail)
        try:
            result = callback(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("progress emit failed for stage=%s", stage)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def deep_research(
    query: str,
    *,
    depth_tier: DepthTier | None = None,
    on_progress: Callable[[ProgressEvent], Any] | None = None,
    run_id: str | None = None,
) -> ResearchReport:
    """Execute a full deep research pipeline.

    Args:
        query: The research question
        depth_tier: Override the classifier's tier choice (None = auto-detect)
        on_progress: Optional callback for progress events
        run_id: Optional run identifier (generated if not provided)

    Returns:
        ResearchReport with markdown, citations, verification, and budget info
    """
    run_id = run_id or str(uuid.uuid4())[:8]
    started_at = datetime.now()
    stages_completed: list[str] = []
    tool_invocations: dict[str, int] = {}
    timings: dict[str, float] = {}

    def _stage_timer(stage: str) -> Callable[[], None]:
        t0 = datetime.now()

        def _stop() -> None:
            timings[stage] = (datetime.now() - t0).total_seconds()

        return _stop

    await _emit(
        on_progress, "start", f"Research run {run_id} started",
        query=query, run_id=run_id,
    )

    # -----------------------------------------------------------------------
    # Setup the meter early so classifier/brief can record real token usage.
    # The ceiling is updated below once we know the tier.
    # -----------------------------------------------------------------------
    meter = TokenMeter(ceiling=0)

    # -----------------------------------------------------------------------
    # Stage 1+2: Classification + Brief (single LLM call, two progress events)
    # -----------------------------------------------------------------------
    await _emit(on_progress, "classifier", "Classifying query...")

    _stop = _stage_timer("classify_and_brief")
    classification, brief = await classify_and_brief(query, meter=meter)
    _stop()
    stages_completed.append("classifier")
    stages_completed.append("brief")

    # Allow override of tier
    tier = depth_tier or classification.depth_tier
    tier_config = resolve_tier(tier)
    meter.ceiling = tier_config.token_budget

    await _emit(
        on_progress,
        "classifier",
        f"Classified as {classification.query_type.value}/{classification.domain.value} "
        f"depth={tier}",
        classification=classification.model_dump(),
    )

    # Check if clarification is needed (ambiguity > 0.6)
    if classification.ambiguity_score > 0.6 and classification.suggested_clarifications:
        await _emit(
            on_progress,
            "clarification_needed",
            "Query is ambiguous — proceeding with best interpretation",
            clarifications=classification.suggested_clarifications,
        )

    await _emit(on_progress, "brief", "Writing research brief...")

    # -----------------------------------------------------------------------
    # Setup: VFS, cache, URL whitelist (per-run, shared across subagents)
    # -----------------------------------------------------------------------
    vfs = VirtualFS()
    cache = RunCache()
    whitelist = URLWhitelist()

    # Write brief to VFS for synthesizer
    brief_content = (
        f"# Research Brief\n\n"
        f"**Title:** {brief.title}\n"
        f"**Objective:** {brief.objective}\n"
        f"**Scope:** {brief.scope}\n"
        f"**Constraints:** {', '.join(brief.constraints) if brief.constraints else 'None'}\n"
    )
    vfs.write("/brief.md", brief_content)

    # -----------------------------------------------------------------------
    # Stage 3: Lead orchestrator
    # -----------------------------------------------------------------------
    await _emit(on_progress, "lead", "Building lead researcher agent...")

    budget_early_stop = False

    try:
        agent = build_lead_agent(
            brief=brief,
            vfs=vfs,
            cache=cache,
            tier_config=tier_config,
            tool_invocations=tool_invocations,
            meter=meter,
            whitelist=whitelist,
        )

        await _emit(on_progress, "lead", "Lead researcher running...")

        # Run the lead agent with wall-clock timeout
        _stop = _stage_timer("lead")
        await asyncio.wait_for(
            _run_lead_agent(agent, query, vfs, meter, tier_config),
            timeout=tier_config.timeout_seconds,
        )
        _stop()
        stages_completed.append("lead")

        if meter.should_early_stop(tier_config.early_stop_pct):
            budget_early_stop = True
            meter.early_stopped = True
            await _emit(on_progress, "budget", "Budget threshold reached — early stopping")

    except asyncio.TimeoutError:
        log.warning("Lead agent timed out after %ds", tier_config.timeout_seconds)
        stages_completed.append("lead_timeout")
        budget_early_stop = True
        meter.early_stopped = True
        await _emit(on_progress, "timeout", "Wall-clock timeout — synthesizing partial findings")
    except Exception as exc:
        log.exception("Lead agent failed")
        stages_completed.append("lead_error")
        await _emit(on_progress, "error", f"Lead agent error: {exc}")

    # Grounding summary — Google vs DDG fallback rate
    g = tool_invocations.get("search_provider_google", 0)
    d = tool_invocations.get("search_provider_ddg", 0)
    n = tool_invocations.get("search_provider_none", 0)
    total = g + d + n
    if total:
        await _emit(
            on_progress,
            "grounding",
            (
                f"Search providers: {g}/{total} google "
                f"({100 * g / total:.0f}%), "
                f"{d}/{total} ddg fallback "
                f"({100 * d / total:.0f}%), "
                f"{n}/{total} empty"
            ),
            google=g,
            ddg=d,
            empty=n,
            total=total,
        )

    # -----------------------------------------------------------------------
    # Stage 4: Verification
    # -----------------------------------------------------------------------
    await _emit(on_progress, "verifier", "Verifying citations...")

    citations: list[Citation] = []
    verification = VerificationReport()

    try:
        _stop = _stage_timer("verifier")
        citations, verification = await verify_findings(
            vfs, cache=cache, meter=meter
        )
        _stop()
        stages_completed.append("verifier")

        verdict_counts: dict[str, int] = {}
        for c in citations:
            verdict_counts[c.nli_verdict] = verdict_counts.get(c.nli_verdict, 0) + 1
        await _emit(
            on_progress,
            "verifier",
            (
                f"Verified {verification.total_citations} citations: "
                f"{verdict_counts.get('entails', 0)} entails / "
                f"{verdict_counts.get('not_mentioned', 0)} not_mentioned / "
                f"{verdict_counts.get('contradicts', 0)} contradicts / "
                f"{len(verification.dead_urls)} dead / "
                f"{len(verification.hallucinated_urls)} hallucinated"
            ),
        )
    except Exception as exc:
        log.exception("Verifier failed")
        stages_completed.append("verifier_error")
        await _emit(on_progress, "error", f"Verifier error: {exc}")

    # -----------------------------------------------------------------------
    # Stage 5: Synthesis
    # -----------------------------------------------------------------------
    await _emit(on_progress, "synthesizer", "Synthesizing final report...")

    markdown = ""
    try:
        _stop = _stage_timer("synthesizer")
        markdown = await synthesize_report(
            vfs,
            citations,
            verification,
            depth_tier=tier,
            budget_early_stop=budget_early_stop,
            meter=meter,
        )
        _stop()
        stages_completed.append("synthesizer")

        await _emit(on_progress, "synthesizer", "Report complete")
    except Exception as exc:
        log.exception("Synthesizer failed")
        stages_completed.append("synthesizer_error")
        # Fallback: return raw findings
        markdown = _fallback_report(vfs)
        await _emit(on_progress, "error", f"Synthesizer error, returning raw findings: {exc}")

    # -----------------------------------------------------------------------
    # Assemble final report
    # -----------------------------------------------------------------------
    completed_at = datetime.now()

    budget_report = BudgetReport(
        ceiling=meter.ceiling,
        used=meter.used,
        early_stopped=meter.early_stopped,
        pct_used=meter.pct_used,
        stages_completed=stages_completed,
        note=(
            "Research was truncated at 80% budget; findings based on partial coverage."
            if meter.early_stopped
            else ""
        ),
    )

    report = ResearchReport(
        markdown=markdown,
        citations=citations,
        verification=verification,
        tokens_used=meter.per_stage,
        budget=budget_report,
        classification=classification,
        brief=brief,
        started_at=started_at,
        completed_at=completed_at,
        run_id=run_id,
    )

    if debug_dump.is_dump_enabled():
        import sys
        import traceback as _tb
        from pathlib import Path as _Path
        from kairos_runtime.config import repo_root as _repo_root

        def _safe_print(text: str) -> None:
            payload = text.encode("utf-8", errors="replace")
            try:
                sys.stdout.buffer.write(payload + b"\n")
                sys.stdout.flush()
            except Exception:
                try:
                    sys.stderr.buffer.write(payload + b"\n")
                    sys.stderr.flush()
                except Exception:
                    pass

        folder = None
        try:
            folder = debug_dump.dump_run(
                run_id=run_id,
                query=query,
                depth_tier=tier,
                vfs=vfs,
                classification=classification,
                citations=citations,
                verification=verification,
                markdown=markdown,
                tool_invocations=tool_invocations,
                timings=timings,
                started_at=started_at,
                completed_at=completed_at,
                tokens_used=meter.per_stage,
                budget_ceiling=meter.ceiling,
            )
            _safe_print(f"[research] debug dump written to {folder}")
        except Exception as exc:
            _safe_print(
                f"[research] debug dump FAILED (non-fatal): "
                f"{type(exc).__name__}: {exc}"
            )
            _safe_print(_tb.format_exc())
            # Last-resort: persist the traceback to a file so we don't lose it
            try:
                fallback_dir = (
                    _repo_root() / "services" / "harness" / "data" / "research_debug"
                )
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fp = fallback_dir / f"_dump_error_{run_id}.txt"
                fp.write_text(
                    f"run_id={run_id}\nquery={query}\n\n{_tb.format_exc()}",
                    encoding="utf-8",
                )
            except Exception:
                pass

    await _emit(
        on_progress,
        "complete",
        f"Research complete in {(completed_at - started_at).total_seconds():.1f}s",
        tokens_used=meter.used,
        citations=len(citations),
    )

    return report


async def _run_lead_agent(
    agent: Any,
    query: str,
    vfs: VirtualFS,
    meter: TokenMeter,
    tier_config: TierConfig,
) -> dict:
    """Invoke the lead agent.

    Token usage is recorded via the UsageCallback attached to each LLM
    instance (lead, subagents) — no scraping required here.
    """
    input_msg = {"messages": [{"role": "user", "content": query}]}
    return await agent.ainvoke(input_msg)


def _fallback_report(vfs: VirtualFS) -> str:
    """Emergency fallback: concatenate all findings if synthesis fails."""
    parts = ["# Research Findings (raw — synthesis failed)\n"]
    for path, content in vfs.files.items():
        if path == "/brief.md":
            continue
        parts.append(f"\n## {path}\n\n{content}")
    return "\n".join(parts) if len(parts) > 1 else "No findings were produced."
