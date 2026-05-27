"""Postgres tsvector full-text search (ADR 0001 phase 2.4).

Replaces the FTS5 SQLite mirror in `index_db.py` with a query against the
generated `pages.tsv` column. Title is weighted 'A' and body 'B' inside
the generated tsvector (same shape as the FTS5 schema), so result
ranking stays comparable.

`websearch_to_tsquery` lets users type Google-style queries
("foo bar -baz \"quoted phrase\"") without having to learn tsquery syntax.
Fallback to `plainto_tsquery` when the input doesn't parse — the FTS5
implementation never raised on weird input, so neither do we.
"""

from __future__ import annotations

from .db import acquire


async def search(
    tenant_id: str,
    brain_id: str,
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Full-text search within a single brain. Returns SearchHit-shaped dicts."""
    return await _run_search(
        tenant_id, query, limit, where_extra="and brain_id = $4", extra_params=(brain_id,)
    )


async def search_all(tenant_id: str, query: str, limit: int = 20) -> list[dict]:
    """Full-text search across every brain in this tenant."""
    return await _run_search(tenant_id, query, limit, where_extra="", extra_params=())


async def _run_search(
    tenant_id: str,
    query: str,
    limit: int,
    *,
    where_extra: str,
    extra_params: tuple,
) -> list[dict]:
    # `websearch_to_tsquery` is permissive but does raise on certain inputs
    # (e.g. unbalanced quotes). Fall back to `plainto_tsquery` so we don't
    # leak a 500 to the agent for a malformed search.
    sql = f"""
        with q as (
            select coalesce(
                nullif(websearch_to_tsquery('english', $2), ''::tsquery),
                plainto_tsquery('english', $2)
            ) as tsq
        )
        select
            p.path,
            p.title,
            b.name as brain,
            ts_headline(
                'english', p.body, q.tsq,
                'StartSel=<mark>, StopSel=</mark>, MaxWords=20, MinWords=8, ShortWord=2'
            ) as snippet,
            ts_rank(p.tsv, q.tsq) as score
          from public.pages p
          join q on true
          join public.brains b on b.id = p.brain_id
         where p.tenant_id = $1
           and p.tsv @@ q.tsq
           {where_extra}
         order by score desc
         limit $3
    """
    params: tuple = (tenant_id, query, limit, *extra_params)
    async with acquire() as c:
        rows = await c.fetch(sql, *params)
    return [
        {
            "brain": r["brain"],
            "path": r["path"],
            "title": r["title"],
            "snippet": r["snippet"],
            "score": float(r["score"]),
        }
        for r in rows
    ]
