"""Postgres-backed wiki maintenance agent (ADR 0001 phase 2.5).

Mirrors `wiki_agent.{ingest_plan, lint, solve_plan, apply_plan}` but
reads/writes Postgres rows instead of disk. The plan store
(`_PLANS`, `store_plan`, `get_plan`, `pop_plan`), the JSON extractor,
and the LLM call are reused from the disk implementation — they don't
care about the storage substrate.

Two-phase write flow is preserved:
    plan: ingest_plan / solve_plan / lint  -> IngestPlan (no DB writes)
    apply: apply_plan(plan_id)             -> writes pages/hot/index/log

`apply_plan` is async here because vault_pg writes are async. Callers in
the harness already `await` plan-application paths via the route, so
this is a clean swap.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from .schemas import (
    ApplyResult,
    IngestPlan,
    LintIssue,
    LintReport,
    WikiEditOp,
)
from .vault_pg import (
    list_pages,
    read_agents_md,
    read_hot,
    read_index_md,
    read_page,
    write_hot,
    write_index_md,
    write_page,
)
from .wiki_agent import (
    _PLAN_TTL_SECONDS,  # noqa: F401 — re-export for callers expecting it
    _extract_json,
    _llm_json,
    _now_iso,
    _slug,
    get_plan,
    pop_plan,
    store_plan,
)

__all__ = [
    "ingest_plan",
    "lint",
    "solve_plan",
    "apply_plan",
    "get_plan",
    "pop_plan",
    "store_plan",
]


def _expires_iso() -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=_PLAN_TTL_SECONDS)).isoformat()


# --- Plan builders ---------------------------------------------------------


async def _read_existing(tenant_id: str, brain_id: str, path: str) -> str:
    try:
        page = await read_page(tenant_id, brain_id, path)
    except FileNotFoundError:
        return ""
    return page.body


async def _result_to_plan(
    tenant_id: str,
    brain_id: str,
    brain_name: str,
    kind: str,
    result: dict,
    raw_path: str | None,
) -> IngestPlan:
    """Convert the LLM JSON into an IngestPlan with before/after content."""
    ops: list[WikiEditOp] = []

    if "source_summary" in result and isinstance(result["source_summary"], dict):
        ss = result["source_summary"]
        if ss.get("path") and ss.get("content"):
            before = await _read_existing(tenant_id, brain_id, ss["path"])
            ops.append(
                WikiEditOp(
                    kind="update" if before else "create",
                    path=ss["path"],
                    title=ss.get("title"),
                    before=before or None,
                    after=ss["content"],
                )
            )

    for page in result.get("new_pages", []) or []:
        if not isinstance(page, dict) or not page.get("path") or not page.get("content"):
            continue
        before = await _read_existing(tenant_id, brain_id, page["path"])
        ops.append(
            WikiEditOp(
                kind="update" if before else "create",
                path=page["path"],
                title=page.get("title"),
                before=before or None,
                after=page["content"],
            )
        )

    for page in result.get("updated_pages", []) or []:
        if not isinstance(page, dict) or not page.get("path") or not page.get("content"):
            continue
        before = await _read_existing(tenant_id, brain_id, page["path"])
        ops.append(
            WikiEditOp(
                kind="update",
                path=page["path"],
                title=page.get("title"),
                before=before,
                after=page["content"],
            )
        )

    hot_before = await read_hot(tenant_id, brain_id)
    index_before = await read_index_md(tenant_id, brain_id)
    overview_before = await _read_existing(tenant_id, brain_id, "wiki/overview.md")

    hot_after = result.get("hot_md", "") or ""
    index_after = result.get("index_md", "") or ""
    overview_after = result.get("overview_md", "") or ""

    plan = IngestPlan(
        plan_id=str(uuid.uuid4()),
        brain=brain_name,
        kind=kind,
        summary=result.get("summary", "") or "",
        ops=ops,
        hot_before=hot_before,
        hot_after=hot_after if hot_after and hot_after != hot_before else "",
        index_before=index_before,
        index_after=index_after if index_after and index_after != index_before else "",
        overview_before=overview_before,
        overview_after=(
            overview_after if overview_after and overview_after != overview_before else ""
        ),
        log_entry=result.get("log_entry", "") or "",
        raw_path=raw_path,
        created_at=_now_iso(),
        expires_at=_expires_iso(),
    )
    store_plan(plan)
    return plan


# --- Public API ------------------------------------------------------------


async def ingest_plan(
    tenant_id: str, brain_id: str, brain_name: str, title: str, content: str
) -> IngestPlan:
    """Propose a full ingest. Drops the source into raw_captures so the apply step has it."""
    from .vault_pg import ingest_raw

    slug = _slug(title) or "untitled"
    raw_rel = f"raw/{slug}.md"

    hot = (await read_hot(tenant_id, brain_id))[:4000]
    index = (await read_index_md(tenant_id, brain_id))[:4000]
    agents = (await read_agents_md(tenant_id, brain_id))[:3000]
    pages = await list_pages(tenant_id, brain_id)
    existing_list = "\n".join(
        f"- {p['path']} ({_type_from_path(p['path'])}): {p['title']}" for p in pages[:40]
    )

    prompt = f"""You are the wiki agent for {brain_name}. A new source is being added to {raw_rel}.

