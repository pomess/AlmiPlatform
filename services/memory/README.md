# Memory service

**Greenfield FastAPI + markdown vault.** Built from scratch — no code from `Obsidian-Knowledge-Graphs`. The KG project's design (BrainRegistry / VaultManager / WikiAgent / D3 graph / Karpathy 3-layer vault) is the *reference*; the implementation here is original.

## Vault layout (per brain)

```
vault/{brain}/
├── raw/             ← immutable sources (notes dumps, transcripts, web clips)
├── wiki/            ← LLM-maintained markdown (concepts/, entities/, sources/, analyses/)
├── index.md         ← TOC of wiki pages, manually + LLM curated
├── log.md           ← per-day journal
├── hot.md           ← active focus / working set (token-budgeted, see docs/11-hot-cache.md)
└── AGENTS.md        ← schema + instructions for the LLM ingest workflow
```

Markdown is the source of truth. SQLite (FTS5) is a derived index for fast lexical search.

## HTTP API (FastAPI, `localhost:8001`)

- `GET  /brains`                       — list registered brains
- `GET  /brain/{id}/index`             — return rendered `index.md`
- `GET  /brain/{id}/hot`               — return current `hot.md`
- `POST /brain/{id}/append-hot`        — append-only update (silent per actions.yaml)
- `POST /brain/{id}/replace-hot`       — full rewrite (require_approval)
- `GET  /brain/{id}/page?path=…`       — fetch a wiki page (with frontmatter + parsed wikilinks)
- `POST /brain/{id}/note`              — create/update a wiki page (require_approval)
- `GET  /brain/{id}/search?q=…`        — FTS5 lexical search (titles + body + tags)
- `GET  /brain/{id}/graph`             — nodes + edges from wikilink parse (D3-shaped)
- `POST /brain/{id}/raw/ingest`        — drop a file into `raw/` (require_approval)
- `POST /brain/{id}/compact-hot`       — day-close compaction pass (returns proposed diff)

## Modules

- `app/main.py`            — FastAPI app, route registration
- `app/vault.py`           — disk I/O, frontmatter (`python-frontmatter`), wikilink regex `\[\[([^\]|]+)(?:\|[^\]]+)?\]\]`
- `app/registry.py`        — `BrainRegistry` (loads vaults from `vault/` subdirs)
- `app/index_db.py`        — SQLite FTS5 mirror (rebuilt on file change)
- `app/graph.py`           — wikilink graph builder
- `app/compaction.py`      — hot-cache compactor (token-budget aware)
- `app/schemas.py`         — pydantic request/response models

## Deps (greenfield)

- `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `python-frontmatter`, `aiosqlite`, `watchfiles` (re-index on save).

Status: **scaffolded — implement in Phase 1**.
