# Disease360 Atlas — AI orientation

This file is loaded into context every session. Read before touching code.

## What Disease360 Atlas is

A **competitive intelligence cockpit** for Almirall's dermatology franchise. It visualizes pharma landscape data (drugs, companies, clinical trials, KOLs, regulatory events) from Unity Catalog and provides AI-powered research via the Vera assistant.

- **Deployed as:** a Databricks App (single FastAPI process serving React SPA + API routes)
- **Data source:** Unity Catalog tables in `{env}_gold_commercial.genai_mcm_d360`
- **AI backend:** Vera — an MLflow ResponsesAgent on Databricks Model Serving (GPT-5-1, 7 subagents, 24+ tools)
- **Target users:** Almirall Medical Affairs and Commercial teams

## Architecture

Single Databricks App, three logical modules:

| Module | Route prefix | Role |
|--------|-------------|------|
| Static | `/` | React 19 SPA (Vite build) |
| Memory | `/api/memory/*` | Reads from Platinum tables (graph, bullseye, trials, KOLs, news) |
| Harness | `/api/harness/*` | News RSS aggregation, Vera proxy (SSE streaming) |

External dependencies:
- **Vera endpoint** (`genai-d360-assistant`) — AI research assistant
- **SQL Warehouse** — query engine for Unity Catalog
- **Vector Search** (`vectorsearch_csa_com`) — semantic retrieval

## Repo layout

```
apps/web/              React 19 + TypeScript cockpit (Vite 6, MapLibre, Three.js, D3)
docs/                  Demo scripts, this orientation
scripts/               fetch_biomcp.py, research_competitors.py, run.py
services/
  harness/             News RSS + Vera SSE proxy + competitor updates
  memory/              Unity Catalog adapter (graph, bullseye, search, pages)
  runtime/             LLM client, deep research pipeline, config
tests/                 pytest suite
app.yaml              Databricks App runtime config
databricks.yml        DABs bundle definition
pyproject.toml        Python package (atlas_harness, atlas_memory, atlas_runtime)
```

## Data layer

### Gold (existing, populated by upstream pipelines)

| Table | Content |
|-------|---------|
| `globaldata_catalyst_metadata` | Regulatory milestones, PDUFA dates |
| `globaldata_companies_metadata` | Company profiles, revenue |
| `globaldata_deals_metadata` | M&A, licensing, partnerships |
| `globaldata_drugsales_metadata` | Historical + forecast drug sales |
| `globaldata_marketeddrugs_metadata` | Approved drugs (MoA, targets, LOE) |
| `globaldata_pipelinedrugs_metadata` | Pipeline drugs (preclinical → Phase III) |
| `globaldata_news_metadata` | Pharma news |
| `openfda_drug_metadata` | FDA approvals |
| `ema_product_information_metadata` | EMA product info |
| `clinical_trials_metadata` | ClinicalTrials.gov |
| `all_kol_minutes_metadata` | KOL meeting minutes |

### Platinum (derived, refreshed by Lakeflow Jobs)

| Table | Feeds |
|-------|-------|
| `platinum_graph_nodes` | Knowledge graph nodes (companies, drugs, indications, mechanisms, KOLs) |
| `platinum_graph_edges` | Relationships (develops, treats, competes_with, sponsors_trial, etc.) |
| `platinum_bullseye` | Competitive positioning by ring/segment with threat scores |
| `platinum_news_events` | Unified event timeline from all sources |
| `platinum_kols` | Enriched KOL profiles |
| `platinum_trials` | Enriched clinical trials with relevance scores |

## Frontend features

- **Dashboard** — MapLibre globe with competitor HQ pins + Almirall hologram
- **Bullseye** — Radial drug-landscape chart (AD, HS, PSO segments)
- **Knowledge Graph** — Force-directed visualization of Platinum graph
- **News Panel** — Daily pharma/derm/competitor feed
- **Vera Chat** — Streaming AI assistant (SSE)
- **Competitor Intel** — Photo cards + structured analysis profiles

## How to work in this repo

- **Read `CONTEXT.md`** for domain language before writing code or copy.
- **Don't duplicate Vera's logic.** The cockpit is a visualization + proxy layer. All AI reasoning, tool use, and retrieval happens in Vera.
- **Memory service is read-only.** It queries pre-computed Platinum tables. No writes to Unity Catalog from the app.
- **News RSS is the only write path.** The harness fetches RSS feeds and can persist to `platinum_news_events` via a Lakeflow Job trigger.
- **Frontend talks to FastAPI, never directly to Databricks.** All UC queries go through the memory module; Vera calls go through the harness proxy.
- **Keep the API contract stable.** The frontend expects specific response shapes from `/api/memory/*` and `/api/harness/*` — see `services/memory/atlas_memory/schemas.py`.

## Dev workflow

```powershell
.\run.ps1          # launches memory + harness + web with colored prefixes
.\stop.ps1         # frees ports 8001 / 8002 / 5173

# Lint
ruff check .
mypy services

# Test
pytest

# Frontend type check
cd apps\web && npx tsc --noEmit
```

## Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABRICKS_APP_PORT` | Databricks App | Port to bind (production) |
| `DATABRICKS_SERVER_HOSTNAME` | All envs | SQL Warehouse server |
| `DATABRICKS_HTTP_PATH` | All envs | SQL Warehouse HTTP path |
| `DATABRICKS_TOKEN` | Local dev only | Personal access token |
| `DATABRICKS_VERA_ENDPOINT` | All envs | Vera Model Serving URL |
| `ATLAS_CATALOG` | All envs | Unity Catalog name (e.g. `dev_gold_commercial`) |
| `ATLAS_SCHEMA` | All envs | Schema name (e.g. `genai_mcm_d360`) |
