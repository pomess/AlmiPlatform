"""Graph builder — node emission, link resolution, layer priority."""

from __future__ import annotations

from kairos_memory.graph import build


def _write(brain, rel: str, body: str) -> None:
    p = brain.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_build_emits_nodes_and_resolved_edges(make_brain):
    brain = make_brain("G")
    _write(brain, "wiki/foo.md", "# Foo\n\nLinks to [[bar]].")
    _write(brain, "wiki/bar.md", "# Bar\n\nLinks to [[foo]].")
    g = build(brain)
    ids = sorted(n.id for n in g.nodes)
    assert "wiki/foo.md" in ids and "wiki/bar.md" in ids
    edges = {(e.source, e.target) for e in g.edges}
    assert ("wiki/foo.md", "wiki/bar.md") in edges
    assert ("wiki/bar.md", "wiki/foo.md") in edges


def test_unresolvable_links_dropped(make_brain):
    brain = make_brain("G2")
    _write(brain, "wiki/foo.md", "# Foo\n\n[[ghost]] [[also-missing]]")
    g = build(brain)
    assert all(e.source != e.target for e in g.edges)
    # Only `wiki/foo.md` plus the layout files; no phantom nodes.
    for node in g.nodes:
        assert "ghost" not in node.id
        assert "missing" not in node.id


def test_resolves_by_title_slug(make_brain):
    brain = make_brain("G3")
    _write(brain, "wiki/page-one.md", "# Custom Title\n\nIntro.")
    _write(brain, "wiki/other.md", "# Other\n\nSee [[Custom Title]].")
    g = build(brain)
    edges = {(e.source, e.target) for e in g.edges}
    assert ("wiki/other.md", "wiki/page-one.md") in edges


def test_layer_priority_keeps_highest(make_brain):
    """If a node id collides between layers, the higher-priority layer wins.

    The hot/index files always exist after ensure_layout(); confirm they get
    their proper layer rather than being clobbered.
    """
    brain = make_brain("G4")
    g = build(brain)
    by_id = {n.id: n for n in g.nodes}
    assert by_id["hot.md"].layer == "hot"
    assert by_id["index.md"].layer == "index"


def test_includes_raw_pages_at_raw_layer(make_brain):
    brain = make_brain("G5")
    _write(brain, "raw/snapshot.md", "# Snapshot\n")
    g = build(brain)
    by_id = {n.id: n for n in g.nodes}
    assert by_id["raw/snapshot.md"].layer == "raw"
