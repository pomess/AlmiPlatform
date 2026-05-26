"""Postgres-backed brain registry (ADR 0001 phase 2.2).

Mirrors the disk-backed registry's surface (`list_brains`, `get_brain`,
`bootstrap_default_brains`) but stores rows in `public.brains` keyed by
`tenant_id`. The memory service connects with the service-role DSN and
bypasses RLS at the database layer; we re-engage tenant scoping at the
query layer by passing `tenant_id` into every WHERE clause.

Phase 4 swaps the service-role connection for a per-user JWT, at which
point RLS becomes load-bearing. The query-layer scoping stays in place
as defense in depth.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import acquire
from .schemas import BrainSummary

DEFAULT_DEFAULT_BRAINS = ("Bruno's Brain", "Deloitte's Brain")


@dataclass
class PgBrain:
    """A Postgres-backed brain row.

    Distinct type from the disk-backed `Brain` so accidental cross-pollination
    (e.g. someone reading `.wiki_dir` on a Postgres brain) fails loudly at the
    type check rather than silently producing a phantom path.
    """

    id: str  # uuid string
    name: str
    tenant_id: str

    async def summary(self) -> BrainSummary:
        async with acquire() as c:
            row = await c.fetchrow(
                """
                select count(*) as page_count,
                       coalesce(
                         (select length(body) > 0
                            from public.hot_cache
                           where brain_id = $1),
                         false
                       ) as has_hot
                  from public.pages
                 where brain_id = $1
                """,
                self.id,
            )
        return BrainSummary(
            id=self.name,
            title=self.name,
            page_count=int(row["page_count"]) if row else 0,
            has_hot=bool(row["has_hot"]) if row else False,
        )


async def list_brains(tenant_id: str) -> list[PgBrain]:
    async with acquire() as c:
        rows = await c.fetch(
            """
            select id::text as id, name
              from public.brains
             where tenant_id = $1
             order by name
            """,
            tenant_id,
        )
    return [PgBrain(id=r["id"], name=r["name"], tenant_id=tenant_id) for r in rows]


async def get_brain_by_name(tenant_id: str, name: str) -> PgBrain:
    async with acquire() as c:
        row = await c.fetchrow(
            "select id::text as id, name from public.brains where tenant_id = $1 and name = $2",
            tenant_id,
            name,
        )
    if row is None:
        raise KeyError(f"No such brain in tenant {tenant_id!r}: {name!r}")
    return PgBrain(id=row["id"], name=row["name"], tenant_id=tenant_id)


async def get_brain_by_id(tenant_id: str, brain_id: str) -> PgBrain:
    async with acquire() as c:
        row = await c.fetchrow(
            """
            select id::text as id, name
              from public.brains
             where tenant_id = $1 and id = $2
            """,
            tenant_id,
            brain_id,
        )
    if row is None:
        raise KeyError(f"No such brain in tenant {tenant_id!r} by id: {brain_id!r}")
    return PgBrain(id=row["id"], name=row["name"], tenant_id=tenant_id)


async def bootstrap_default_brains(
    tenant_id: str, names: tuple[str, ...] = DEFAULT_DEFAULT_BRAINS
) -> list[PgBrain]:
    """Create the default brains on first run if the tenant has none.

    Idempotent: if any brain already exists for this tenant, returns the
    existing list unchanged. We don't auto-create the legacy "Bruno's
    Brain" + "Deloitte's Brain" pair for every new tenant — only for
    Bruno's dev tenant. Future tenants pick their own brains via the UI.
    """
    existing = await list_brains(tenant_id)
    if existing:
        return existing
    async with acquire() as c:
        for name in names:
            await c.execute(
                """
                insert into public.brains (tenant_id, name, agents_md, index_md)
                values ($1, $2, $3, $4)
                on conflict (tenant_id, name) do nothing
                """,
                tenant_id,
                name,
                "# AGENTS\n\n_Schema for ingest. See docs/04-karpathy-llm-wiki.md._\n",
                f"# {name} — Index\n\n_(empty)_\n",
            )
            # Seed an empty hot row alongside the brain so /hot reads never 404.
            await c.execute(
                """
                insert into public.hot_cache (brain_id, tenant_id, body)
                select id, tenant_id, '# Hot cache' || E'\n\n_Empty._\n'
                  from public.brains
                 where tenant_id = $1 and name = $2
                on conflict (brain_id) do nothing
                """,
                tenant_id,
                name,
            )
    return await list_brains(tenant_id)
