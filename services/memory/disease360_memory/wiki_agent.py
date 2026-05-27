"""Wiki maintenance agent.

Two-phase write flow:
    plan: ingest_plan / solve_plan / lint  -> IngestPlan (no disk writes)
    apply: apply_plan(plan_id)             -> writes files

Plans live in an in-process dict with a 30-minute TTL. The harness mirrors
the plan into approvals.args at interrupt time so the UI shows the diff.

Ported from `Obsidian-Knowledge-Graphs/backend/wiki_agent.py` — the JSON
prompts are kept compatible with each brain's AGENTS.md schema.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage

from disease360_runtime.llm import get_chat_model

from .registry import Brain
from .schemas import (
    ApplyResult,
    IngestPlan,
    LintIssue,
    LintReport,
    WikiEditOp,
)
from .vault import list_markdown, parse_wikilinks, read_page, write_page

# ---------------------------------------------------------------------------
# Plan store (in-process, 30-minute TTL)
# ---------------------------------------------------------------------------

_PLAN_TTL_SECONDS = 30 * 60
_PLANS: dict[str, tuple[float, IngestPlan]] = {}


def _evict_expired() -> None:
    now = time.time()
    stale = [pid for pid, (exp, _) in _PLANS.items() if exp < now]
    for pid in stale:
        _PLANS.pop(pid, None)


def store_plan(plan: IngestPlan) -> None:
    _evict_expired()
    _PLANS[plan.plan_id] = (time.time() + _PLAN_TTL_SECONDS, plan)


def get_plan(plan_id: str) -> IngestPlan | None:
    _evict_expired()
    item = _PLANS.get(plan_id)
    return item[1] if item else None


def pop_plan(plan_id: str) -> IngestPlan | None:
    _evict_expired()
    item = _PLANS.pop(plan_id, None)
    return item[1] if item else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(raw: str) -> dict:
    """Extract a JSON object from an LLM response that may contain fences."""
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    raise json.JSONDecodeError("Could not extract valid JSON object", text[:200], 0)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _read_or_empty(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _list_existing_pages(brain: Brain) -> list[dict]:
    """Lightweight list of wiki pages: path, title, type."""
    out: list[dict] = []
    for p in list_markdown(brain.wiki_dir):
        rel = p.relative_to(brain.root).as_posix()
        try:
            page = read_page(brain.root, rel)
        except Exception:
            continue
        # type from path: wiki/<type>/...
        parts = rel.split("/")
        ptype = parts[1] if len(parts) > 1 else "page"
        out.append({"path": rel, "title": page.title, "type": ptype, "slug": p.stem})
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=_PLAN_TTL_SECONDS)).isoformat()


async def _llm_json(prompt: str, timeout_s: float = 120.0) -> dict:
    """Run a one-shot JSON-mode generation and return the parsed dict."""
    import asyncio

    model = get_chat_model("chat", temperature=0.2)
    resp = await asyncio.wait_for(
        model.ainvoke([HumanMessage(content=prompt)]),
        timeout=timeout_s,
    )
    raw = resp.content if isinstance(resp.content, str) else "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in resp.content
    )
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Plan builders
# ---------------------------------------------------------------------------


def _result_to_plan(
    brain: Brain,
    kind: str,
    result: dict,
    raw_path: str | None,
) -> IngestPlan:
    """Convert the LLM JSON into an IngestPlan with before/after content."""
    ops: list[WikiEditOp] = []

    # source_summary is treated as a new page
    if "source_summary" in result and isinstance(result["source_summary"], dict):
        ss = result["source_summary"]
        if ss.get("path") and ss.get("content"):
            existing = (brain.root / ss["path"]).is_file()
            ops.append(
                WikiEditOp(
                    kind="update" if existing else "create",
                    path=ss["path"],
                    title=ss.get("title"),
                    before=_read_or_empty(brain.root / ss["path"]) if existing else None,
                    after=ss["content"],
                )
            )

    for page in result.get("new_pages", []) or []:
        if not isinstance(page, dict) or not page.get("path") or not page.get("content"):
            continue
        existing = (brain.root / page["path"]).is_file()
        ops.append(
            WikiEditOp(
                kind="update" if existing else "create",
                path=page["path"],
                title=page.get("title"),
                before=_read_or_empty(brain.root / page["path"]) if existing else None,
                after=page["content"],
            )
        )

    for page in result.get("updated_pages", []) or []:
        if not isinstance(page, dict) or not page.get("path") or not page.get("content"):
            continue
        before = _read_or_empty(brain.root / page["path"])
        ops.append(
            WikiEditOp(
                kind="update",
                path=page["path"],
                title=page.get("title"),
                before=before,
                after=page["content"],
            )
        )

    hot_before = _read_or_empty(brain.hot_path)
    index_before = _read_or_empty(brain.index_path)
    overview_before = _read_or_empty(brain.root / "wiki" / "overview.md")

    hot_after = result.get("hot_md", "") or ""
    index_after = result.get("index_md", "") or ""
    overview_after = result.get("overview_md", "") or ""

    plan = IngestPlan(
        plan_id=str(uuid.uuid4()),
        brain=brain.id,
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_plan(brain: Brain, title: str, content: str) -> IngestPlan:
    """Ask the LLM to propose a full ingest. No disk writes."""
    slug = _slug(title) or "untitled"
    raw_rel = f"raw/{slug}.md"

    hot = _read_or_empty(brain.hot_path)[:4000]
    index = _read_or_empty(brain.index_path)[:4000]
    agents = _read_or_empty(brain.agents_path)[:3000]
    pages = _list_existing_pages(brain)
    existing_list = "\n".join(
        f"- {p['path']} ({p['type']}): {p['title']}" for p in pages[:40]
    )

    prompt = f"""You are the wiki agent for {brain.id}. A new source is being added to {raw_rel}.

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

    # Drop the source file into raw/ now so the path is real for the apply step.
    raw_target = brain.raw_dir / f"{slug}.md"
    raw_target.parent.mkdir(parents=True, exist_ok=True)
    if not raw_target.exists():
        raw_target.write_text(content, encoding="utf-8")

    return _result_to_plan(brain, kind="ingest", result=result, raw_path=raw_rel)


