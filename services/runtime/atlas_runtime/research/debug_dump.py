"""Env-flagged forensic dump for a deep research run.

Off by default. When ``DISEASE360_RESEARCH_DEBUG_DUMP`` is set to a truthy value,
``dump_run`` writes a self-contained folder under
``services/harness/data/research_debug/`` capturing every artifact a future
diagnostic session might need: VFS files, classification, citations + NLI
verdicts, tool-invocation counters, per-stage timings, and the final report.

A dump failure must never break the research run — the caller is expected
to wrap ``dump_run`` in try/except.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas_runtime.config import get, repo_root

from .filesystem import VirtualFS
from .state import Citation, Classification, VerificationReport

log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def is_dump_enabled() -> bool:
    val = get("DISEASE360_RESEARCH_DEBUG_DUMP")
    if not val:
        return False
    return val.strip().lower() not in {"0", "false", "no", "off", ""}


def _slug(text: str, *, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len] or "query"


def _dump_root() -> Path:
    return repo_root() / "services" / "harness" / "data" / "research_debug"


def dump_run(
    *,
    run_id: str,
    query: str,
    depth_tier: str,
    vfs: VirtualFS,
    classification: Classification | None,
    citations: list[Citation],
    verification: VerificationReport,
    markdown: str,
    tool_invocations: dict[str, int],
    timings: dict[str, float],
    started_at: datetime,
    completed_at: datetime,
    tokens_used: dict[str, int] | None = None,
    budget_ceiling: int | None = None,
) -> Path:
    """Write the run's forensic artifacts to a timestamped folder.

    Returns the dump folder path. Raises on filesystem errors — callers are
    responsible for swallowing exceptions if a dump failure should not break
    the run.
    """
    timestamp = started_at.strftime("%Y%m%d-%H%M%S")
    folder = _dump_root() / f"{timestamp}_{run_id}_{_slug(query)}"
    folder.mkdir(parents=True, exist_ok=True)

    verdict_counts: dict[str, int] = {}
    for c in citations:
        verdict_counts[c.nli_verdict] = verdict_counts.get(c.nli_verdict, 0) + 1

    meta: dict[str, Any] = {
        "run_id": run_id,
        "query": query,
        "depth_tier": depth_tier,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": (completed_at - started_at).total_seconds(),
        "tool_invocations": dict(tool_invocations),
        "timings_seconds": dict(timings),
        "classification": classification.model_dump(mode="json") if classification else None,
        "verification_summary": {
            "total_citations": verification.total_citations,
            "entails": verdict_counts.get("entails", 0),
            "not_mentioned": verdict_counts.get("not_mentioned", 0),
            "contradicts": verdict_counts.get("contradicts", 0),
            "unchecked": verdict_counts.get("unchecked", 0),
            "dead_urls": len(verification.dead_urls),
            "wayback_substituted": len(verification.wayback_substituted),
            "hallucinated_urls": len(verification.hallucinated_urls),
        },
        "vfs_files": list(vfs.files.keys()),
        "tokens_used": dict(tokens_used) if tokens_used else {},
        "budget_ceiling": budget_ceiling,
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for path, content in vfs.files.items():
        # path looks like "/brief.md" or "/findings_x.md"
        name = path.lstrip("/")
        if not name:
            continue
        out = folder / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    citations_payload = [c.model_dump(mode="json") for c in citations]
    (folder / "citations.json").write_text(
        json.dumps(citations_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    (folder / "report.md").write_text(markdown or "(empty)", encoding="utf-8")

    log.info("[research] debug dump written to %s", folder)
    return folder
