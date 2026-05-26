"""Benchmark script for the deep research pipeline.

Runs a set of curated queries through deep_research at varying depth tiers
and reports per-stage timing, token usage, citation count, and verifier stats.
Writes full markdown reports to docs/benchmarks/research-<timestamp>/.

Usage (from repo root):
    python scripts/bench_research.py
    python scripts/bench_research.py --tier quick --queries 2
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "runtime"))

from kairos_runtime.research.config import DepthTier  # noqa: E402
from kairos_runtime.research.runner import deep_research  # noqa: E402
from kairos_runtime.research.state import ProgressEvent  # noqa: E402

QUERIES: list[tuple[str, DepthTier]] = [
    (
        "Compare LangGraph and CrewAI for building multi-agent systems in 2026. "
        "Cover architecture, ease of use, performance, and community adoption.",
        "standard",
    ),
    (
        "What are the current state-of-the-art approaches to reducing hallucination "
        "in LLM-powered research agents? Include recent papers from 2025-2026.",
        "standard",
    ),
    (
        "Analyze the competitive landscape of AI code assistants as of May 2026: "
        "Cursor, GitHub Copilot, Windsurf, Cline. Market share, pricing, capabilities.",
        "standard",
    ),
    (
        "What is prompt caching and how do different LLM providers implement it? "
        "Compare Google, Anthropic, and OpenAI approaches with cost savings data.",
        "quick",
    ),
    (
        "Survey the latest techniques for building personal knowledge management "
        "systems with AI. Cover graph-based approaches, RAG, and hybrid methods.",
        "deep",
    ),
]


async def run_benchmark(
    queries: list[tuple[str, DepthTier]],
    output_dir: Path,
) -> None:
    """Run all benchmark queries and write results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    for i, (query, tier) in enumerate(queries):
        print(f"\n{'='*60}")
        print(f"Query {i+1}/{len(queries)} [tier={tier}]")
        print(f"  {query[:80]}...")
        print(f"{'='*60}")

        progress_log: list[str] = []

        def _on_progress(event: ProgressEvent, _log: list[str] = progress_log) -> None:
            ts = event.timestamp.strftime("%H:%M:%S")
            line = f"  [{ts}] {event.stage}: {event.message}"
            _log.append(line)
            print(line, flush=True)

        start = time.perf_counter()
        try:
            report = await deep_research(
                query, depth_tier=tier, on_progress=_on_progress
            )
            elapsed = time.perf_counter() - start

            result = {
                "query": query,
                "tier": tier,
                "elapsed_s": elapsed,
                "tokens_used": report.tokens_used,
                "budget": report.budget.model_dump(),
                "citations": len(report.citations),
                "verification": report.verification.model_dump(),
                "report_length": len(report.markdown),
                "success": True,
            }

            # Write individual report
            report_file = output_dir / f"report_{i+1}_{tier}.md"
            report_file.write_text(report.markdown, encoding="utf-8")
            print(f"\n  Report written: {report_file.name} ({len(report.markdown)} chars)")

        except Exception as exc:
            elapsed = time.perf_counter() - start
            result = {
                "query": query,
                "tier": tier,
                "elapsed_s": elapsed,
                "error": str(exc),
                "success": False,
            }
            print(f"\n  FAILED: {exc}")

        results.append(result)
        _print_result(result)

    # Write summary
    _write_summary(results, output_dir)


def _print_result(result: dict) -> None:
    """Print a single benchmark result."""
    print("\n  --- Result ---")
    print(f"  Elapsed:     {result['elapsed_s']:.1f}s")
    if result["success"]:
        print(f"  Tokens:      {result.get('budget', {}).get('used', '?')}")
        print(f"  Citations:   {result['citations']}")
        v = result.get("verification", {})
        print(f"  Verified:    {v.get('verified_count', 0)}/{v.get('total_citations', 0)}")
        print(f"  Dead URLs:   {len(v.get('dead_urls', []))}")
        print(f"  Halluc URLs: {len(v.get('hallucinated_urls', []))}")
        print(f"  Report len:  {result['report_length']} chars")
    else:
        print(f"  Error:       {result.get('error', 'unknown')}")


def _write_summary(results: list[dict], output_dir: Path) -> None:
    """Write a summary markdown file."""
    lines = [
        "# Deep Research Benchmark Results",
        f"\nRun: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\n## Summary\n",
        "| # | Tier | Elapsed | Tokens | Citations | Verified | Dead | Report |",
        "|---|------|---------|--------|-----------|----------|------|--------|",
    ]

    for i, r in enumerate(results):
        if r["success"]:
            budget = r.get("budget", {})
            v = r.get("verification", {})
            lines.append(
                f"| {i+1} | {r['tier']} | {r['elapsed_s']:.1f}s | "
                f"{budget.get('used', '?')} | {r['citations']} | "
                f"{v.get('verified_count', 0)}/{v.get('total_citations', 0)} | "
                f"{len(v.get('dead_urls', []))} | {r['report_length']} |"
            )
        else:
            lines.append(
                f"| {i+1} | {r['tier']} | {r['elapsed_s']:.1f}s | "
                f"FAILED | - | - | - | {r.get('error', '')[:40]} |"
            )

    lines.append("\n## Queries\n")
    for i, r in enumerate(results):
        lines.append(f"{i+1}. [{r['tier']}] {r['query'][:100]}")

    summary_path = output_dir / "SUMMARY.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSummary written to: {summary_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark deep research pipeline")
    ap.add_argument(
        "--tier",
        choices=["quick", "standard", "deep", "exhaustive"],
        default=None,
        help="Override all queries to this tier (default: use per-query tier)",
    )
    ap.add_argument(
        "--queries",
        type=int,
        default=None,
        help="Limit number of queries to run (default: all)",
    )
    args = ap.parse_args()

    queries = QUERIES[: args.queries] if args.queries else QUERIES
    if args.tier:
        queries = [(q, args.tier) for q, _ in queries]

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = ROOT / "docs" / "benchmarks" / f"research-{ts}"

    print("Deep Research Benchmark")
    print(f"  Queries:    {len(queries)}")
    print(f"  Output dir: {output_dir}")

    asyncio.run(run_benchmark(queries, output_dir))


if __name__ == "__main__":
    main()
