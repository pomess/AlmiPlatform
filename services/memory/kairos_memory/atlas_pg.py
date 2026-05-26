"""Postgres-backed knowledge atlas (ADR 0001 phase 2.5).

Mirrors `atlas.build_atlas` but reads pages from the database instead of
the filesystem. Cache key is `<tenant_id>/<brain_id>` (UUID); invalidation
is keyed by brain UUID. The atlas drives the system-prompt context
section so the agent can pre-route to the right brain without a search
round-trip.

Cache freshness uses the brain's max(updated_at) across pages and the
brain row itself, taken in a single query.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from .db import acquire

MAX_ENTITIES_PER_BRAIN = 12
MAX_CONCEPTS_PER_BRAIN = 8
BLURB_CHAR_LIMIT = 140


@dataclass
class _CacheEntry:
    mtime_ns: int  # truncated to int for cmp
    payload: dict


_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(tenant_id: str, brain_id: str) -> str:
    return f"{tenant_id}/{brain_id}"


def invalidate(tenant_id: str, brain_id: str | None = None) -> None:
    """Drop the cached atlas for this tenant. brain_id=None clears all of theirs."""
    with _CACHE_LOCK:
        if brain_id is None:
            for key in list(_CACHE):
                if key.startswith(f"{tenant_id}/"):
                    _CACHE.pop(key, None)
        else:
            _CACHE.pop(_cache_key(tenant_id, brain_id), None)


async def build_atlas(tenant_id: str) -> dict:
    out: list[dict] = []
    async with acquire() as c:
        brains = await c.fetch(
            """
            select id::text as id, name, updated_at
              from public.brains
             where tenant_id = $1
             order by name
            """,
            tenant_id,
        )
    for b in brains:
        out.append(await _brain_atlas(tenant_id, b["id"], b["name"], b["updated_at"]))
    return {"brains": out}


async def _brain_atlas(
    tenant_id: str, brain_id: str, brain_name: str, brain_updated: object
) -> dict:
    latest = await _max_updated_at(tenant_id, brain_id, fallback=brain_updated)
    key = _cache_key(tenant_id, brain_id)
    latest_ns = _to_ns(latest)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached.mtime_ns >= latest_ns:
            return cached.payload

    payload = await _compute_brain_atlas(tenant_id, brain_id, brain_name, latest)

    with _CACHE_LOCK:
        _CACHE[key] = _CacheEntry(mtime_ns=latest_ns, payload=payload)
    return payload


async def _max_updated_at(tenant_id: str, brain_id: str, fallback) -> object:
    async with acquire() as c:
        row = await c.fetchrow(
            """
            select coalesce(max(updated_at), $3) as latest, count(*)::int as n
              from public.pages
             where tenant_id = $1 and brain_id = $2
            """,
            tenant_id,
            brain_id,
            fallback,
        )
    return row["latest"] if row else fallback


async def _compute_brain_atlas(
    tenant_id: str, brain_id: str, brain_name: str, latest
) -> dict:
    purpose = await _read_purpose(tenant_id, brain_id, brain_name)
    entities = await _collect_pages(tenant_id, brain_id, "wiki/entities/", MAX_ENTITIES_PER_BRAIN)
    concepts = await _collect_pages(tenant_id, brain_id, "wiki/concepts/", MAX_CONCEPTS_PER_BRAIN)
    async with acquire() as c:
        page_count = await c.fetchval(
            "select count(*) from public.pages where tenant_id = $1 and brain_id = $2",
            tenant_id,
            brain_id,
        )
    return {
        "id": brain_name,
        "purpose": purpose,
        "page_count": int(page_count or 0),
        "key_entities": entities,
        "key_concepts": concepts,
        "updated_at": latest.isoformat() if hasattr(latest, "isoformat") else None,
    }


async def _read_purpose(tenant_id: str, brain_id: str, brain_name: str) -> str:
    """Use frontmatter.purpose on wiki/overview.md, else first paragraph, else brain name."""
    async with acquire() as c:
        row = await c.fetchrow(
            """
            select frontmatter, body
              from public.pages
             where tenant_id = $1 and brain_id = $2 and path = 'wiki/overview.md'
            """,
            tenant_id,
            brain_id,
        )
    if row is None:
        return brain_name
    fm = row["frontmatter"]
    fm_purpose = None
    if isinstance(fm, dict):
        fm_purpose = fm.get("purpose")
    elif isinstance(fm, str):
        import json
        try:
            fm_purpose = json.loads(fm).get("purpose")
        except json.JSONDecodeError:
            fm_purpose = None
    if isinstance(fm_purpose, str) and fm_purpose.strip():
        return fm_purpose.strip()
    for raw_para in (row["body"] or "").split("\n\n"):
        para = raw_para.strip()
        if not para or para.startswith("#"):
            continue
        return _truncate(_strip_wikilinks(para), 200)
    return brain_name


async def _collect_pages(
    tenant_id: str, brain_id: str, path_prefix: str, cap: int
) -> list[dict]:
    """Return up to `cap` `{title, blurb, path}` records from a path-prefix slice."""
    async with acquire() as c:
        rows = await c.fetch(
            """
            select path, title, body
              from public.pages
             where tenant_id = $1 and brain_id = $2 and path like $3
             order by updated_at desc
             limit $4
            """,
            tenant_id,
            brain_id,
            f"{path_prefix}%",
            cap,
        )
    out: list[dict] = []
    for r in rows:
        blurb = _first_paragraph(r["body"] or "")
        out.append(
            {
                "title": r["title"],
                "blurb": _truncate(blurb, BLURB_CHAR_LIMIT),
                "path": r["path"],
            }
        )
    return out


def _first_paragraph(body: str) -> str:
    for raw_para in body.split("\n\n"):
        para = raw_para.strip()
        if not para or para.startswith("#") or para.startswith("---"):
            continue
        return _strip_wikilinks(para)
    return ""


_WIKILINK_INLINE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")


def _strip_wikilinks(text: str) -> str:
    def _sub(m):
        return (m.group(2) or m.group(1)).strip()

    return _WIKILINK_INLINE.sub(_sub, text).replace("\n", " ").strip()


def _truncate(s: str, limit: int) -> str:
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    cut = s[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def _to_ns(latest) -> int:
    """Convert an updated_at value to int ns for cache comparison."""
    if latest is None:
        return 0
    if hasattr(latest, "timestamp"):
        return int(latest.timestamp() * 1_000_000_000)
    return 0