CURRENT STATE:
- hot.md:
{hot}

- index.md:
{index}

- AGENTS.md (schema rules — follow strictly):
{agents}

- Existing wiki pages ({len(pages)} total, showing first 40):
{existing_list or "(none)"}

SOURCE TITLE: {title}
SOURCE CONTENT:
{content[:6000]}

YOUR TASK: propose the SMALLEST useful ingest. Return ONLY valid JSON (no markdown fences) matching:
{{
  "source_summary": {{
    "path": "wiki/sources/{slug}.md",
    "title": "...",
    "content": "full markdown content with frontmatter"
  }} OR null if the source is too small / personal to deserve a source page,
  "new_pages": [
    {{ "path": "wiki/concepts/<slug>.md or wiki/entities/<slug>.md", "title": "...", "content": "full markdown with frontmatter" }}
  ],
  "updated_pages": [
    {{ "path": "wiki/concepts/<existing>.md", "title": "...", "content": "full updated markdown" }}
  ],
  "index_md":    "" if index.md does not need to change, ELSE full updated index.md content,
  "hot_md":      "" if hot.md does not need to change, ELSE full updated hot.md content,
  "overview_md": "" (ALWAYS leave empty — never rewrite overview for a single ingest),
  "log_entry": "## [{date.today().isoformat()}] ingest | {title} ...",
  "summary": "one-sentence human-readable summary of what this plan does"
}}

CRITICAL OUTPUT RULES — violating these causes timeouts:
- ALWAYS set "overview_md" to "". Never rewrite it.
- ALWAYS set "hot_md" to "" unless the source is genuinely breaking/urgent news.
- ALWAYS set "index_md" to "" unless you are adding a brand new page that must be listed.
- When you DO set "index_md", output ONLY the updated index — do not pad or repeat unchanged sections verbatim if the index is large.
- Keep page content SHORT and factual. A typical entity page is 10-30 lines.
- Prefer ONE new/updated page over many. A single fact = one entity page + maybe an index line.

