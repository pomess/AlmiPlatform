# Disease360 Atlas

Competitive intelligence cockpit for Almirall's dermatology franchise (Atopic Dermatitis, Hidradenitis Suppurativa, Psoriasis).

Deployed as a **Databricks App** backed by Unity Catalog Gold/Platinum tables and the Vera AI assistant (MLflow Model Serving).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Databricks App (disease360-atlas)                      │
│                                                         │
│  FastAPI  ─┬─ /static        → React 19 SPA            │
│            ├─ /api/memory/*  → Unity Catalog queries    │
│            ├─ /api/harness/* → News RSS + streaming     │
│            └─ /api/vera/*    → Model Serving proxy      │
└──────────────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
 Unity Catalog       Vera Endpoint      RSS Feeds
 (Platinum layer)    (genai-d360-       (FiercePharma,
  graph_nodes         assistant)         STAT, etc.)
  graph_edges
  bullseye
  news_events
  kols, trials
```

## Quick start (local dev)

```powershell
# Install Python dependencies
uv sync

# Install frontend dependencies
cd apps/web && npm install && cd ../..

# Start dev servers (memory + harness + web)
.\run.ps1
```

Services:
- **Web:** http://localhost:5173
- **Memory:** http://localhost:8001
- **Harness:** http://localhost:8002

## Deployment

Deployed via DABs (Databricks Asset Bundles) + Azure DevOps CI/CD.

```bash
databricks bundle deploy --target dev
databricks bundle run disease360-atlas --target dev
```

## Data layer

All data lives in Unity Catalog under `{env}_gold_commercial.genai_mcm_d360`:

| Layer | Tables | Purpose |
|-------|--------|---------|
| Gold | globaldata_*, ema_*, fda_*, clinical_trials_*, kol_* | Curated source data |
| Platinum | platinum_graph_nodes/edges, platinum_bullseye, platinum_news_events, platinum_kols, platinum_trials | Frontend-optimized views |

## Frontend features

- **Dashboard** — MapLibre globe with 16 pharma competitor HQs + Almirall hologram
- **Bullseye** — Radial drug-landscape visualization (AD, HS, PSO)
- **Knowledge Graph** — Force-directed entity graph from Platinum layer
- **News** — Daily pharma/derm/competitor feed (RSS + GlobalData catalysts)
- **Vera Chat** — AI research assistant (7 subagents, 24+ tools)
- **Competitor Intel** — Structured profiles with pipeline, financials, threats

## Tech stack

- **Frontend:** React 19, TypeScript, Vite 6, MapLibre GL, Three.js, D3
- **Backend:** FastAPI, Python 3.11+, databricks-sql-connector
- **AI:** Vera (GPT-5-1 orchestrator, Deep Agents, LangGraph)
- **Data:** Unity Catalog (Delta Lake), Vector Search, Lakeflow Jobs
- **Deploy:** Databricks Apps, DABs, Azure Pipelines
