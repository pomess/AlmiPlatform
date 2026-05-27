"""SQLite FTS5 index — reindex, single-brain search, multi-brain search."""

from __future__ import annotations

from pathlib import Path

from disease360_memory.index_db import reindex, search, search_all


def _write(brain, rel: str, body: str) -> None:
    p = brain.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_reindex_counts_only_wiki_pages(make_brain, tmp_path: Path):
    brain = make_brain("S")
    _write(brain, "wiki/alpha.md", "# Alpha\n\nlangchain notes.")
    _write(brain, "wiki/beta.md", "# Beta\n\nlanggraph notes.")
    _write(brain, "raw/ignored.md", "# Ignored\n\nshould not be indexed.")
    db = tmp_path / "fts.sqlite"
    n = reindex(brain, db)
    assert n == 2


def test_search_returns_hits_with_snippets(make_brain, tmp_path: Path):
    brain = make_brain("S2")
    _write(brain, "wiki/alpha.md", "# Alpha\n\nThe quick brown fox jumps.")
    _write(brain, "wiki/beta.md", "# Beta\n\nUnrelated content.")
    db = tmp_path / "fts.sqlite"
    reindex(brain, db)
    hits = search(brain, db, "fox")
    assert len(hits) == 1
    assert hits[0]["path"] == "wiki/alpha.md"
    assert "<mark>" in hits[0]["snippet"]
    assert hits[0]["brain"] == "S2"


def test_search_returns_empty_for_no_match(make_brain, tmp_path: Path):
    brain = make_brain("S3")
    _write(brain, "wiki/alpha.md", "# Alpha\n\nbody.")
    db = tmp_path / "fts.sqlite"
    reindex(brain, db)
    assert search(brain, db, "nothingmatching") == []


def test_reindex_replaces_old_rows(make_brain, tmp_path: Path):
    brain = make_brain("S4")
    _write(brain, "wiki/alpha.md", "# Alpha\n\nfirst")
    db = tmp_path / "fts.sqlite"
    reindex(brain, db)
    assert search(brain, db, "first")
    # rewrite content; reindex; old term should be gone.
    (brain.wiki_dir / "alpha.md").write_text("# Alpha\n\nsecond", encoding="utf-8")
    reindex(brain, db)
    assert search(brain, db, "first") == []
    assert search(brain, db, "second")


def test_search_all_tags_each_hit_with_brain(make_brain, tmp_path: Path):
    a = make_brain("Alpha")
    b = make_brain("Beta")
    _write(a, "wiki/x.md", "# X\n\nshared keyword.")
    _write(b, "wiki/y.md", "# Y\n\nshared keyword.")
    db = tmp_path / "fts.sqlite"
    reindex(a, db)
    reindex(b, db)
    hits = search_all(db, "shared")
    brains = sorted({h["brain"] for h in hits})
    assert brains == ["Alpha", "Beta"]


def test_search_handles_double_quote_in_query(make_brain, tmp_path: Path):
    brain = make_brain("S5")
    _write(brain, "wiki/a.md", "# A\n\nplain body")
    db = tmp_path / "fts.sqlite"
    reindex(brain, db)
    # Should not raise even with a stray double quote in the query.
    assert search(brain, db, 'plain "weird') == [] or search(brain, db, 'plain "weird')