General rules:
- Be conservative. A single short fact often only needs ONE updated_pages entry — not a source summary, overview rewrite, and 5 new pages.
- Do NOT create source pages for tiny personal notes or single facts.
- Follow AGENTS.md conventions for frontmatter, filenames, wikilinks, writing style.
- Use [[wikilinks]] between pages.
- Do NOT invent facts not in the source.
- Today's date: {date.today().isoformat()}.
"""

    result = await _llm_json(prompt)

    # Drop the source into raw_captures so the apply step has it persisted
    # before the user even approves. Mirrors disk-side raw/<slug>.md write.
    try:
        await ingest_raw(tenant_id, brain_id, f"{slug}.md", content)
    except Exception:
        # Already exists or DB hiccup — non-fatal for plan generation.
        pass

    return await _result_to_plan(
        tenant_id, brain_id, brain_name, kind="ingest", result=result, raw_path=raw_rel
    )


async def lint(tenant_id: str, brain_id: str, brain_name: str) -> LintReport:
    """Read-only health check."""
    from .vault import parse_wikilinks

    pages = await list_pages(tenant_id, brain_id)
    index = await read_index_md(tenant_id, brain_id)
    hot = await read_hot(tenant_id, brain_id)

    all_links: set[str] = set()
    inbound: set[str] = set()
    page_bodies: list[str] = []
    slugs = {_slug_from_path(p["path"]) for p in pages}

    for page in pages:
        try:
            full = await read_page(tenant_id, brain_id, page["path"])
        except Exception:
            continue
        page_bodies.append(f"## {page['path']}\n{full.body[:2000]}")
        for link in parse_wikilinks(full.body):
            target = link.target.lower().replace(" ", "-")
            if "/" in target:
                target = target.split("/")[-1]
            all_links.add(target)
            inbound.add(target)

    missing_pages = [
        link for link in all_links if link not in slugs and link not in ("index", "log")
    ]
    orphans = [
        _slug_from_path(p["path"])
        for p in pages
        if _slug_from_path(p["path"]) not in inbound
        and _type_from_path(p["path"]) != "overview"
    ]

    pages_summary = "\n".join(page_bodies[:30])

    prompt = f"""You are the wiki agent for {brain_name}. Perform a lint check.

CURRENT STATE:
- hot.md:
{hot}

- index.md:
{index}