async def lint(brain: Brain) -> LintReport:
    """Read-only health check. Mirrors old WikiAgent.lint()."""
    pages = _list_existing_pages(brain)
    index = _read_or_empty(brain.index_path)
    hot = _read_or_empty(brain.hot_path)

    all_links: set[str] = set()
    inbound: set[str] = set()
    page_bodies: list[str] = []
    slugs = {p["slug"] for p in pages}

    for page in pages:
        try:
            full = read_page(brain.root, page["path"])
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
    orphans = [p["slug"] for p in pages if p["slug"] not in inbound and p["type"] != "overview"]

    pages_summary = "\n".join(page_bodies[:30])

    prompt = f"""You are the wiki agent for {brain.id}. Perform a lint check.

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


async def solve_plan(brain: Brain, issue: LintIssue) -> IngestPlan:
    """Propose edits that resolve a single lint issue. No disk writes."""
    hot = _read_or_empty(brain.hot_path)
    index = _read_or_empty(brain.index_path)
    pages = _list_existing_pages(brain)
    existing_list = "\n".join(
        f"- {p['path']} ({p['type']}): {p['title']}" for p in pages
    )

    prompt = f"""You are the wiki agent for {brain.id}. Solve a single lint issue.

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
    return _result_to_plan(brain, kind="solve", result=result, raw_path=None)


def apply_plan(brain: Brain, plan: IngestPlan, db_path: Path) -> ApplyResult:
    """Replay a plan onto disk. Re-indexes FTS at the end."""
    from . import index_db

    pages_touched: list[str] = []

    for op in plan.ops:
        rel = op.path
        # Parse out frontmatter from the LLM output if present so write_page
        # doesn't double-encode it.
        body, fm = _split_frontmatter(op.after)
        if op.title and "title" not in fm:
            fm["title"] = op.title
        write_page(brain.root, rel, body, fm)
        pages_touched.append(rel)

    if plan.hot_after:
        brain.hot_path.write_text(plan.hot_after, encoding="utf-8")
        pages_touched.append("hot.md")
    if plan.index_after:
        brain.index_path.write_text(plan.index_after, encoding="utf-8")
        pages_touched.append("index.md")
    if plan.overview_after:
        ovw = brain.root / "wiki" / "overview.md"
        ovw.parent.mkdir(parents=True, exist_ok=True)
        ovw.write_text(plan.overview_after, encoding="utf-8")
        pages_touched.append("wiki/overview.md")
    if plan.log_entry:
        existing = _read_or_empty(brain.log_path) or "# Log\n"
        sep = "" if existing.endswith("\n") else "\n"
        brain.log_path.write_text(
            f"{existing}{sep}{plan.log_entry.rstrip()}\n", encoding="utf-8"
        )
        pages_touched.append("log.md")

    # Reindex FTS so search picks up the new pages immediately.
    try:
        index_db.reindex(brain, db_path)
    except Exception:
        pass

    pop_plan(plan.plan_id)
    return ApplyResult(
        ok=True,
        plan_id=plan.plan_id,
        pages_touched=pages_touched,
        summary=plan.summary,
    )


def _split_frontmatter(text: str) -> tuple[str, dict]:
    """If `text` starts with a YAML frontmatter block, parse and remove it."""
    import frontmatter

    try:
        post = frontmatter.loads(text)
        return post.content, dict(post.metadata) if post.metadata else {}
    except Exception:
        return text, {}
