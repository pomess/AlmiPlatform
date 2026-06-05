"""Atlas Memory service — reads from Unity Catalog Platinum tables.

Run with: `uvicorn atlas_memory.main:app --port 8001`

All data is read-only from pre-computed Platinum layer tables in Unity Catalog.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .schemas import BrainSummary, Graph, GraphEdge, GraphNode, Page, SearchHit
from .uc_client import full_table, is_configured, query


app = FastAPI(title="Disease360 Atlas Memory", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "memory", "backend": "unity_catalog", "configured": is_configured()}


# --- Graph endpoints ----------------------------------------------------------


@app.get("/graph", response_model=Graph)
def get_graph(segment: str | None = None) -> Graph:
    """Return the knowledge graph (nodes + edges) from Platinum tables."""
    if not is_configured():
        return Graph(nodes=[], edges=[])

    nodes_sql = f"SELECT * FROM {full_table('platinum_graph_nodes')}"
    edges_sql = f"SELECT * FROM {full_table('platinum_graph_edges')}"

    if segment:
        nodes_sql += f" WHERE array_contains(properties['indication'], '{segment}')"

    raw_nodes = query(nodes_sql)
    raw_edges = query(edges_sql)

    nodes = [
        GraphNode(
            id=n["node_id"],
            title=n["name"],
            layer=n["node_type"],
        )
        for n in raw_nodes
    ]

    node_ids = {n["node_id"] for n in raw_nodes}
    edges = [
        GraphEdge(source=e["source_node"], target=e["target_node"])
        for e in raw_edges
        if e["source_node"] in node_ids and e["target_node"] in node_ids
    ]

    return Graph(nodes=nodes, edges=edges)


# --- Bullseye endpoint --------------------------------------------------------


@app.get("/bullseye")
def get_bullseye(segment: str = Query(default="AD")) -> list[dict]:
    """Return bullseye positioning data for a given segment."""
    rows = query(
        f"SELECT * FROM {full_table('platinum_bullseye')} WHERE segment = %(segment)s",
        {"segment": segment},
    )
    return rows


# --- News events endpoint -----------------------------------------------------


@app.get("/news")
def get_news(limit: int = Query(default=50, le=200)) -> list[dict]:
    """Return recent news events from Platinum layer."""
    rows = query(
        f"SELECT * FROM {full_table('platinum_news_events')} "
        f"ORDER BY event_date DESC LIMIT {limit}"
    )
    return rows


# --- KOL profiles endpoint ----------------------------------------------------


@app.get("/kols")
def get_kols(limit: int = Query(default=50, le=200)) -> list[dict]:
    """Return top KOL profiles by influence score."""
    rows = query(
        f"SELECT * FROM {full_table('platinum_kols')} "
        f"ORDER BY influence_score DESC LIMIT {limit}"
    )
    return rows


# --- Clinical trials endpoint -------------------------------------------------


@app.get("/trials")
def get_trials(
    status: str | None = None,
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    """Return clinical trials, optionally filtered by status."""
    sql = f"SELECT * FROM {full_table('platinum_trials')}"
    params = {}
    if status:
        sql += " WHERE status = %(status)s"
        params["status"] = status
    sql += f" ORDER BY start_date DESC LIMIT {limit}"
    return query(sql, params if params else None)


# --- Node detail endpoint -----------------------------------------------------


@app.get("/node/{node_id}")
def get_node(node_id: str) -> dict:
    """Return a single graph node with its connected edges."""
    node = query(
        f"SELECT * FROM {full_table('platinum_graph_nodes')} WHERE node_id = %(nid)s",
        {"nid": node_id},
    )
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")

    edges = query(
        f"SELECT * FROM {full_table('platinum_graph_edges')} "
        f"WHERE source_node = %(nid)s OR target_node = %(nid)s",
        {"nid": node_id},
    )

    return {"node": node[0], "edges": edges}


# --- Legacy-compatible brain endpoints (for frontend compatibility) -----------


@app.get("/tenant/{tenant_id}/brains", response_model=list[BrainSummary])
def get_brains(tenant_id: str) -> list[BrainSummary]:
    """Return a singleton brain list for frontend compatibility."""
    if not is_configured():
        return [BrainSummary(id="atlas", title="Disease360 Atlas", page_count=0, has_hot=False)]
    node_count = query(f"SELECT COUNT(*) as cnt FROM {full_table('platinum_graph_nodes')}")
    count = node_count[0]["cnt"] if node_count else 0
    return [
        BrainSummary(
            id="atlas",
            title="Disease360 Atlas",
            page_count=count,
            has_hot=False,
        )
    ]


@app.get("/tenant/{tenant_id}/brain/{brain_id}/hot")
def get_hot(tenant_id: str, brain_id: str) -> dict:
    """Return hot cache equivalent — latest news events summary."""
    if not is_configured():
        return {"path": "hot.md", "body": "# Disease360 Atlas\n\nDatabricks not configured."}
    rows = query(
        f"SELECT title, event_date, category FROM {full_table('platinum_news_events')} "
        f"ORDER BY event_date DESC LIMIT 10"
    )
    lines = ["# Disease360 Atlas — Hot", ""]
    for r in rows:
        lines.append(f"- [{r.get('category', '')}] {r.get('title', '')} ({r.get('event_date', '')})")
    return {"path": "hot.md", "body": "\n".join(lines)}


@app.get("/tenant/{tenant_id}/brain/{brain_id}/index")
def get_index(tenant_id: str, brain_id: str) -> dict:
    """Return index page equivalent — summary of Platinum layer."""
    if not is_configured():
        return {"path": "index.md", "body": "# Disease360 Atlas\n\nConnect to Databricks to see data."}
    counts = {}
    for table in ["platinum_graph_nodes", "platinum_graph_edges", "platinum_bullseye", "platinum_trials"]:
        try:
            result = query(f"SELECT COUNT(*) as cnt FROM {full_table(table)}")
            counts[table] = result[0]["cnt"] if result else 0
        except Exception:
            counts[table] = 0
    lines = ["# Disease360 Atlas — Index", ""]
    lines.append(f"- Graph nodes: {counts.get('platinum_graph_nodes', 0)}")
    lines.append(f"- Graph edges: {counts.get('platinum_graph_edges', 0)}")
    lines.append(f"- Bullseye entries: {counts.get('platinum_bullseye', 0)}")
    lines.append(f"- Clinical trials: {counts.get('platinum_trials', 0)}")
    return {"path": "index.md", "body": "\n".join(lines)}


@app.get("/tenant/{tenant_id}/atlas")
def get_atlas(tenant_id: str) -> dict:
    """Return atlas summary for the cockpit sidebar."""
    if not is_configured():
        return {"brains": [{"id": "atlas", "purpose": "Pharma competitive intelligence", "page_count": 0, "key_entities": [], "key_concepts": []}]}
    node_count = query(f"SELECT COUNT(*) as cnt FROM {full_table('platinum_graph_nodes')}")
    return {
        "brains": [{
            "id": "atlas",
            "purpose": "Almirall dermatology competitive intelligence",
            "page_count": node_count[0]["cnt"] if node_count else 0,
            "key_entities": [],
            "key_concepts": [],
        }]
    }


@app.get("/tenant/{tenant_id}/brain/{brain_id}/graph", response_model=Graph)
def get_brain_graph(tenant_id: str, brain_id: str) -> Graph:
    """Legacy route — delegates to /graph."""
    return get_graph()


@app.get("/tenant/{tenant_id}/brain/{brain_id}/page", response_model=Page)
def get_page(tenant_id: str, brain_id: str, path: str = "") -> Page:
    """Return a graph node as a Page (for frontend compatibility)."""
    node_id = path.replace(".md", "").split("/")[-1] if path else ""
    if not node_id:
        raise HTTPException(400, "path parameter required")

    result = query(
        f"SELECT * FROM {full_table('platinum_graph_nodes')} WHERE node_id = %(nid)s",
        {"nid": node_id},
    )
    if not result:
        raise HTTPException(404, f"Node {node_id} not found")

    n = result[0]
    props = n.get("properties", {}) or {}
    body_lines = [f"# {n['name']}", "", f"**Type:** {n['node_type']}", ""]
    for k, v in props.items():
        body_lines.append(f"- **{k}:** {v}")

    return Page(
        path=path,
        title=n["name"],
        frontmatter={"node_type": n["node_type"]},
        body="\n".join(body_lines),
        wikilinks=[],
    )


@app.get("/tenant/{tenant_id}/brain/{brain_id}/search", response_model=list[SearchHit])
def search_brain(tenant_id: str, brain_id: str, q: str, limit: int = 20) -> list[SearchHit]:
    """Full-text search across graph nodes by name/aliases."""
    if not is_configured():
        return []
    rows = query(
        f"SELECT node_id, name, node_type, aliases FROM {full_table('platinum_graph_nodes')} "
        f"WHERE LOWER(name) LIKE LOWER(%(q)s) "
        f"LIMIT {limit}",
        {"q": f"%{q}%"},
    )
    return [
        SearchHit(
            path=r["node_id"],
            title=r["name"],
            snippet=f"{r['node_type']}: {r['name']}",
            score=1.0,
            brain="atlas",
        )
        for r in rows
    ]


# --- Run entry point ----------------------------------------------------------


def run() -> None:
    import uvicorn

    port = int(os.environ.get("ATLAS_MEMORY_PORT", "8001"))
    uvicorn.run("atlas_memory.main:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    run()
