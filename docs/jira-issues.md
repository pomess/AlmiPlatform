# Disease360 Atlas — JIRA Issues Reference

> **Epic:** Disease360 Atlas Platform Construction
> **Total:** 15 issues (1 Epic + 4 Stories + 10 Subtasks) | 4 story points

---

## EPIC: Disease360 Atlas Platform Construction

Build a competitive intelligence cockpit for Almirall's dermatology franchise. A Databricks App (FastAPI + React SPA) that visualizes pharma landscape data from Unity Catalog and provides AI-powered research via streaming chat, voice interaction, and an interactive 3D globe.

---

## STORY 1: Project Setup & Backend Data Services [1 pt]

**As a** developer,
**I want** a well-structured backend with a data adapter layer
**so that** the frontend can consume competitive intelligence data from Unity Catalog via REST endpoints.

**Acceptance Criteria:**
- [ ] Monorepo with three Python service packages (memory, harness, runtime)
- [ ] Memory Service exposes 12+ GET endpoints reading from Platinum tables
- [ ] Runtime library provides config management, LLM factory, and prompt caching
- [ ] Dev launcher (`run.py`) starts all services with colored output

### Subtask 1.1: Monorepo scaffolding, runtime library & dev tooling

| Item | Detail |
|------|--------|
| Build system | `pyproject.toml` with hatchling (3 packages: atlas_memory, atlas_harness, atlas_runtime) |
| Runtime lib | env/config loader, LLM factory (Gemini cloud + Ollama local), Gemini context-cache helper |
| Dev launcher | `scripts/run.py` multi-process launcher (memory + harness + Vite) |
| Scripts | `run.ps1` / `stop.ps1` convenience wrappers |
| Quality | pytest config, ruff lint, mypy type checking |

### Subtask 1.2: Memory Service — Unity Catalog REST adapter

| Item | Detail |
|------|--------|
| Framework | FastAPI on port 8001, `databricks-sql-connector` |
| Core endpoints | `/graph`, `/bullseye`, `/news`, `/kols`, `/trials`, `/node/{id}` |
| Tenant routes | `/tenant/{id}/brain/{brain_id}/hot\|index\|graph\|page\|search` |
| Schemas | Pydantic response models for all endpoints |
| Data source | SQL queries against `platinum_*` tables |

---

## STORY 2: AI Agent, Voice & News Services [1 pt]

**As a** user,
**I want** to interact with an AI agent via text and voice, receive streaming responses, and get a daily pharma news briefing
**so that** I can research the competitive landscape hands-free.

**Acceptance Criteria:**
- [ ] LangGraph agent with tools (wiki search, map control, deep research)
- [ ] SSE streaming endpoint with structured event types
- [ ] Full voice pipeline: push-to-talk STT, agent turn, TTS playback
- [ ] News RSS aggregation from 24+ pharma feeds with 24h caching
- [ ] Vera proxy endpoint forwarding to Databricks Model Serving

### Subtask 2.1: LangGraph chat agent + SSE streaming + deep research

| Item | Detail |
|------|--------|
| Agent | `create_deep_agent()` with `AsyncSqliteSaver` checkpointer |
| Tools | `search_wiki`, `read_page`, `fly_to_location`, `show_route`, `clear_map` |
| SSE events | `meta`, `tool`, `tool_done`, `tool_progress`, `token`, `done`, `error` |
| Research | Supervisor → parallel sub-agents → compression → synthesis |
| Infra | SQLite run store, per-turn budget enforcement, query classifier |

### Subtask 2.2: Voice pipeline (Gemini STT/TTS, WebSocket)

| Item | Detail |
|------|--------|
| Streaming STT | WebSocket `/voice/stream/stt` via Gemini Live API |
| Voice turn | `POST /voice/turn` — multipart audio in, SSE response with text + audio |
| TTS | `gemini-3.1-flash-tts-preview`, sentence-splitting for low-latency first audio |
| Caching | Pre-rendered PCM cache for cue phrases, language detection (EN/ES/CA) |
| Client tools | Agent → SSE → browser executes → HTTP result back |

### Subtask 2.3: News RSS aggregator & Vera proxy endpoint

| Item | Detail |
|------|--------|
| RSS feeds | 24+ feeds (pharma, derm, competitors, YouTube) |
| Caching | `feedparser` ingestion with 24h response caching |
| Vera proxy | `POST /vera/stream` → Databricks MLflow ResponsesAgent |
| Competitors | `POST /competitor-update` — BioMCP trial search + deep research |
| Scripts | `fetch_biomcp.py`, `research_competitors.py` batch utilities |

---

## STORY 3: Frontend Cockpit Visualizations [1 pt]

**As an** Almirall analyst,
**I want** an interactive cockpit with a 3D globe, radial drug chart, and knowledge graph
**so that** I can visually explore the competitive landscape and drill into any entity.

**Acceptance Criteria:**
- [ ] React 19 SPA with Vite 6, dark/light theme, glassmorphism design system
- [ ] Dashboard: MapLibre globe with competitor pins + Three.js hologram shader
- [ ] Bullseye: SVG radial chart with 47 drugs across AD/HS/PSO + timeline slider
- [ ] Knowledge Graph: hand-rolled force simulation, SVG rendering, flashcards on click

