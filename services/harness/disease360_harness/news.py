"""Daily news briefing aggregator.

Fetches a fixed list of public RSS feeds in parallel, parses them,
shapes the result into world / tech / ai categories, and caches the
payload for 24 hours so subsequent calls return in <50ms.

The first call of the day pays the cold-fetch cost (~500ms typical
when all feeds are healthy, capped at the per-feed timeout). Per-feed
failures are isolated so a single dead source never breaks the brief.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

log = logging.getLogger(__name__)

ITEMS_PER_SOURCE = 3
PER_FEED_TIMEOUT = 4.0

# YouTube channel for the daily video bulletin. Reuters publishes a
# steady stream of business and healthcare news videos, the closest
# zero-auth public source for pharma-flavored broadcast news. If the
# channel goes quiet, fall back to industry conference/AAD content.
VIDEO_FEED_URL = (
    "https://www.youtube.com/feeds/videos.xml?channel_id=UChqUTb7kYRX8-EiaN3XFrSQ"
)
VIDEO_FEED_SOURCE = "Reuters"
VIDEO_FEED_CHANNEL_ICON = ""


@dataclass(frozen=True)
class FeedSpec:
    source: str
    url: str


FEEDS: dict[str, list[FeedSpec]] = {
    # Pharma & biotech business news — daily deal/approval/readout flow.
    # All URLs verified live.
    "pharma": [
        FeedSpec("FiercePharma", "https://www.fiercepharma.com/rss/xml"),
        FeedSpec("FierceBiotech", "https://www.fiercebiotech.com/rss/xml"),
        FeedSpec("FierceHealthcare", "https://www.fiercehealthcare.com/rss/xml"),
        FeedSpec("BioPharma Dive", "https://www.biopharmadive.com/feeds/news/"),
        FeedSpec(
            "Pharmaceutical Technology",
            "https://www.pharmaceutical-technology.com/feed/",
        ),
        FeedSpec("STAT Pharma", "https://www.statnews.com/category/pharma/feed/"),
        FeedSpec("STAT Biotech", "https://www.statnews.com/category/biotech/feed/"),
        FeedSpec("FirstWord Pharma", "https://www.firstwordpharma.com/rss"),
    ],
    # Dermatology — clinical and scientific news for the AD/HS focus.
    # Most dermatology trade press blocks RSS scrapers; we fall back to the
    # closest live medical/skin sources that publishers leave open.
    "derm": [
        FeedSpec("Medscape Medical News", "https://www.medscape.com/cx/rssfeeds/2700.xml"),
        FeedSpec(
            "ScienceDaily Skin",
            "https://www.sciencedaily.com/rss/health_medicine/skin_care.xml",
        ),
        FeedSpec(
            "Medical Xpress Dermatology",
            "https://medicalxpress.com/rss-feed/dermatology-news/",
        ),
    ],
    # Competitors — corporate newsrooms / press release feeds for the
    # companies that show up on the Disease360 map. Per-feed failures are
    # isolated so a missing corporate feed leaves an empty entry without
    # breaking the panel. Where corporate RSS is unavailable or blocked,
    # we use Google News RSS as a reliable proxy.
    "competitors": [
        FeedSpec("Eli Lilly", "https://investor.lilly.com/rss/news-releases.xml"),
        FeedSpec("Regeneron", "https://newsroom.regeneron.com/rss/news-releases.xml"),
        FeedSpec("Incyte", "https://investor.incyte.com/rss/news-releases.xml"),
        FeedSpec(
            "Sanofi",
            "https://news.google.com/rss/search?q=Sanofi+pharma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "Novartis",
            "https://news.google.com/rss/search?q=Novartis+pharma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "AbbVie",
            "https://news.google.com/rss/search?q=AbbVie+pharma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "Johnson & Johnson",
            "https://news.google.com/rss/search?q=%22Johnson+%26+Johnson%22+pharma&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "Roche",
            "https://news.google.com/rss/search?q=Roche+pharma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "AstraZeneca",
            "https://news.google.com/rss/search?q=AstraZeneca+pharma&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "Galderma",
            "https://news.google.com/rss/search?q=Galderma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "Pfizer",
            "https://news.google.com/rss/search?q=Pfizer+pharma+dermatology&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "UCB",
            "https://news.google.com/rss/search?q=UCB+pharma+bimekizumab&hl=en&gl=US&ceid=US:en",
        ),
        FeedSpec(
            "LEO Pharma",
            "https://news.google.com/rss/search?q=%22LEO+Pharma%22+dermatology&hl=en&gl=US&ceid=US:en",
        ),
    ],
}

_CACHE: dict[str, Any] = {"date": None, "payload": None}
_CACHE_LOCK = asyncio.Lock()


def _today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_title(raw: str) -> str:
    """Strip embedded HTML and decode entities from a feed title.

    Some publishers (FiercePharma, Pharmaceutical Technology, etc.) wrap
    titles in ``<a href=...>`` tags inside their RSS, which feedparser
    returns verbatim. Without this scrub the React panel renders the raw
    markup as text — the "weird code-looking news" the user reported.
    """
    if not raw:
        return ""
    no_tags = _TAG_RE.sub(" ", raw)
    decoded = html.unescape(no_tags)
    return _WS_RE.sub(" ", decoded).strip()


def _parse_bytes(raw: bytes) -> list[dict]:
    """Parse one feed's bytes (sync — call via asyncio.to_thread).

    Returns up to ITEMS_PER_SOURCE items, newest first.
    """
    parsed = feedparser.parse(raw)
    entries = parsed.entries or []
    items: list[dict] = []
    for entry in entries[: ITEMS_PER_SOURCE * 2]:
        title = _clean_title(entry.get("title") or "")
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = (
            entry.get("published")
            or entry.get("updated")
            or entry.get("pubDate")
            or ""
        )
        items.append({"title": title, "link": link, "published": published})
        if len(items) >= ITEMS_PER_SOURCE:
            break
    return items


async def _fetch_one(client: httpx.AsyncClient, feed: FeedSpec) -> dict:
    try:
        r = await client.get(feed.url, timeout=PER_FEED_TIMEOUT)
        r.raise_for_status()
        items = await asyncio.to_thread(_parse_bytes, r.content)
        return {"source": feed.source, "items": items}
    except Exception as exc:
        log.warning("news fetch failed source=%s err=%s", feed.source, exc)
        return {"source": feed.source, "items": [], "error": str(exc)}


def _parse_video_candidates(raw: bytes) -> list[dict]:
    """Parse all non-#shorts videos from a YouTube channel feed."""
    parsed = feedparser.parse(raw)
    candidates: list[dict] = []
    for entry in parsed.entries or []:
        video_id = entry.get("yt_videoid") or ""
        title = _clean_title(entry.get("title") or "")
        if not video_id or not title:
            continue
        lower_title = title.lower()
        if "#shorts" in lower_title or "shorts" in (entry.get("link") or "").lower():
            continue
        candidates.append({
            "source": VIDEO_FEED_SOURCE,
            "video_id": video_id,
            "title": title,
            "link": (entry.get("link") or f"https://www.youtube.com/watch?v={video_id}"),
            "published": entry.get("published") or entry.get("updated") or "",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "channel_icon": VIDEO_FEED_CHANNEL_ICON,
        })
    return candidates


