# Karpathy's LLM Wiki — the "Second Brain" pattern

> Author: **Andrej Karpathy** (ex-OpenAI founding member, ex-Tesla AI director, Eureka Labs).
> Published: **April 2026** as a GitHub gist. 16M+ views on the X post that introduced it. 5,000+ stars on the gist within days.
> Source: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>

> **This is a *pattern*, not a product.** The gist is explicitly an "idea file" meant to be copy-pasted into your own LLM agent. Your agent then collaborates with you to instantiate a concrete version that fits your domain.

## The core idea (one paragraph)

Most people use LLMs over documents via **RAG**: upload files, retrieve chunks at query time, generate an answer. The LLM rediscovers the knowledge from scratch on every question. Nothing accumulates.

Karpathy's pattern flips this. **The LLM incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that sits between you and the raw sources. New source comes in → LLM reads it → updates entity pages, revises summaries, flags contradictions. **The knowledge is compiled once, then kept current**, not re-derived per query.

The wiki is a *compounding artifact*. Cross-references are pre-built. Contradictions are pre-flagged. The synthesis already reflects everything you've read.

> *"Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase."*
> — Karpathy

## The three-layer architecture

```
my-vault/
├── raw/                   # Layer 1: IMMUTABLE source documents
│   ├── articles/          # Web clippings, papers, transcripts…
│   ├── papers/
│   ├── repos/
│   ├── data/
│   ├── images/
│   └── assets/
│
├── wiki/                  # Layer 2: LLM-GENERATED markdown
│   ├── index.md           # Content catalog (updated every ingest)
│   ├── log.md             # Append-only chronological record
│   ├── overview.md
│   ├── concepts/          # Concept pages
│   ├── entities/          # Entity pages (people, orgs, products)
│   ├── sources/           # One summary per ingested source
│   └── comparisons/       # Comparison/analysis pages
│
├── outputs/               # Generated reports, slide decks, lint results
├── CLAUDE.md              # Layer 3: SCHEMA — how the LLM maintains the wiki
└── .gitignore
```

| Layer | Owner | Role |
|---|---|---|
| **Raw sources** (`raw/`) | You | Source of truth. LLM only reads, never writes. |
| **Wiki** (`wiki/`) | The LLM | The compiled knowledge graph. You read; LLM writes. |
| **Schema** (`CLAUDE.md` or `AGENTS.md`) | You + LLM, co-evolved | Conventions, page templates, workflows. The "config file" that turns a generic LLM into a disciplined wiki maintainer. |

## The three operations

### 1. Ingest
You drop a new source into `raw/` and tell the agent to process it.

The LLM:
1. Reads the document, discusses takeaways with you.
2. Creates a summary in `wiki/sources/`.
3. Updates 10–15 related concept/entity pages.
4. Creates new pages if needed.
5. Updates `index.md`.
6. Appends to `log.md`.

A single ingest can touch dozens of pages.

### 2. Query
You ask a question. The LLM reads `index.md` first, picks relevant pages, reads them, synthesizes an answer with `[[wikilink]]` citations.

> Crucial insight: **valuable answers should be filed back into the wiki as new pages.** The wiki compounds from queries too, not just ingests.

### 3. Lint
Periodic health check. The LLM scans for:
- Contradictions between pages.
- Orphan pages with no inbound links.
- Concepts referenced but lacking their own page.
- Stale claims superseded by newer sources.
- Investigation gaps.

> Think of it as **`eslint` for knowledge.**

## The two structural files

| File | Purpose |
|---|---|
| `index.md` | **Content-oriented.** Catalog of every page with a one-line summary. The LLM reads this first to navigate. Works at moderate scale (~100 sources, hundreds of pages) without needing embeddings/RAG infrastructure. |
| `log.md` | **Chronological.** Append-only record of every operation. Tip: prefix entries `## [YYYY-MM-DD] ingest \| Title` so `grep "^## \[" log.md` gives you the timeline. |

## YAML frontmatter convention

```yaml
---
title: Page Title
type: concept | entity | source-summary | comparison
sources:
  - raw/papers/filename.md
related:
  - "[[related-concept]]"
created: 2026-04-01
updated: 2026-04-27
confidence: high | medium | low
---
```

The `confidence` field is gold — combined with Dataview-style queries you can surface "all my low-confidence pages that haven't been updated in 30 days" and feed those to the lint pass.

## Recommended toolchain

