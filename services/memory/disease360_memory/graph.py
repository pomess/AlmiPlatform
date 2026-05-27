"""Build a wikilink graph for a brain.

Only real markdown files become nodes. Wikilink targets are resolved against
the on-disk vault (by exact rel path, by filename stem, or by title-slug) and
unresolvable targets are dropped — orphan/missing-page detection lives in the
lint endpoint, and surfacing phantom nodes here would dead-end the Graph view
into a "Page not found" card when a user clicks one.
"""

from __future__ import annotations

from .registry import Brain
from .schemas import Graph, GraphEdge, GraphNode, Page
from .vault import list_markdown, read_page


def build(brain: Brain) -> Graph:
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

    # 1) Enumerate every real markdown file with its rel path, layer, and parsed page.
    real_pages: list[tuple[str, str, Page]] = []
    for f in list_markdown(brain.wiki_dir):
        rel = str(f.relative_to(brain.root)).replace("\\", "/")
        real_pages.append((rel, "wiki", read_page(brain.root, rel)))
    for f in list_markdown(brain.raw_dir):
        rel = str(f.relative_to(brain.root)).replace("\\", "/")
        real_pages.append((rel, "raw", read_page(brain.root, rel)))
    for special_path, layer in (
        (brain.hot_path, "hot"),
        (brain.index_path, "index"),
    ):
        if not special_path.exists():
            continue
        rel = special_path.name  # "hot.md" / "index.md"
        real_pages.append((rel, layer, read_page(brain.root, rel)))

    # 2) Build a resolver from wikilink target → real rel path.
    rel_set: set[str] = {rel for rel, _layer, _page in real_pages}
    by_key: dict[str, str] = {}
    for rel, _layer, page in real_pages:
        stem = rel.rsplit("/", 1)[-1]
        if stem.endswith(".md"):
            stem = stem[:-3]
        by_key.setdefault(stem.lower(), rel)
        title_key = page.title.lower().replace(" ", "-")
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

    # 3) Emit a node per real file, then edges for resolvable wikilinks.
    for rel, layer, page in real_pages:
        add(rel, page.title, layer)
    for rel, _layer, page in real_pages:
        for link in page.wikilinks:
            target_rel = resolve(link.target)
            if target_rel is None:
                continue
            edges.append(GraphEdge(source=rel, target=target_rel))

    return Graph(nodes=list(nodes.values()), edges=edges)
