"""Tests for the per-run URL whitelist module."""

from __future__ import annotations

from atlas_runtime.research.url_whitelist import (
    URLWhitelist,
    extract_urls,
    format_violation_message,
)


def test_extract_urls_finds_bare_and_markdown_link():
    text = (
        "Some prose. See https://example.com/foo for context.\n"
        "Also [the docs](https://docs.example.com/page).\n"
    )
    urls = extract_urls(text)
    assert "https://example.com/foo" in urls
    assert "https://docs.example.com/page" in urls


def test_extract_urls_strips_trailing_punctuation():
    urls = extract_urls("See https://example.com/foo, then visit https://x.io/bar.")
    assert "https://example.com/foo" in urls
    assert "https://x.io/bar" in urls
    # Trailing comma/period must not stick to the URL.
    assert "https://example.com/foo," not in urls
    assert "https://x.io/bar." not in urls


def test_extract_urls_normalises_case_and_drops_fragment():
    urls = extract_urls("Visit HTTPS://Example.com/Path#section")
    assert "https://example.com/Path" in urls


def test_whitelist_contains_normalised_url():
    w = URLWhitelist()
    w.add("https://Example.com/page#frag")
    assert w.contains("HTTPS://example.com/page")
    assert w.contains("https://example.com/page#anything")


def test_whitelist_diff_returns_offending():
    w = URLWhitelist()
    w.add("https://allowed.example.com/x")
    seen = {
        "https://allowed.example.com/x",
        "https://invented.example.com/y",
    }
    offending = w.diff(seen)
    assert offending == {"https://invented.example.com/y"}


def test_whitelist_add_many_iterable():
    w = URLWhitelist()
    w.add_many(["https://a.com/", "https://b.com/", ""])  # empty skipped
    assert w.size == 2
    assert w.contains("https://a.com/")
    assert w.contains("https://b.com/")


def test_format_violation_message_lists_offenders_and_guidance():
    msg = format_violation_message(
        "findings.md",
        ["https://invented.com/a", "https://invented.com/b"],
    )
    assert "findings.md" in msg
    assert "https://invented.com/a" in msg
    assert "https://invented.com/b" in msg
    assert "fetch_url" in msg  # guidance mentions a remediation tool
    assert "web_search" in msg


def test_format_violation_message_truncates_long_lists():
    offenders = [f"https://x{i}.com/" for i in range(25)]
    msg = format_violation_message("f.md", offenders)
    assert "...and 5 more" in msg
