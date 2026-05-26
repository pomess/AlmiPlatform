"""URL content extraction via Jina Reader (free, no API key required).

Jina Reader converts any URL to clean markdown by prepending r.jina.ai/.
Fallback to raw httpx GET with basic HTML stripping for resilience.
"""

from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger(__name__)

JINA_PREFIX = "https://r.jina.ai/"
FETCH_TIMEOUT = 15.0
MAX_CONTENT_LENGTH = 50_000  # chars — truncate to avoid blowing subagent context


async def fetch_url(url: str) -> str:
    """Fetch a URL as clean markdown via Jina Reader.

    Returns empty string on failure (never raises).
    """
    jina_url = f"{JINA_PREFIX}{url}"
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(
                jina_url,
                headers={"Accept": "text/markdown", "X-No-Cache": "true"},
            )
            resp.raise_for_status()
            content = resp.text[:MAX_CONTENT_LENGTH]
            return content
    except Exception as exc:
        log.debug("Jina Reader failed for %s, trying raw fetch: %s", url, exc)

    # Fallback: raw fetch with basic HTML tag stripping
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text[:MAX_CONTENT_LENGTH]
            text = _strip_html(text)
            return text
    except Exception as exc:
        log.warning("fetch_url failed entirely for %s: %s", url, exc)
        return ""


def _strip_html(html: str) -> str:
    """Minimal HTML -> plain text conversion."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
