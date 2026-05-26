"""FastAPI app for the memory service.

Run with: `uvicorn kairos_memory.main:app --port 8001`

Routes are tenant-scoped: `/tenant/{tenant_id}/...`. The `{brain_id}` URL
segment is the brain *name* (e.g. "Bruno's Brain") — the disk backend
keys folders by name, and the Postgres backend resolves the name to a
UUID internally so the public contract stays identical across backends.

`KAIROS_VAULT_BACKEND` selects the storage substrate:
  - `disk` (default): legacy `vault/<tenant>/<brain>/` filesystem.
  - `postgres`: rows in Supabase Postgres under tenant RLS (ADR 0001).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kairos_runtime.config import repo_root

from . import atlas as atlas_mod
from . import (
    atlas_pg,
    db,
    graph_pg,
    index_db,
    index_pg,
    registry_pg,
    vault_pg,
    wiki_agent,
    wiki_agent_pg,
)
from .graph import build as build_graph
from .registry import (
    DEFAULT_TENANT_ID,
    bootstrap_default_brains,
    get_brain,
    list_brains,
)
from .schemas import (
    AppendHotRequest,
    ApplyPlanRequest,
    ApplyResult,
    BrainSummary,
    Graph,
    IngestPlan,
    IngestPlanRequest,
    IngestRawRequest,
    LintIssue,
    LintReport,
    NoteRequest,
    Page,
    ReplaceHotRequest,
    SearchHit,
)
from .vault import append_to_section, read_page, write_page


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if db.is_postgres():
        # Bootstrap Bruno's tenant default brains if Postgres mode is on.
        # Future tenants pick their own brains from the cockpit; we don't
        # auto-seed for everyone.
        try:
            await registry_pg.bootstrap_default_brains(db.dev_tenant_id())
        except Exception as e:
            # Surface the misconfig in the log but don't take the service
            # down — read-only routes keep working without bootstrap.
            print(f"[memory] postgres bootstrap skipped: {e}")
    else:
        bootstrap_default_brains(DEFAULT_TENANT_ID)
    yield
    if db.is_postgres():
        await db.close_pool()


app = FastAPI(title="Kairos Memory", version="0.3.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db_path(tenant_id: str) -> Path:
    """Disk-backend FTS index DB. One per tenant so cross-tenant searches stay impossible."""
    p = repo_root() / "services" / "memory" / "data" / tenant_id / "fts.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


async def _pg_brain(tenant_id: str, brain_name: str) -> registry_pg.PgBrain:
    try:
        return await registry_pg.get_brain_by_name(tenant_id, brain_name)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "memory", "backend": db.vault_backend()}


# --- Tenant-scoped routes ---------------------------------------------------


@app.get("/tenant/{tenant_id}/brains", response_model=list[BrainSummary])
async def get_brains(tenant_id: str) -> list[BrainSummary]:
    if db.is_postgres():
        brains = await registry_pg.list_brains(tenant_id)
        return [await b.summary() for b in brains]
    return [b.summary() for b in list_brains(tenant_id)]


@app.get("/tenant/{tenant_id}/atlas")
async def get_atlas(tenant_id: str) -> dict:
    """Compact, file-derived summary of every brain's contents in this tenant.

    Returned shape:
        {"brains": [{id, purpose, page_count, key_entities, key_concepts, updated_at}, ...]}

    Cached per-brain on max(updated_at); recomputed on writes via
    `atlas_pg.invalidate(tenant_id, brain_id)` (Postgres) or
    `atlas.invalidate(brain_id, tenant_id)` (disk).
    """
    if db.is_postgres():
        return await atlas_pg.build_atlas(tenant_id)
    return atlas_mod.build_atlas(tenant_id)


@app.get("/tenant/{tenant_id}/brain/{brain_id}/index")
async def get_index(tenant_id: str, brain_id: str) -> dict:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        body = await vault_pg.read_index_md(tenant_id, b.id)
        return {"path": "index.md", "body": body}
    b = _brain(tenant_id, brain_id)
    return {"path": "index.md", "body": b.index_path.read_text(encoding="utf-8")}


@app.get("/tenant/{tenant_id}/brain/{brain_id}/hot")
async def get_hot(tenant_id: str, brain_id: str) -> dict:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        body = await vault_pg.read_hot(tenant_id, b.id)
        return {"path": "hot.md", "body": body}
    b = _brain(tenant_id, brain_id)
    return {"path": "hot.md", "body": b.hot_path.read_text(encoding="utf-8")}


@app.post("/tenant/{tenant_id}/brain/{brain_id}/append-hot")
async def append_hot(tenant_id: str, brain_id: str, req: AppendHotRequest) -> dict:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        current = await vault_pg.read_hot(tenant_id, b.id)
        if req.section:
            new = append_to_section(current, req.section, req.text)
        else:
            sep = "" if current.endswith("\n") else "\n"
            new = f"{current}{sep}{req.text.rstrip()}\n"
        await vault_pg.write_hot(tenant_id, b.id, new)
        atlas_pg.invalidate(tenant_id, b.id)
        return {"ok": True, "size": len(new)}

    b = _brain(tenant_id, brain_id)
    current = b.hot_path.read_text(encoding="utf-8") if b.hot_path.exists() else "# Hot cache\n\n"
    if req.section:
        new = append_to_section(current, req.section, req.text)
    else:
        sep = "" if current.endswith("\n") else "\n"
        new = f"{current}{sep}{req.text.rstrip()}\n"
    b.hot_path.write_text(new, encoding="utf-8")
    atlas_mod.invalidate(brain_id, tenant_id)
    return {"ok": True, "size": len(new)}


@app.post("/tenant/{tenant_id}/brain/{brain_id}/replace-hot")
async def replace_hot(tenant_id: str, brain_id: str, req: ReplaceHotRequest) -> dict:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        await vault_pg.write_hot(tenant_id, b.id, req.full_text)
        atlas_pg.invalidate(tenant_id, b.id)
        return {"ok": True, "size": len(req.full_text)}
    b = _brain(tenant_id, brain_id)
    b.hot_path.write_text(req.full_text, encoding="utf-8")
    atlas_mod.invalidate(brain_id, tenant_id)
    return {"ok": True, "size": len(req.full_text)}


@app.get("/tenant/{tenant_id}/brain/{brain_id}/page", response_model=Page)
async def get_page_route(tenant_id: str, brain_id: str, path: str) -> Page:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        try:
            return await vault_pg.read_page(tenant_id, b.id, path)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
    b = _brain(tenant_id, brain_id)
    try:
        return read_page(b.root, path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/tenant/{tenant_id}/brain/{brain_id}/note", response_model=Page)
async def post_note(tenant_id: str, brain_id: str, req: NoteRequest) -> Page:
    rel = req.path
    if not rel.startswith("wiki/"):
        rel = f"wiki/{rel}"
    if not rel.endswith(".md"):
        rel += ".md"
    body = req.body if req.body.lstrip().startswith("#") else f"# {req.title}\n\n{req.body}"
    fm = {"title": req.title, **(req.frontmatter or {})}

    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        page = await vault_pg.write_page(tenant_id, b.id, rel, body, fm)
        atlas_pg.invalidate(tenant_id, b.id)
        return page
    b = _brain(tenant_id, brain_id)
    page = write_page(b.root, rel, body, fm)
    index_db.reindex(b, _db_path(tenant_id))
    atlas_mod.invalidate(brain_id, tenant_id)
    return page


@app.get("/tenant/{tenant_id}/brain/{brain_id}/search", response_model=list[SearchHit])
async def search_route(
    tenant_id: str, brain_id: str, q: str, limit: int = 20
) -> list[SearchHit]:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return [SearchHit(**h) for h in await index_pg.search(tenant_id, b.id, q, limit=limit)]
    b = _brain(tenant_id, brain_id)
    fts_db = _db_path(tenant_id)
    index_db.reindex(b, fts_db)
    return [SearchHit(**h) for h in index_db.search(b, fts_db, q, limit=limit)]


@app.get("/tenant/{tenant_id}/search", response_model=list[SearchHit])
async def search_all_route(tenant_id: str, q: str, limit: int = 20) -> list[SearchHit]:
    """Full-text search across every brain in this tenant. Hits are tagged with brain id."""
    if db.is_postgres():
        return [SearchHit(**h) for h in await index_pg.search_all(tenant_id, q, limit=limit)]
    fts_db = _db_path(tenant_id)
    for b in list_brains(tenant_id):
        index_db.reindex(b, fts_db)
    return [SearchHit(**h) for h in index_db.search_all(fts_db, q, limit=limit)]


@app.get("/tenant/{tenant_id}/brain/{brain_id}/graph", response_model=Graph)
async def graph_route(tenant_id: str, brain_id: str) -> Graph:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return await graph_pg.build(tenant_id, b.id, b.name)
    b = _brain(tenant_id, brain_id)
    return build_graph(b)


@app.post("/tenant/{tenant_id}/brain/{brain_id}/raw/ingest")
async def raw_ingest(tenant_id: str, brain_id: str, req: IngestRawRequest) -> dict:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return await vault_pg.ingest_raw(tenant_id, b.id, req.filename, req.content)
    b = _brain(tenant_id, brain_id)
    target = (b.raw_dir / req.filename).resolve()
    if b.raw_dir.resolve() not in target.parents:
        raise HTTPException(400, "raw filename escapes raw/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"ok": True, "path": f"raw/{req.filename}"}


# --- Wiki maintenance: ingest / lint / solve --------------------------------


@app.post("/tenant/{tenant_id}/brain/{brain_id}/ingest/plan", response_model=IngestPlan)
async def ingest_plan_route(
    tenant_id: str, brain_id: str, req: IngestPlanRequest
) -> IngestPlan:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return await wiki_agent_pg.ingest_plan(tenant_id, b.id, b.name, req.title, req.content)
    b = _brain(tenant_id, brain_id)
    return await wiki_agent.ingest_plan(b, req.title, req.content)


@app.post("/tenant/{tenant_id}/brain/{brain_id}/ingest/apply", response_model=ApplyResult)
async def ingest_apply_route(
    tenant_id: str, brain_id: str, req: ApplyPlanRequest
) -> ApplyResult:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        plan = wiki_agent_pg.get_plan(req.plan_id)
        if plan is None:
            raise HTTPException(404, f"No such plan (or expired): {req.plan_id}")
        if plan.brain != b.name:
            raise HTTPException(400, "plan_id does not belong to this brain")
        result = await wiki_agent_pg.apply_plan(tenant_id, b.id, plan)
        atlas_pg.invalidate(tenant_id, b.id)
        return result

    b = _brain(tenant_id, brain_id)
    plan = wiki_agent.get_plan(req.plan_id)
    if plan is None:
        raise HTTPException(404, f"No such plan (or expired): {req.plan_id}")
    if plan.brain != brain_id:
        raise HTTPException(400, "plan_id does not belong to this brain")
    result = wiki_agent.apply_plan(b, plan, _db_path(tenant_id))
    atlas_mod.invalidate(brain_id, tenant_id)
    return result


@app.post("/tenant/{tenant_id}/brain/{brain_id}/lint", response_model=LintReport)
async def lint_route(tenant_id: str, brain_id: str) -> LintReport:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return await wiki_agent_pg.lint(tenant_id, b.id, b.name)
    b = _brain(tenant_id, brain_id)
    return await wiki_agent.lint(b)


@app.post("/tenant/{tenant_id}/brain/{brain_id}/solve/plan", response_model=IngestPlan)
async def solve_plan_route(
    tenant_id: str, brain_id: str, issue: LintIssue
) -> IngestPlan:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        return await wiki_agent_pg.solve_plan(tenant_id, b.id, b.name, issue)
    b = _brain(tenant_id, brain_id)
    return await wiki_agent.solve_plan(b, issue)


@app.post("/tenant/{tenant_id}/brain/{brain_id}/solve/apply", response_model=ApplyResult)
async def solve_apply_route(
    tenant_id: str, brain_id: str, req: ApplyPlanRequest
) -> ApplyResult:
    if db.is_postgres():
        b = await _pg_brain(tenant_id, brain_id)
        plan = wiki_agent_pg.get_plan(req.plan_id)
        if plan is None:
            raise HTTPException(404, f"No such plan (or expired): {req.plan_id}")
        if plan.brain != b.name:
            raise HTTPException(400, "plan_id does not belong to this brain")
        result = await wiki_agent_pg.apply_plan(tenant_id, b.id, plan)
        atlas_pg.invalidate(tenant_id, b.id)
        return result

    b = _brain(tenant_id, brain_id)
    plan = wiki_agent.get_plan(req.plan_id)
    if plan is None:
        raise HTTPException(404, f"No such plan (or expired): {req.plan_id}")
    if plan.brain != brain_id:
        raise HTTPException(400, "plan_id does not belong to this brain")
    result = wiki_agent.apply_plan(b, plan, _db_path(tenant_id))
    atlas_mod.invalidate(brain_id, tenant_id)
    return result


@app.get("/tenant/{tenant_id}/brain/{brain_id}/plan/{plan_id}", response_model=IngestPlan)
def get_plan_route(tenant_id: str, brain_id: str, plan_id: str) -> IngestPlan:
    # Plan store is shared across backends (same module-level dict).
    plan = wiki_agent.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, f"No such plan (or expired): {plan_id}")
    if plan.brain != brain_id:
        raise HTTPException(400, "plan_id does not belong to this brain")
    return plan


def _brain(tenant_id: str, brain_id: str):
    """Disk-backend brain resolver. Postgres routes go through `_pg_brain`."""
    try:
        return get_brain(tenant_id, brain_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


def run() -> None:
    import uvicorn

    uvicorn.run("kairos_memory.main:app", host="127.0.0.1", port=8001, reload=False)


if __name__ == "__main__":
    run()