### Subtask 3.1: React SPA scaffold, routing & design system

| Item | Detail |
|------|--------|
| Stack | Vite 6 + React 19 + TypeScript 5.7, react-router-dom v7 |
| Routing | Two-level: `/` (landing) and `/app/*` (cockpit shell with tabs) |
| Tokens | oklch-based design tokens (`tokens.css`), ~5000 lines cockpit CSS |
| Effects | Glassmorphism header, HUD bracket frames, aurora blobs, dot-pulse |
| Transitions | View Transitions API for landing → cockpit crossfade |
| Theming | Dark/light via `[data-theme]`, localStorage persistence |

### Subtask 3.2: Dashboard — MapLibre globe, Three.js hologram, competitor pins

| Item | Detail |
|------|--------|
| Map | MapLibre GL 5.x, globe projection, CARTO basemaps (theme-aware) |
| Markers | 16 competitor HQ pins with custom SVG markers |
| Hologram | Three.js custom layer: GLSL shader (scanline, fresnel, data-rain) |
| Buildings | OSM Overpass footprint fetch + static JSON fallback |
| Panel | Daily news panel + expandable competitor photo cards |

### Subtask 3.3: Bullseye chart + Knowledge Graph visualization

| Item | Detail |
|------|--------|
| Bullseye | Pure SVG radial chart, concentric phase rings, 47 drugs, color-coded by modality |
| Timeline | Slider 2001–2026, animates drugs to historical positions |
| Interactions | Zoom/pan, drug dossier sidebar on click |
| Graph | Custom force simulation (N-body repulsion, spring edges, center gravity) |
| Rendering | SVG with zoom/pan/drag, node coloring by layer, neighborhood highlighting |
| Details | Flashcard popover via Memory API on node click |

---

## STORY 4: Frontend AI Integration & Deployment [1 pt]

**As a** user, I want to chat with the AI agent via text and voice directly in the cockpit,
**and as a** DevOps engineer I want the app deployed on Databricks with automated data refresh
**so that** the platform is production-ready.

**Acceptance Criteria:**
- [ ] Chat UI with SSE streaming, typewriter effect, tool call visualization
- [ ] Voice agent: AudioWorklet capture, WebSocket STT, TTS playback via AudioContext
- [ ] Landing page with product showcase and animated transitions
- [ ] Databricks App deployment with DABs bundle and daily Lakeflow Job

### Subtask 4.1: Chat + voice UI (SSE streaming, push-to-talk, typewriter)

| Item | Detail |
|------|--------|
| Chat hook | `useStreamChat`: ReadableStream reader, `data:` frame parsing, typewriter drain via rAF |
| Tool UI | Collapsible ToolGroup, deep-research progress steps |
| Vera hook | `useVeraChat`: separate agent, full history, no server thread |
| Voice hook | `useVoiceTurn` (~740 LOC): AudioWorklet 16kHz mono, WebSocket STT, TTS playback |
| Client tools | `fly_to_location` executed in browser, result POSTed back |
| State | Thread persistence in localStorage, research mode toggle |

### Subtask 4.2: Landing page, competitor intel cards & Databricks deployment

| Item | Detail |
|------|--------|
| Landing | Multi-section marketing, parallax, IntersectionObserver fade-ups |
| Showcases | Static bullseye snapshot, mock globe, mock graph SVG |
| Competitors | Photo cards with Wikipedia/curated photos, therapy areas, deep analysis |
| App config | `app.yaml`: entry point, env vars, SQL Warehouse resource binding |
| DABs bundle | `databricks.yml`: dev/tst/prod targets, React SPA artifact upload |
| Jobs | `refresh-platinum` daily cron at 06:00 UTC |
| Entrypoint | `atlas_app.py`: FastAPI serving static SPA + mounting service routers |

---

## Quick Reference

| # | Type | Title | Pts | Parent |
|---|------|-------|-----|--------|
| 1 | Epic | Disease360 Atlas Platform Construction | — | — |
| 2 | Story | Project Setup & Backend Data Services | 1 | Epic |
| 3 | Sub-task | Monorepo scaffolding, runtime library & dev tooling | — | Story 1 |
| 4 | Sub-task | Memory Service — Unity Catalog REST adapter | — | Story 1 |
| 5 | Story | AI Agent, Voice & News Services | 1 | Epic |
| 6 | Sub-task | LangGraph chat agent + SSE streaming + deep research | — | Story 2 |
| 7 | Sub-task | Voice pipeline (Gemini STT/TTS, WebSocket) | — | Story 2 |
| 8 | Sub-task | News RSS aggregator & Vera proxy endpoint | — | Story 2 |
| 9 | Story | Frontend Cockpit Visualizations | 1 | Epic |
| 10 | Sub-task | React SPA scaffold, routing & design system | — | Story 3 |
| 11 | Sub-task | Dashboard — MapLibre globe, Three.js hologram, competitor pins | — | Story 3 |
| 12 | Sub-task | Bullseye chart + Knowledge Graph visualization | — | Story 3 |
| 13 | Story | Frontend AI Integration & Deployment | 1 | Epic |
| 14 | Sub-task | Chat + voice UI (SSE streaming, push-to-talk, typewriter) | — | Story 4 |
| 15 | Sub-task | Landing page, competitor intel cards & Databricks deployment | — | Story 4 |
