"""Vault parsing & I/O — wikilinks, frontmatter, sections, path safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from disease360_memory.vault import (
    append_to_section,
    parse_wikilinks,
    read_page,
    title_from_body,
    write_page,
)


def test_parse_wikilinks_basic():
    body = "See [[foo]] and [[bar/baz]] plus [[qux|alias]] and [[h#anchor]]."
    links = parse_wikilinks(body)
    targets = [(l.target, l.alias) for l in links]
    assert targets == [
        ("foo", None),
        ("bar/baz", None),
        ("qux", "alias"),
        ("h", None),
    ]


def test_parse_wikilinks_ignores_malformed():
    assert parse_wikilinks("[[]] no link [single] [[broken") == []


def test_title_from_body_uses_first_h1(tmp_path: Path):
    body = "\n\nstuff\n# Real Title\nmore\n"
    assert title_from_body(tmp_path / "x.md", body) == "Real Title"


def test_title_from_body_falls_back_to_filename(tmp_path: Path):
    body = "no heading here"
    assert title_from_body(tmp_path / "my-page_name.md", body) == "My Page Name"


def test_write_then_read_round_trip(tmp_path: Path):
    write_page(tmp_path, "wiki/foo.md", "# Foo\n\nBody with [[bar]].", {"tags": ["x"]})
    page = read_page(tmp_path, "wiki/foo.md")
    assert page.title == "Foo"
    assert page.frontmatter["tags"] == ["x"]
    assert [l.target for l in page.wikilinks] == ["bar"]
    assert page.path == "wiki/foo.md"


def test_read_page_normalizes_windows_path(tmp_path: Path):
    write_page(tmp_path, "wiki/sub/foo.md", "# Foo", None)
    page = read_page(tmp_path, "wiki\\sub\\foo.md")
    assert page.path == "wiki/sub/foo.md"


def test_read_page_rejects_path_escape(tmp_path: Path):
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_page(tmp_path / "vault", "../outside.md")


def test_read_page_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_page(tmp_path, "nope.md")


def test_write_page_rejects_path_escape(tmp_path: Path):
    (tmp_path / "vault").mkdir()
    with pytest.raises(ValueError):
        write_page(tmp_path / "vault", "../escape.md", "x")


def test_append_to_section_creates_section_when_missing():
    out = append_to_section("# Hot\n\nBody.\n", "Today", "- ate breakfast")
    assert "## Today" in out
    assert "- ate breakfast" in out
    assert out.endswith("\n")


def test_append_to_section_appends_inside_existing_section():
    text = (
        "# Hot\n\n"
        "## Today\n\n"
        "- a\n"
        "- b\n\n"
        "## Other\n\n"
        "tail.\n"
    )
    out = append_to_section(text, "Today", "- c")
    today = out.split("## Today", 1)[1].split("## Other", 1)[0]
    assert "- a" in today and "- b" in today and "- c" in today
    # Other section preserved
    assert "tail." in out
    # `- c` lands above `## Other`
    assert out.index("- c") < out.index("## Other")


def test_append_to_section_handles_empty_text():
    out = append_to_section("", "Today", "first")
    assert "## Today" in out and "first" in out
