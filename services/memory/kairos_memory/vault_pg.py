"""Postgres-backed vault I/O (ADR 0001 phase 2.3).

Reads/writes pages, hot cache, and raw captures against the rows defined
in `supabase/migrations/0002_vault_schema.sql`. Wikilinks are parsed
with the same regex as the disk implementation (`vault.parse_wikilinks`)
and persisted to `public.wikilinks` on every page upsert so the graph
view can join on them.

Pages preserve frontmatter as a `jsonb` column rather than a YAML header
on disk. The Page schema returned to the client is unchanged — only the
storage substrate changes.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

from .db import acquire, transaction
from .schemas import Page
from .vault import parse_wikilinks, title_from_body_str

__all__ = [
    "read_page",
    "write_page",
    "list_pages",
    "read_hot",
    "write_hot",
    "append_to_hot",
    "ingest_raw",
    "read_index_md",
    "write_index_md",
    "read_agents_md",
]


async def read_page(tenant_id: str, brain_id: str, path: str) -> Page:
    async with acquire() as c:
        row = await c.fetchrow(
            """
            select path, title, body, frontmatter
              from public.pages
             where tenant_id = $1 and brain_id = $2 and path = $3
            """,
            tenant_id,
            brain_id,
            path,
        )
    if row is None:
        raise FileNotFoundError(f"No such page: {path}")
    fm = _decode_jsonb(row["frontmatter"])
    return Page(
        path=row["path"],
        title=row["title"],
        frontmatter=fm,
        body=row["body"],
        wikilinks=parse_wikilinks(row["body"]),
    )


async def write_page(
    tenant_id: str,
    brain_id: str,
    path: str,
    body: str,
    fm: dict[str, Any] | None = None,
) -> Page:
    """Upsert a page row and refresh its outgoing wikilinks.

    Frontmatter is stored as jsonb; the `title` column is denormalized
    from frontmatter.title (or the first heading) for cheap listing.
    """
    fm = dict(fm or {})
    title = fm.get("title") or title_from_body_str(path, body)
    fm.setdefault("title", title)

    async with transaction() as c:
        row = await c.fetchrow(
            """
            insert into public.pages (tenant_id, brain_id, path, title, body, frontmatter)
            values ($1, $2, $3, $4, $5, $6::jsonb)
            on conflict (brain_id, path) do update
                set title = excluded.title,
                    body = excluded.body,
                    frontmatter = excluded.frontmatter,
                    updated_at = now()
            returning id::text as id, path, title, body, frontmatter
            """,
            tenant_id,
            brain_id,
            path,
            title,
            body,
            json.dumps(fm, default=_json_default),
        )
        # Refresh outgoing wikilinks for this page. Cheaper than a diff —
        # pages are small and reads dominate.
        await c.execute(
            "delete from public.wikilinks where source_page = $1",
            row["id"],
        )
        for link in parse_wikilinks(body):
            await c.execute(
                """
                insert into public.wikilinks
                    (tenant_id, brain_id, source_page, target_slug, alias, anchor)
                values ($1, $2, $3, $4, $5, $6)
                """,
                tenant_id,
                brain_id,
                row["id"],
                link.target,
                link.alias,
                None,
            )
    return Page(
        path=row["path"],
        title=row["title"],
        frontmatter=_decode_jsonb(row["frontmatter"]),
        body=row["body"],
        wikilinks=parse_wikilinks(row["body"]),
    )


async def list_pages(tenant_id: str, brain_id: str) -> list[dict[str, Any]]:
    """Light listing for the index/atlas — title and path only."""
    async with acquire() as c:
        rows = await c.fetch(
            """
            select path, title, frontmatter, updated_at
              from public.pages
             where tenant_id = $1 and brain_id = $2
             order by path
            """,
            tenant_id,
            brain_id,
        )
    return [
        {
            "path": r["path"],
            "title": r["title"],
            "frontmatter": _decode_jsonb(r["frontmatter"]),
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


# --- Hot cache -------------------------------------------------------------


async def read_hot(tenant_id: str, brain_id: str) -> str:
    async with acquire() as c:
        row = await c.fetchrow(
            "select body from public.hot_cache where tenant_id = $1 and brain_id = $2",
            tenant_id,
            brain_id,
        )
    return row["body"] if row else "# Hot cache\n\n"


async def write_hot(tenant_id: str, brain_id: str, body: str) -> None:
    async with acquire() as c:
        await c.execute(
            """
            insert into public.hot_cache (brain_id, tenant_id, body)
            values ($1, $2, $3)
            on conflict (brain_id) do update set body = excluded.body, updated_at = now()
            """,
            brain_id,
            tenant_id,
            body,
        )


async def append_to_hot(tenant_id: str, brain_id: str, addition: str) -> str:
    """Append `addition` at the bottom of hot.md. Returns the new body."""
    current = await read_hot(tenant_id, brain_id)
    sep = "" if current.endswith("\n") or current == "" else "\n"
    new = f"{current}{sep}{addition.rstrip()}\n"
    await write_hot(tenant_id, brain_id, new)
    return new


# --- Raw captures ----------------------------------------------------------


async def ingest_raw(
    tenant_id: str, brain_id: str, filename: str, body: str
) -> dict[str, Any]:
    async with acquire() as c:
        row = await c.fetchrow(
            """
            insert into public.raw_captures (tenant_id, brain_id, filename, body)
            values ($1, $2, $3, $4)
            returning id::text as id, filename, created_at
            """,
            tenant_id,
            brain_id,
            filename,
            body,
        )
    return {
        "id": row["id"],
        "filename": row["filename"],
        "path": f"raw/{row['filename']}",
        "created_at": row["created_at"].isoformat(),
    }


# --- Index / agents (per-brain singletons stored on `brains`) -------------


async def read_index_md(tenant_id: str, brain_id: str) -> str:
    async with acquire() as c:
        row = await c.fetchrow(
            "select index_md from public.brains where tenant_id = $1 and id = $2",
            tenant_id,
            brain_id,
        )
    return (row and row["index_md"]) or ""


async def write_index_md(tenant_id: str, brain_id: str, body: str) -> None:
    async with acquire() as c:
        await c.execute(
            """
            update public.brains set index_md = $3, updated_at = now()
             where tenant_id = $1 and id = $2
            """,
            tenant_id,
            brain_id,
            body,
        )


async def read_agents_md(tenant_id: str, brain_id: str) -> str:
    async with acquire() as c:
        row = await c.fetchrow(
            "select agents_md from public.brains where tenant_id = $1 and id = $2",
            tenant_id,
            brain_id,
        )
    return (row and row["agents_md"]) or ""


# --- helpers --------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    """JSON encoder hook for non-native types found in YAML frontmatter.

    `date`/`datetime` round-trip as ISO 8601 strings — Postgres jsonb
    doesn't have a native date type, and the lossy stringification is
    the same trade-off `python-frontmatter` makes when re-emitting YAML.
    """
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _decode_jsonb(val: Any) -> dict[str, Any]:
    """asyncpg returns jsonb as str by default unless a codec is registered."""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return {}
    return {}