_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could of in on at to for with "
    "and or but not no by from that this it its he she they we you i my "
    "your his her their our us me him them who what when where how why "
    "as if then than so very just also about up out all into over after "
    "before between through during".split()
)


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful lowercase words (>2 chars, no stopwords)."""
    words = set()
    for w in text.lower().split():
        cleaned = "".join(c for c in w if c.isalnum())
        if len(cleaned) > 2 and cleaned not in _STOPWORDS:
            words.add(cleaned)
    return words


def _pick_most_relevant(candidates: list[dict], headlines: list[str]) -> dict | None:
    """Pick the video whose title has the most keyword overlap with headlines."""
    if not candidates:
        return None
    if not headlines:
        return candidates[0]

    headline_keywords = set()
    for h in headlines:
        headline_keywords.update(_extract_keywords(h))

    best = candidates[0]
    best_score = 0
    for video in candidates:
        video_kw = _extract_keywords(video["title"])
        score = len(video_kw & headline_keywords)
        if score > best_score:
            best_score = score
            best = video
    return best


async def _fetch_video_candidates(client: httpx.AsyncClient) -> list[dict]:
    try:
        r = await client.get(VIDEO_FEED_URL, timeout=PER_FEED_TIMEOUT)
        r.raise_for_status()
        return await asyncio.to_thread(_parse_video_candidates, r.content)
    except Exception as exc:
        log.warning("video fetch failed err=%s", exc)
        return []


async def _build_payload() -> dict:
    headers = {
        "User-Agent": (
            "Disease360Harness/0.1 (+https://localhost) "
            "feedparser-aggregator"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    }
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=PER_FEED_TIMEOUT
    ) as client:
        flat: list[tuple[str, asyncio.Task]] = []
        for category, feeds in FEEDS.items():
            for feed in feeds:
                flat.append((category, asyncio.create_task(_fetch_one(client, feed))))
        video_task = asyncio.create_task(_fetch_video_candidates(client))
        results: dict[str, list[dict]] = {c: [] for c in FEEDS}
        for category, task in flat:
            results[category].append(await task)
        video_candidates = await video_task

    # Collect all pharma headlines to rank video relevance.
    headlines: list[str] = []
    for source_block in results.get("pharma", []):
        for item in source_block.get("items", []):
            headlines.append(item.get("title", ""))

    video = _pick_most_relevant(video_candidates, headlines)

    return {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pharma": results["pharma"],
        "derm": results["derm"],
        "competitors": results["competitors"],
        "video": video,
    }


async def get_briefing(force: bool = False) -> dict:
    """Return today's briefing, fetching only if cache is stale or absent."""
    today = _today_utc()
    if not force and _CACHE["date"] == today and _CACHE["payload"] is not None:
        return _CACHE["payload"]
    async with _CACHE_LOCK:
        # Re-check after acquiring the lock — another caller may have filled it.
        if not force and _CACHE["date"] == today and _CACHE["payload"] is not None:
            return _CACHE["payload"]
        payload = await _build_payload()
        _CACHE["date"] = today
        _CACHE["payload"] = payload
        return payload


async def warm_cache() -> None:
    """Best-effort startup warm — never raises."""
    try:
        await get_briefing()
    except Exception as exc:
        log.warning("news warm_cache failed: %s", exc)
