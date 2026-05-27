"""Atlas builder — purpose extraction, entity/concept caps, mtime-keyed cache."""

from __future__ import annotations

from disease360_memory import atlas as atlas_mod


def _write(brain, rel: str, body: str) -> None:
    p = brain.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_purpose_prefers_frontmatter(make_brain):
    brain = make_brain("A")
    _write(
        brain,
        "wiki/overview.md",
        "---\npurpose: A specific stated purpose.\n---\n\n# Overview\n\nbody.",
    )
    out = atlas_mod._brain_atlas(brain)
    assert out["purpose"] == "A specific stated purpose."


def test_purpose_falls_back_to_first_paragraph(make_brain):
    brain = make_brain("B")
    _write(brain, "wiki/overview.md", "# Overview\n\nA narrative paragraph about the brain.")
    atlas_mod.invalidate("B")
    out = atlas_mod._brain_atlas(brain)
    assert "narrative paragraph" in out["purpose"]


def test_purpose_falls_back_to_id_without_overview(make_brain):
    brain = make_brain("C")
    out = atlas_mod._brain_atlas(brain)
    assert out["purpose"] == "C"


def test_collect_pages_caps_results(make_brain):
    brain = make_brain("D")
    for i in range(20):
        _write(brain, f"wiki/entities/e{i}.md", f"# Entity {i}\n\nBlurb {i}.")
    out = atlas_mod._brain_atlas(brain)
    assert len(out["key_entities"]) == atlas_mod.MAX_ENTITIES_PER_BRAIN


def test_strip_wikilinks_uses_alias_when_present():
    assert atlas_mod._strip_wikilinks("see [[foo|the foo]]") == "see the foo"
    assert atlas_mod._strip_wikilinks("see [[foo]]") == "see foo"


def test_truncate_appends_ellipsis():
    out = atlas_mod._truncate("a " * 200, 20)
    assert len(out) <= 20
    assert out.endswith("…")


def test_cache_returns_same_payload_until_invalidated(make_brain):
    brain = make_brain("E")
    _write(brain, "wiki/overview.md", "---\npurpose: First.\n---\n\n# Overview\n")
    first = atlas_mod._brain_atlas(brain)
    # Mutate without bumping mtime path: write same file with new content but
    # rely on invalidate() to drop the cache.
    (brain.wiki_dir / "overview.md").write_text(
        "---\npurpose: Second.\n---\n\n# Overview\n", encoding="utf-8"
    )
    atlas_mod.invalidate("E")
    second = atlas_mod._brain_atlas(brain)
    assert first["purpose"] == "First."
    assert second["purpose"] == "Second."
