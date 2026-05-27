"""Download PubMed articles and ClinicalTrials.gov trials via biomcp-python
and store them as raw captures in the BioMCP Brain vault.

Recurring, manual trigger. Filename-based dedup: existing files are skipped.
Each failed item is retried once before being reported. Rate-limited to stay
under PubMed's unauthenticated 3 req/s ceiling.

Usage:

# Full run — both conditions, 50 items each
uv run python scripts/fetch_biomcp.py

# Custom conditions or limit
uv run python scripts/fetch_biomcp.py -c "atopic dermatitis" --limit 25

# Preview without writing
uv run python scripts/fetch_biomcp.py --dry-run
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import typer
import yaml

ROOT = Path(__file__).resolve().parent.parent
for _sub in ("services/runtime", "services/memory"):
    sys.path.insert(0, str(ROOT / _sub))

from disease360_memory.registry import DEFAULT_TENANT_ID, Brain, tenant_root  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────────────────

BRAIN_NAME = "BioMCP Brain"
DEFAULT_CONDITIONS: list[str] = ["atopic dermatitis", "hidradenitis suppurativa"]
DEFAULT_LIMIT = 50
RATE_SLEEP = 0.4   # seconds between requests — keeps us under 3 req/s (PubMed free tier)
RETRY_SLEEP = 2.0  # extra wait before a single retry attempt

app = typer.Typer(help=__doc__, add_completion=False)

# ── BioMCP imports ─────────────────────────────────────────────────────────────
# biomcp-python 0.7.3: all individual async tool functions live in individual_tools.

try:
    from biomcp.individual_tools import (
        article_getter,
        article_searcher,
        trial_getter,
        trial_searcher,
    )
except ImportError as exc:
    typer.echo(
        f"[error] Cannot import biomcp. Install it with:\n"
        f"    pip install biomcp-python==0.7.3\n"
        f"Detail: {exc}",
        err=True,
    )
    sys.exit(2)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


def _coerce_str(result: object) -> str:
    """Normalise a biomcp return value to plain text.

    biomcp tools may return a bare string, a list of MCP TextContent objects,
    or a single TextContent object depending on the version and call path.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts: list[str] = []
        for item in result:
            parts.append(item.text if hasattr(item, "text") else str(item))
        return "\n".join(parts)
    if hasattr(result, "text"):
        return result.text  # type: ignore[union-attr]
    return str(result)


async def _call(fn, *args, **kwargs) -> str:
    """Await a biomcp async tool function and normalise its return value."""
    return _coerce_str(await fn(*args, **kwargs))


def _extract_pmids(text: str) -> list[str]:
    """Pull PubMed IDs from biomcp search output.

    Tries explicit 'PMID: 12345678' tags first; falls back to any standalone
    7-or-8-digit number so we survive minor format changes.
    """
    hits = re.findall(r"(?i)pmid[:\s#*]*(\d{7,8})", text)
    if not hits:
        hits = re.findall(r"\b(\d{7,8})\b", text)
    return list(dict.fromkeys(hits))  # preserve order, deduplicate


def _extract_nct_ids(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"NCT\d{8}", text)))


def _wrap_frontmatter(meta: dict, body: str) -> str:
    fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{fm}\n---\n\n{body.strip()}\n"


def _article_md(pmid: str, detail: str, condition: str) -> str:
    return _wrap_frontmatter(
        {
            "pmid": pmid,
            "condition": condition,
            "source": "biomcp-python",
            "tags": ["raw", "pubmed", _slug(condition)],
            "fetched": _now_iso(),
        },
        detail,
    )


def _trial_md(nct_id: str, detail: str, condition: str) -> str:
    return _wrap_frontmatter(
        {
            "nct_id": nct_id,
            "condition": condition,
            "source": "biomcp-python",
            "tags": ["raw", "clinical-trial", _slug(condition)],
            "fetched": _now_iso(),
        },
        detail,
    )