- Total pages: {len(pages)}
- Missing pages (linked but don't exist): {json.dumps(missing_pages[:20])}
- Orphan pages (no inbound links): {json.dumps(orphans[:20])}

PAGE CONTENTS (truncated):
{pages_summary[:8000]}

Check for:
1. Contradictions between pages
2. Stale content superseded by newer sources
3. Orphan pages with no inbound links
4. Missing pages (concepts/entities linked but no page exists)
5. Sparse pages that could be expanded
6. Missing cross-references
7. Index drift (pages that exist but aren't in index.md)
8. Data gaps

Return ONLY valid JSON (no fences):
{{
  "issues": [
    {{ "type": "contradiction|stale|orphan|missing_page|sparse|missing_xref|index_drift|data_gap",
       "severity": "high|medium|low",
       "description": "...",
       "page": "affected slug or path",
       "suggestion": "how to fix" }}
  ],
  "summary": "brief overall health assessment"
}}
"""

    try:
        result = await _llm_json(prompt)
    except Exception as e:  # noqa: BLE001
        return LintReport(
            issues=[],
            summary=f"Lint LLM call failed: {e}",
            stats={
                "total_pages": len(pages),
                "orphans": len(orphans),
                "missing_pages": len(missing_pages),
            },
        )

    issues_raw = result.get("issues", []) or []
    issues: list[LintIssue] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            continue
        try:
            issues.append(
                LintIssue(
                    type=item.get("type", "data_gap"),
                    severity=item.get("severity", "medium"),
                    description=item.get("description", ""),
                    page=item.get("page", "") or "",
                    suggestion=item.get("suggestion", "") or "",
                )
            )
        except Exception:
            continue

    return LintReport(
        issues=issues,
        summary=result.get("summary", ""),
        stats={
            "total_pages": len(pages),
            "orphans": len(orphans),
            "missing_pages": len(missing_pages),
        },
    )


async def solve_plan(
    tenant_id: str, brain_id: str, brain_name: str, issue: LintIssue
) -> IngestPlan:
    """Propose edits that resolve a single lint issue."""
    hot = await read_hot(tenant_id, brain_id)
    index = await read_index_md(tenant_id, brain_id)
    pages = await list_pages(tenant_id, brain_id)
    existing_list = "\n".join(
        f"- {p['path']} ({_type_from_path(p['path'])}): {p['title']}" for p in pages
    )

    prompt = f"""You are the wiki agent for {brain_name}. Solve a single lint issue.

CURRENT STATE:
- hot.md:
{hot}

- index.md:
{index}

- Existing pages:
{existing_list or "(none)"}

ISSUE:
- type: {issue.type}
- severity: {issue.severity}
- page: {issue.page}
- description: {issue.description}
- suggestion: {issue.suggestion}

Propose the smallest set of edits that fixes this issue. Return ONLY valid JSON:
{{
  "new_pages":     [{{ "path": "...", "title": "...", "content": "..." }}],
  "updated_pages": [{{ "path": "...", "title": "...", "content": "..." }}],
  "index_md":      "full updated index.md if it changes, else empty string",
  "hot_md":        "full updated hot.md if it changes, else empty string",
  "overview_md":   "full updated wiki/overview.md if it changes, else empty string",
  "log_entry":     "## [{date.today().isoformat()}] solve | {issue.type} | <page> ...",
  "summary":       "one-sentence summary of the fix"
}}

Rules: do not invent facts; cite via [[wikilinks]]; follow AGENTS.md style.
Today's date: {date.today().isoformat()}.
"""

    result = await _llm_json(prompt)
    return await _result_to_plan(
        tenant_id, brain_id, brain_name, kind="solve", result=result, raw_path=None
    )


async def apply_plan(
    tenant_id: str, brain_id: str, plan: IngestPlan
) -> ApplyResult:
    """Replay a plan onto Postgres rows. tsvector + GIN handle the FTS refresh."""
    pages_touched: list[str] = []

    for op in plan.ops:
        body, fm = _split_frontmatter(op.after)
        if op.title and "title" not in fm:
            fm["title"] = op.title
        await write_page(tenant_id, brain_id, op.path, body, fm)
        pages_touched.append(op.path)

    if plan.hot_after:
        await write_hot(tenant_id, brain_id, plan.hot_after)
        pages_touched.append("hot.md")
    if plan.index_after:
        await write_index_md(tenant_id, brain_id, plan.index_after)
        pages_touched.append("index.md")
    if plan.overview_after:
        await write_page(
            tenant_id,
            brain_id,
            "wiki/overview.md",
            plan.overview_after,
            fm=None,
        )
        pages_touched.append("wiki/overview.md")
    if plan.log_entry:
        # Append the log entry as a wiki page named `log.md` at the brain root.
        # On disk this lived at brain.log_path; in Postgres it's a regular page.
        existing = await _read_existing(tenant_id, brain_id, "log.md") or "# Log\n"
        sep = "" if existing.endswith("\n") else "\n"
        new_log = f"{existing}{sep}{plan.log_entry.rstrip()}\n"
        await write_page(tenant_id, brain_id, "log.md", new_log, fm=None)
        pages_touched.append("log.md")

    pop_plan(plan.plan_id)
    return ApplyResult(
        ok=True,
        plan_id=plan.plan_id,
        pages_touched=pages_touched,
        summary=plan.summary,
    )


# --- helpers ---------------------------------------------------------------


def _split_frontmatter(text: str) -> tuple[str, dict]:
    """If `text` starts with a YAML frontmatter block, parse and remove it."""
    import frontmatter

    try:
        post = frontmatter.loads(text)
        return post.content, dict(post.metadata) if post.metadata else {}
    except Exception:
        return text, {}


def _type_from_path(path: str) -> str:
    """`wiki/<type>/...` → `<type>` for prompt context."""
    parts = path.split("/")
    return parts[1] if len(parts) > 1 else "page"


def _slug_from_path(path: str) -> str:
    stem = path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[:-3]
    return stem
