"""Postgres-backed wikilink graph (ADR 0001 phase 2.5).

Reads pages and outgoing wikilinks from the database, resolves each
wikilink target to a real page, and emits the same Graph shape as
`graph.build`. Unresolvable targets are dropped on purpose: we don't
want phantom nodes in the cockpit's force-directed view.

The hot/index "specials" don't live in `pages` — they're per-brain
singletons on the `brains` row (index_md, agents_md) and the `hot_cache`
table. We synthesize lightweight nodes for them so the layered graph
view (raw / wiki / index / hot) stays consistent across backends.
"""

from __future__ import annotations

from .db import acquire
from .schemas import Graph, GraphEdge, GraphNode


async def build(tenant_id: str, brain_id: str, brain_name: str) -> Graph:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def add(node_id: str, title: str, layer: str) -> None:
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = GraphNode(id=node_id, title=title, layer=layer)
            return
        priority = {"raw": 0, "wiki": 1, "index": 2, "hot": 3}
        if priority.get(layer, 1) > priority.get(existing.layer, 1):
            nodes[node_id] = GraphNode(id=node_id, title=title, layer=layer)

    async with acquire() as c:
        page_rows = await c.fetch(
            """
            select id::text as id, path, title
              from public.pages
             where tenant_id = $1 and brain_id = $2
            """,
            tenant_id,
            brain_id,
        )
        link_rows = await c.fetch(
            """
            select source_page::text as source_page, target_slug
              from public.wikilinks
             where tenant_id = $1 and brain_id = $2
            """,
            tenant_id,
            brain_id,
        )
        # Special nodes: hot.md and index.md are per-brain singletons.
        hot_exists = await c.fetchval(
            """
            select length(coalesce(body, '')) > 0
              from public.hot_cache
             where tenant_id = $1 and brain_id = $2
            """,
            tenant_id,
            brain_id,
        )
        index_exists = await c.fetchval(
            """
            select length(coalesce(index_md, '')) > 0
              from public.brains
             where tenant_id = $1 and id = $2
            """,
            tenant_id,
            brain_id,
        )

    # Build resolution structures. Real pages are addressed by their `path`
    # in graph output, mirroring the disk implementation; the page UUID is
    # only used internally to join wikilinks to source pages.
    by_uuid: dict[str, dict[str, str]] = {
        r["id"]: {"path": r["path"], "title": r["title"]} for r in page_rows
    }
    rel_set = {r["path"] for r in page_rows}
    by_key: dict[str, str] = {}
    for r in page_rows:
        rel = r["path"]
        stem = rel.rsplit("/", 1)[-1]
        if stem.endswith(".md"):
            stem = stem[:-3]
        by_key.setdefault(stem.lower(), rel)
        title_key = (r["title"] or "").lower().replace(" ", "-")
        if title_key:
            by_key.setdefault(title_key, rel)

    def resolve(target: str) -> str | None:
        t = target.strip()
        if not t:
            return None
        if t in rel_set:
            return t
        with_md = t + ".md"
        if with_md in rel_set:
            return with_md
        slug = t[:-3] if t.endswith(".md") else t
        slug = slug.lower().replace(" ", "-")
        if slug in by_key:
            return by_key[slug]
        last = slug.rsplit("/", 1)[-1]
        if last in by_key:
            return by_key[last]
        return None

    # Real page nodes.
    for r in page_rows:
        layer = "raw" if r["path"].startswith("raw/") else "wiki"
        add(r["path"], r["title"], layer)

    # Special nodes for the hot/index layer.
    if hot_exists:
        add("hot.md", f"{brain_name} — Hot", "hot")
    if index_exists:
        add("index.md", f"{brain_name} — Index", "index")

    # Edges: source_uuid → target rel_path (resolved).
    for link in link_rows:
        src = by_uuid.get(link["source_page"])
        if src is None:
            continue
        target_rel = resolve(link["target_slug"])
        if target_rel is None:
            continue
        edges.append(GraphEdge(source=src["path"], target=target_rel))

    return Graph(nodes=list(nodes.values()), edges=edges)