# ── biomcp call wrappers ────────────────────────────────────────────────────────
# article_searcher: page_size controls result count (max 100 per page).
# article_getter:   pmid is a string identifier.
# trial_searcher:   page_size controls result count.
# trial_getter:     nct_id only — returns all sections in one call.


async def _search_articles(condition: str, limit: int) -> str:
    return await _call(article_searcher, diseases=[condition], page_size=min(limit, 100))


async def _get_article(pmid: str) -> str:
    return await _call(article_getter, pmid=pmid)


async def _search_trials(condition: str, limit: int) -> str:
    return await _call(trial_searcher, conditions=[condition], page_size=min(limit, 100))


async def _get_trial(nct_id: str) -> str:
    return await _call(trial_getter, nct_id=nct_id)


# ── Stats ──────────────────────────────────────────────────────────────────────


@dataclass
class RunStats:
    articles_written: int = 0
    articles_skipped: int = 0
    articles_failed: list[str] = field(default_factory=list)
    trials_written: int = 0
    trials_skipped: int = 0
    trials_failed: list[str] = field(default_factory=list)


# ── Pipeline steps ─────────────────────────────────────────────────────────────


async def _process_articles(
    condition: str,
    limit: int,
    raw_dir: Path,
    dry_run: bool,
    stats: RunStats,
) -> list[str]:
    """Search + fetch articles for one condition. Returns list of failed PMIDs."""
    typer.echo(f"\n  [articles] searching '{condition}' (limit={limit})...")
    try:
        search_text = await _search_articles(condition, limit)
    except Exception as exc:
        typer.echo(f"  [error] article search failed: {exc}", err=True)
        return []

    pmids = _extract_pmids(search_text)[:limit]
    typer.echo(f"  [articles] {len(pmids)} PMIDs found")

    failed: list[str] = []
    for pmid in pmids:
        filename = f"PMID-{pmid}.md"
        dest = raw_dir / filename
        if dest.exists():
            typer.echo(f"  [skip]     {filename}")
            stats.articles_skipped += 1
            continue
        if dry_run:
            typer.echo(f"  [dry-run]  would write {filename}")
            stats.articles_written += 1
            continue
        try:
            time.sleep(RATE_SLEEP)
            detail = await _get_article(pmid)
            dest.write_text(_article_md(pmid, detail, condition), encoding="utf-8")
            typer.echo(f"  [ok]       {filename}")
            stats.articles_written += 1
        except Exception as exc:
            typer.echo(f"  [fail]     PMID-{pmid}: {exc}", err=True)
            failed.append(pmid)

    return failed


async def _process_trials(
    condition: str,
    limit: int,
    raw_dir: Path,
    dry_run: bool,
    stats: RunStats,
) -> list[str]:
    """Search + fetch trials for one condition. Returns list of failed NCT IDs."""
    typer.echo(f"\n  [trials]   searching '{condition}' (limit={limit})...")
    try:
        search_text = await _search_trials(condition, limit)
    except Exception as exc:
        typer.echo(f"  [error] trial search failed: {exc}", err=True)
        return []

    nct_ids = _extract_nct_ids(search_text)[:limit]
    typer.echo(f"  [trials]   {len(nct_ids)} NCT IDs found")

    failed: list[str] = []
    for nct_id in nct_ids:
        filename = f"{nct_id}.md"
        dest = raw_dir / filename
        if dest.exists():
            typer.echo(f"  [skip]     {filename}")
            stats.trials_skipped += 1
            continue
        if dry_run:
            typer.echo(f"  [dry-run]  would write {filename}")
            stats.trials_written += 1
            continue
        try:
            time.sleep(RATE_SLEEP)
            detail = await _get_trial(nct_id)
            dest.write_text(_trial_md(nct_id, detail, condition), encoding="utf-8")
            typer.echo(f"  [ok]       {filename}")
            stats.trials_written += 1
        except Exception as exc:
            typer.echo(f"  [fail]     {nct_id}: {exc}", err=True)
            failed.append(nct_id)

    return failed


