"""Batch research Barcelona-area pharma competitors and output structured JSON.

Uses open_deep_research (via disease360_runtime) + BioMCP for clinical trial data.
Outputs to apps/web/public/competitor-intel/{slug}.json.

Usage:
    uv run python scripts/research_competitors.py
    uv run python scripts/research_competitors.py --company "Sanofi"
    uv run python scripts/research_competitors.py --dry-run
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "runtime"))

OUTPUT_DIR = ROOT / "apps" / "web" / "public" / "competitor-intel"

COMPETITORS = [
    {
        "name": "Sanofi",
        "slug": "sanofi",
        "hq": "Paris, France",
        "localOffice": "Barcelona, Spain",
        "ticker": "EURONEXT: SAN",
        "therapyAreas": ["Immunology", "Vaccines", "Rare disease"],
    },
    {
        "name": "Novartis",
        "slug": "novartis",
        "hq": "Basel, Switzerland",
        "localOffice": "Barcelona, Spain",
        "ticker": "SIX: NOVN",
        "therapyAreas": ["Cardiovascular", "Oncology", "Immunology"],
    },
    {
        "name": "LEO Pharma",
        "slug": "leo-pharma",
        "hq": "Ballerup, Denmark",
        "localOffice": "Sant Cugat del Vallès, Spain",
        "ticker": "Private",
        "therapyAreas": ["Dermatology", "Thrombosis"],
    },
    {
        "name": "Roche",
        "slug": "roche",
        "hq": "Basel, Switzerland",
        "localOffice": "Sant Cugat del Vallès, Spain",
        "ticker": "SIX: ROG",
        "therapyAreas": ["Oncology", "Immunology", "Ophthalmology"],
    },
    {
        "name": "Bayer",
        "slug": "bayer",
        "hq": "Leverkusen, Germany",
        "localOffice": "Sant Joan Despí, Spain",
        "ticker": "ETR: BAYN",
        "therapyAreas": ["Cardiovascular", "Oncology", "Women's health"],
    },
    {
        "name": "Boehringer Ingelheim",
        "slug": "boehringer-ingelheim",
        "hq": "Ingelheim, Germany",
        "localOffice": "Sant Cugat del Vallès, Spain",
        "ticker": "Private",
        "therapyAreas": ["Cardiometabolic", "Oncology", "Respiratory"],
    },
]

app = typer.Typer(help=__doc__, add_completion=False)


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_empty_intel(comp: dict) -> dict:
    """Build a skeleton intel JSON for a competitor to be filled by research."""
    return {
        "company": comp["name"],
        "slug": comp["slug"],
        "lastFullResearch": _now_iso(),
        "lastLightweightUpdate": None,
        "meta": {
            "hq": comp["hq"],
            "localOffice": comp["localOffice"],
            "ticker": comp["ticker"],
            "marketCap": "—",
            "employees": "—",
            "logoUrl": None,
        },
        "overview": {
            "summary": "",
            "keyStrengths": [],
            "threatLevel": "moderate",
            "threatRationale": "",
        },
        "financials": {
            "quarter": "Q1 2026",
            "revenue": "—",
            "revenueGrowth": "—",
            "segments": [],
            "guidance": "—",
            "topDrugs": [],
        },
        "pipeline": [],
        "dermRelevance": [],
        "catalysts": [],
        "updates": [],
    }


async def _research_biomcp(company: str) -> list[dict]:
    """Use BioMCP to search clinical trials for this company in derm."""
    try:
        from biomcp.individual_tools import trial_searcher
    except ImportError:
        typer.echo(f"  [warn] biomcp not installed, skipping trial search for {company}")
        return []

    queries = [
        f"{company} atopic dermatitis",
        f"{company} psoriasis",
        f"{company} dermatology",
    ]
    trials = []
    for q in queries:
        try:
            result = await trial_searcher(query=q, status="RECRUITING")
            text = result if isinstance(result, str) else str(result)
            if "NCT" in text:
                trials.append({"query": q, "raw": text[:2000]})
        except Exception as e:
            typer.echo(f"  [warn] trial_searcher failed for '{q}': {e}")
    return trials


async def _research_company(comp: dict, dry_run: bool = False) -> dict:
    """Research a single company and return structured intel."""
    typer.echo(f"\n{'='*60}")
    typer.echo(f"Researching: {comp['name']}")
    typer.echo(f"{'='*60}")

    intel = _build_empty_intel(comp)

    if dry_run:
        typer.echo("  [dry-run] Would research and write JSON")
        return intel

    # BioMCP clinical trial search
    typer.echo("  [1/2] BioMCP trial search...")
    trial_data = await _research_biomcp(comp["name"])
    if trial_data:
        typer.echo(f"  Found {len(trial_data)} trial result sets")

    # Deep research via disease360 runtime (if available)
    typer.echo("  [2/2] Deep research query...")
    try:
        from disease360_runtime.research.runner import run_research

        query = (
            f"{comp['name']} pharmaceutical company 2026 pipeline financials "
            f"dermatology immunology competitive landscape vs Almirall"
        )
        report = await run_research(query=query, depth="standard")
        if report and hasattr(report, "markdown"):
            intel["overview"]["summary"] = _extract_summary(report.markdown)
            typer.echo(f"  Got research report ({len(report.markdown)} chars)")
        elif isinstance(report, str):
            intel["overview"]["summary"] = _extract_summary(report)
            typer.echo(f"  Got research report ({len(report)} chars)")
    except ImportError:
        typer.echo("  [warn] disease360_runtime not available, using fallback")
    except Exception as e:
        typer.echo(f"  [warn] Deep research failed: {e}")

    return intel


def _extract_summary(markdown: str) -> str:
    """Pull a summary paragraph from a research report."""
    lines = [l.strip() for l in markdown.split("\n") if l.strip() and not l.startswith("#")]
    return " ".join(lines[:5])[:800] if lines else ""


@app.command()
def main(
    company: str = typer.Option(None, "--company", "-c", help="Research a single company"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
):
    """Research Barcelona-area competitors and generate intel JSON files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = COMPETITORS
    if company:
        targets = [c for c in COMPETITORS if c["name"].lower() == company.lower()]
        if not targets:
            typer.echo(f"Unknown company: {company}")
            typer.echo(f"Available: {', '.join(c['name'] for c in COMPETITORS)}")
            raise typer.Exit(1)

    async def _run():
        for comp in targets:
            intel = await _research_company(comp, dry_run=dry_run)
            out_path = OUTPUT_DIR / f"{comp['slug']}.json"
            if not dry_run:
                out_path.write_text(json.dumps(intel, indent=2, ensure_ascii=False), encoding="utf-8")
                typer.echo(f"  -> Wrote {out_path.relative_to(ROOT)}")
            else:
                typer.echo(f"  -> Would write {out_path.relative_to(ROOT)}")

    asyncio.run(_run())
    typer.echo(f"\nDone. {len(targets)} competitor(s) processed.")


if __name__ == "__main__":
    app()
