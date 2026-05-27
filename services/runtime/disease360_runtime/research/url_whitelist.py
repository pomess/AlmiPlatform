"""Per-run URL whitelist guarding subagent write_file calls.

Subagents are forbidden from citing URLs they did not actually observe via
``web_search`` or ``fetch_url``. The system prompt says so, but models
violate the rule routinely — a recent live run produced 13/28 hallucinated
URLs. This module enforces the rule at the tool boundary instead of trusting
the model.

The whitelist grows as the subagent uses real tools:
- Each ``web_search`` call adds every URL in ``result.chunks``.
- Each successful ``fetch_url`` call adds the input URL itself.

URLs scraped from inside fetched-page content are NOT auto-added — the
subagent must explicitly fetch a URL before citing it.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

# Bare URL anywhere in markdown (e.g. ``See https://example.com``).
URL_PATTERN = re.compile(r"https?://[^\s\)\]\"'>]+")

# Markdown link form: ``[text](https://example.com)``.
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")


def _normalise(url: str) -> str:
    """Canonicalise a URL for whitelist comparison.

    Strips trailing punctuation that often clings to URLs in prose, drops
    fragments (``#section``), and lower-cases the scheme + host. Keeps the
    path/query intact since those are typically meaningful for matching a
    cited page to a real one.
    """
    cleaned = url.strip().rstrip(".,;:")
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return cleaned
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    # Drop fragment; keep path + query.
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))


def extract_urls(text: str) -> set[str]:
    """Return all distinct URLs found in ``text``, normalised.

    Catches both ``[text](url)`` markdown links and bare URLs.
    """
    urls: set[str] = set()
    for match in LINK_PATTERN.finditer(text):
        urls.add(_normalise(match.group(2)))
    for match in URL_PATTERN.finditer(text):
        urls.add(_normalise(match.group(0)))
    # Filter out anything obviously not a URL after stripping.
    return {u for u in urls if u.startswith(("http://", "https://"))}


class URLWhitelist:
    """Per-run set of URLs the subagent has actually observed.

    Thread-safety not required; the research pipeline is async-single-threaded.
    """

    def __init__(self) -> None:
        self._urls: set[str] = set()

    def add(self, url: str) -> None:
        if url:
            self._urls.add(_normalise(url))

    def add_many(self, urls) -> None:  # noqa: ANN001 — accepts any iterable
        for url in urls:
            self.add(url)

    def contains(self, url: str) -> bool:
        return _normalise(url) in self._urls

    def diff(self, urls) -> set[str]:  # noqa: ANN001
        """Return the subset of ``urls`` not currently whitelisted."""
        return {u for u in urls if _normalise(u) not in self._urls}

    @property
    def size(self) -> int:
        return len(self._urls)

    @property
    def urls(self) -> set[str]:
        return set(self._urls)


def format_violation_message(name: str, offending: list[str]) -> str:
    """Compose the error string returned to the subagent on a guarded write.

    The message must guide the model toward a productive next step, not just
    refuse — otherwise the subagent retries the same write or gives up.
    """
    bullet_list = "\n".join(f"- {u}" for u in offending[:20])
    extra = (
        f"\n  ...and {len(offending) - 20} more"
        if len(offending) > 20
        else ""
    )
    return (
        f"Cannot write {name}: the body contains URLs not seen in any "
        f"tool result.\n\n"
        f"Offending URLs:\n{bullet_list}{extra}\n\n"
        f"You may only cite URLs returned by web_search results or successfully "
        f"fetched via fetch_url. To proceed:\n"
        f"  (a) Remove or replace these URLs with real sources you have "
        f"observed, OR\n"
        f"  (b) Run web_search to find legitimate sources for these claims, OR\n"
        f"  (c) Run fetch_url on each URL above to confirm it exists, then "
        f"re-write.\n\n"
        f"If you cannot find a real source, drop the claim entirely. Do NOT "
        f"invent URLs — the verifier will catch them and the report will be "
        f"rejected."
    )