async def _retry_articles(
    failed: list[str], condition: str, raw_dir: Path, stats: RunStats
) -> None:
    if not failed:
        return
    typer.echo(f"\n  [retry]    {len(failed)} failed article(s)...")
    still_failed: list[str] = []
    for pmid in failed:
        filename = f"PMID-{pmid}.md"
        dest = raw_dir / filename
        try:
            time.sleep(RETRY_SLEEP)
            detail = await _get_article(pmid)
            dest.write_text(_article_md(pmid, detail, condition), encoding="utf-8")
            typer.echo(f"  [retry ok] {filename}")
            stats.articles_written += 1
        except Exception as exc:
            typer.echo(f"  [retry fail] PMID-{pmid}: {exc}", err=True)
            still_failed.append(pmid)
    stats.articles_failed.extend(still_failed)


async def _retry_trials(
    failed: list[str], condition: str, raw_dir: Path, stats: RunStats
) -> None:
    if not failed:
        return
    typer.echo(f"\n  [retry]    {len(failed)} failed trial(s)...")
    still_failed: list[str] = []
    for nct_id in failed:
        filename = f"{nct_id}.md"
        dest = raw_dir / filename
        try:
            time.sleep(RETRY_SLEEP)
            detail = await _get_trial(nct_id)
            dest.write_text(_trial_md(nct_id, detail, condition), encoding="utf-8")
            typer.echo(f"  [retry ok] {filename}")
            stats.trials_written += 1
        except Exception as exc:
            typer.echo(f"  [retry fail] {nct_id}: {exc}", err=True)
            still_failed.append(nct_id)
    stats.trials_failed.extend(still_failed)


# ── Entry point ────────────────────────────────────────────────────────────────


async def _run(conditions: list[str], limit: int, dry_run: bool) -> int:
    brain_root = tenant_root(DEFAULT_TENANT_ID) / BRAIN_NAME
    brain = Brain(id=BRAIN_NAME, root=brain_root, tenant_id=DEFAULT_TENANT_ID)

    if dry_run:
        typer.echo(f"[dry-run] Brain would be bootstrapped at: {brain_root}")
    else:
        brain.ensure_layout()
        typer.echo(f"Brain: {brain_root}")

    raw_dir = brain.raw_dir
    stats = RunStats()

    for condition in conditions:
        bar = "=" * 60
        typer.echo(f"\n{bar}\nCondition: {condition}\n{bar}")

        article_failures = await _process_articles(condition, limit, raw_dir, dry_run, stats)
        await _retry_articles(article_failures, condition, raw_dir, stats)

        trial_failures = await _process_trials(condition, limit, raw_dir, dry_run, stats)
        await _retry_trials(trial_failures, condition, raw_dir, stats)

    bar = "=" * 60
    typer.echo(f"\n{bar}\nSummary\n{bar}")
    typer.echo(f"Articles written : {stats.articles_written}")
    typer.echo(f"Articles skipped : {stats.articles_skipped}  (already in raw/)")
    typer.echo(f"Trials written   : {stats.trials_written}")
    typer.echo(f"Trials skipped   : {stats.trials_skipped}  (already in raw/)")

    if stats.articles_failed:
        typer.echo(
            f"Articles failed  : {len(stats.articles_failed)} — {stats.articles_failed}",
            err=True,
        )
    if stats.trials_failed:
        typer.echo(
            f"Trials failed    : {len(stats.trials_failed)} — {stats.trials_failed}",
            err=True,
        )

    return 1 if (stats.articles_failed or stats.trials_failed) else 0


@app.command()
def main(
    condition: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--condition",
        "-c",
        help=(
            "Disease condition to search. Repeatable. "
            "Defaults to 'atopic dermatitis' and 'hidradenitis suppurativa'."
        ),
    ),
    limit: int = typer.Option(
        DEFAULT_LIMIT,
        "--limit",
        "-l",
        help="Max items per entity type per condition.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be written without touching disk.",
    ),
) -> None:
    conditions = list(condition) if condition else DEFAULT_CONDITIONS
    sys.exit(asyncio.run(_run(conditions, limit, dry_run)))


if __name__ == "__main__":
    app()
