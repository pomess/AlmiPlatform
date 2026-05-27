"""SQLite FTS5 mirror of vault wiki pages. Rebuilt on demand."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .registry import Brain
from .vault import list_markdown, read_page

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    brain UNINDEXED,
    path UNINDEXED,
    title,
    body,
    tags,
    tokenize='porter unicode61'
);
"""


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db_path)
    c.executescript(_SCHEMA)
    return c


def reindex(brain: Brain, db_path: Path) -> int:
    c = _conn(db_path)
    try:
        c.execute("DELETE FROM pages_fts WHERE brain = ?", (brain.id,))
        n = 0
        for f in list_markdown(brain.wiki_dir):
            rel = str(f.relative_to(brain.root)).replace("\\", "/")
            page = read_page(brain.root, rel)
            tags = page.frontmatter.get("tags") or []
            if isinstance(tags, list):
                tags_s = " ".join(str(t) for t in tags)
            else:
                tags_s = str(tags)
            c.execute(
                "INSERT INTO pages_fts(brain, path, title, body, tags) VALUES (?,?,?,?,?)",
                (brain.id, rel, page.title, page.body, tags_s),
            )
            n += 1
        c.commit()
        return n
    finally:
        c.close()


def search(brain: Brain, db_path: Path, query: str, limit: int = 20):
    c = _conn(db_path)
    try:
        # FTS5 query syntax — escape double quotes by wrapping the user query
        q = query.replace('"', '""')
        rows = c.execute(
            """
            SELECT path, title,
                   snippet(pages_fts, 3, '<mark>', '</mark>', '...', 12) AS snip,
                   bm25(pages_fts) AS score
              FROM pages_fts
             WHERE brain = ? AND pages_fts MATCH ?
             ORDER BY score
             LIMIT ?
            """,
            (brain.id, f'"{q}"', limit),
        ).fetchall()
        return [
            {"brain": brain.id, "path": r[0], "title": r[1], "snippet": r[2], "score": float(r[3])}
            for r in rows
        ]
    finally:
        c.close()


def search_all(db_path: Path, query: str, limit: int = 20):
    """Search every brain's pages in a single FTS5 query. Hits are tagged with `brain`."""
    c = _conn(db_path)
    try:
        q = query.replace('"', '""')
        rows = c.execute(
            """
            SELECT brain, path, title,
                   snippet(pages_fts, 3, '<mark>', '</mark>', '...', 12) AS snip,
                   bm25(pages_fts) AS score
              FROM pages_fts
             WHERE pages_fts MATCH ?
             ORDER BY score
             LIMIT ?
            """,
            (f'"{q}"', limit),
        ).fetchall()
        return [
            {"brain": r[0], "path": r[1], "title": r[2], "snippet": r[3], "score": float(r[4])}
            for r in rows
        ]
    finally:
        c.close()