| Tool | Role |
|---|---|
| **Claude Code** (or Codex / OpenCode / Pi) | The agent that maintains the wiki |
| **Obsidian** | The frontend. Graph view, backlinks, search |
| **Obsidian Web Clipper** | Browser → markdown into `raw/` |
| **QMD** ([github.com/tobi/qmd](https://github.com/tobi/qmd)) | On-device hybrid BM25 + vector + LLM-rerank search; CLI + MCP server. Recommended by Karpathy. (Built by Tobi Lutke, Shopify CEO.) |
| **Dataview** | Obsidian plugin for queries over frontmatter |
| **Marp** | Markdown → slide decks |
| **Git** | Version history for the entire knowledge base, free |

## LLM Wiki vs RAG — when to use which

| | LLM Wiki | RAG |
|---|---|---|
| **Sweet spot** | Personal/team (50–200 sources, sub-100K tokens of wiki) | Enterprise (millions of docs) |
| **State** | Stateful — knowledge compounds | Stateless — every query is fresh |
| **Infrastructure** | Folder of `.md` files. That's it. | Vector DB, embedding pipeline, retrieval logic |
| **Cross-references** | Pre-built by the LLM, always available | Discovered ad-hoc per query |
| **Token cost per query** | Low (read index + targeted pages) | High (retrieve + rerank + generate) |
| **Traceability** | Source-level (`raw/` link) | Chunk-level, often lossy |
| **Contradictions** | Flagged during lint | Undetected — conflicting chunks coexist |

## Intellectual lineage

- **Vannevar Bush — Memex (1945)**: a mechanical desk that stores all your books and creates *associative trails* between them. Failed because maintenance was manual. The LLM solves the maintenance problem.
- **Tiago Forte — Building a Second Brain (2022)**: the popular note-taking system. Karpathy's pattern is the LLM-managed version.
- **Karpathy's own arc**:
  1. **Vibe coding** (Feb 2025) — accept LLM-generated code without line-by-line review.
  2. **Agentic engineering** (Jan 2026) — humans orchestrate agents instead of writing code.
  3. **LLM knowledge bases** (Apr 2026) — AI manages knowledge, human is curator.

## Tips & tricks (from the gist)

- **Hot cache file** — community feedback (e.g., AgriciDaniel's `claude-obsidian` v1.6) consistently identifies a "hot cache" or working-context file as the *single highest-leverage piece*. Miss it and the model re-derives context every session.
- **Download images locally** — Obsidian Web Clipper hotkey `Ctrl+Shift+D` downloads attachments. LLMs can't read inline images in one pass; they read text first, then view referenced images separately.
- **`raw/` is immutable** — every claim in the wiki should trace to a file in `raw/`. This is your safeguard against model collapse / hallucination drift.
- **The wiki is just a git repo** — version history, branching, collaboration for free.

## Known limitations

- **The grunt work IS sometimes the learning.** Outsourcing summarization can mean you don't internalize the material. The wiki is a reference system, not a substitute for thinking.
- **Context window degradation** above ~200–300K tokens of active context. Mitigate by reading `index.md` first, then drilling into specific pages.
- **Model collapse risk** — repeated LLM rewriting can compound subtle errors. Mitigate via the immutable `raw/` layer, lint passes, and git history.
- **Complexity ceiling** — works best at 50–200 source scale. Beyond that, you may need extensions (LLM Wiki v2 — see community implementations) or a real RAG pipeline.

## Why this matters for our build

**Our existing `Obsidian-Knowledge-Graphs` project is already an implementation of this exact pattern.** See [05-existing-project-audit.md](05-existing-project-audit.md). We don't need to design the memory layer — we already have it.

Specifically, our project already has:
- The three layers (`raw/`, `wiki/`, `AGENTS.md`/`CLAUDE.md`).
- The three operations (ingest, query/chat, lint).
- `index.md`, `log.md`, `hot.md`.
- Wikilinks, frontmatter, graph view (D3-force).
- Multi-brain support (BrainRegistry).

That's a massive head start. The work for JARVIS is mostly *bolting an action layer onto a memory layer that already exists*.

## Sources

- Primary: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- *blog.starmorph.com* — "How to Build Karpathy's LLM Wiki: The Complete Guide…" (2026-04-09)
- *techstrong.ai* — "Karpathy's Instructions for Building an AI-Driven Second Brain" (2026-04-07)
- Community implementations: `lucasastorian/llmwiki`, `Ar9av/obsidian-wiki`, `NicholasSpisak/second-brain`, `kfchou/wiki-skills`, `axoviq-ai/synthadoc`, `Beever-AI/beever-atlas`, and many more — most landed within a week of the gist going viral.
