"""Citation verifier: URL liveness + NLI faithfulness checking.

Verifies every citation extracted from subagent artifacts:
1. HEAD-check each URL (3s timeout) - flag dead URLs
2. Wayback Machine fallback for dead URLs
3. Fetch the actual page (or Wayback snapshot) and NLI-check the claim
   against its REAL content, not against the subagent's own writeup.
4. Writes /verified_findings.md to the virtual FS
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI

from kairos_runtime.config import require

from .cache import RunCache
from .config import get_model
from .fetch import fetch_url
from .filesystem import VirtualFS
from .prompts import VERIFIER_NLI_PROMPT, VERIFIER_NLI_BATCH_PROMPT
from .state import Citation, VerificationReport
from .url_whitelist import LINK_PATTERN, URL_PATTERN
from .usage import attach as _attach_usage

log = logging.getLogger(__name__)

URL_CHECK_TIMEOUT = 3.0
URL_CHECK_CONCURRENCY = 10
PAGE_FETCH_CONCURRENCY = 5
NLI_CONCURRENCY = 5
WAYBACK_API = "https://archive.org/wayback/available"

_NliVerdict = Literal["entails", "contradicts", "not_mentioned"]


async def _check_url_liveness(url: str) -> tuple[str, bool, str | None]:
    """Check if a URL is live. Returns (url, is_live, wayback_url_or_None).

    Strategy: HEAD first (cheap), then GET on failure. Many real sites
    (Cloudflare-fronted blogs, anti-bot WAFs, sites that simply don't
    implement HEAD) will 403/405/timeout on HEAD but serve GET fine.
    Treating HEAD failure as "dead" misclassifies these as hallucinated.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; KairosResearchBot/1.0; "
            "+https://github.com/anthropics/claude-code)"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(
            timeout=URL_CHECK_TIMEOUT, headers=headers
        ) as client:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code < 400:
                return (url, True, None)
    except Exception:
        pass

    # HEAD failed or returned 4xx/5xx — try a GET with a small Range to
    # avoid pulling the full body. Definitive 404/410 from GET is the only
    # signal we trust for "this URL really doesn't exist".
    try:
        async with httpx.AsyncClient(
            timeout=URL_CHECK_TIMEOUT * 2,
            headers={**headers, "Range": "bytes=0-2047"},
        ) as client:
            resp = await client.get(url, follow_redirects=True)
            # 2xx, 3xx (already followed), or 206 (partial) all mean live.
            # 401/403 means the page exists but is gated — still "live"
            # for citation purposes; the page text just may not verify.
            if resp.status_code < 400 or resp.status_code in (401, 403, 429):
                return (url, True, None)
    except Exception:
        pass

    # Both HEAD and GET failed — try Wayback Machine
    wayback_url = await _get_wayback_url(url)
    return (url, False, wayback_url)


async def _get_wayback_url(url: str) -> str | None:
    """Query Wayback Machine for a snapshot of a dead URL."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(WAYBACK_API, params={"url": url})
            if resp.status_code == 200:
                data = resp.json()
                snapshot = data.get("archived_snapshots", {}).get("closest", {})
                if snapshot.get("available"):
                    return snapshot.get("url")
    except Exception as exc:
        log.debug("Wayback lookup failed for %s: %s", url, exc)
    return None


async def check_urls_batch(
    urls: list[str], cache: RunCache | None = None
) -> dict[str, tuple[bool, str | None]]:
    """Batch-check URL liveness with concurrency limit.

    If `cache` is provided, URLs the subagent already fetched successfully
    are treated as live without re-probing — successful retrieval is the
    strongest possible liveness signal.

    Returns dict of url -> (is_live, wayback_url_or_None).
    """
    sem = asyncio.Semaphore(URL_CHECK_CONCURRENCY)
    results: dict[str, tuple[bool, str | None]] = {}

    async def _check(url: str) -> None:
        if cache and cache.has("fetch", url) and (cache.get("fetch", url) or "").strip():
            results[url] = (True, None)
            return
        async with sem:
            _, is_live, wayback = await _check_url_liveness(url)
            results[url] = (is_live, wayback)

    await asyncio.gather(*[_check(u) for u in urls], return_exceptions=True)
    return results


def extract_citations_from_findings(
    vfs: VirtualFS,
) -> list[tuple[str, str]]:
    """Extract (claim_context, url) pairs from all findings.

    The subagent contract is:
      - Findings body uses inline ``[n]`` markers next to claims.
      - A trailing ``## Sources`` block maps ``[n] → URL``.

    For each ``[n]`` marker in the body, we pull the *sentence* containing
    it as the claim, look up its URL in the Sources block, and emit a
    ``(claim_sentence, url)`` pair. This is what NLI actually needs.

    Falls back to the old "URL with surrounding lines" extraction for
    findings that don't follow the ``[n]`` + Sources convention (e.g.
    inline markdown links, bare URLs).
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    url_pattern = URL_PATTERN
    link_pattern = LINK_PATTERN
    citation_marker = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")

    for path, content in vfs.files.items():
        if not path.endswith(".md"):
            continue
        if path == "/verified_findings.md":
            continue  # never verify the verifier's own output

        body, sources_block = _split_sources(content)
        n_to_url = _parse_sources_map(sources_block)

        # Pass 1: [n] markers in the body → look up URL in sources map.
        if n_to_url:
            for sentence in _iter_sentences(body):
                for match in citation_marker.finditer(sentence):
                    nums_raw = match.group(1)
                    for num_str in re.split(r"\s*,\s*", nums_raw):
                        try:
                            n = int(num_str)
                        except ValueError:
                            continue
                        url = n_to_url.get(n)
                        if not url:
                            continue
                        claim = _strip_citation_markers(sentence)[:500]
                        key = (claim, url)
                        if key in seen:
                            continue
                        seen.add(key)
                        pairs.append(key)

        # Pass 2: inline markdown links and bare URLs anywhere in the file.
        # Falls back to surrounding-line context, but only for URLs that
        # didn't already get a real claim from pass 1. We walk the full
        # content (not just the body) so URLs that appear only in the
        # Sources block still get a liveness check.
        already_paired = {url for _, url in pairs}
        lines = content.splitlines()
        for i, line in enumerate(lines):
            for match in link_pattern.finditer(line):
                url = match.group(2)
                if url in already_paired:
                    continue
                claim = _get_claim_context(lines, i)
                key = (claim, url)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(key)
                already_paired.add(url)

            for match in url_pattern.finditer(line):
                url = match.group(0).rstrip(".,;:")
                if url in already_paired:
                    continue
                claim = _get_claim_context(lines, i)
                key = (claim, url)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(key)
                already_paired.add(url)

    return pairs


_SOURCES_HEADER = re.compile(
    r"(?im)^\s*#{1,6}\s*Sources\b.*$"
)
_SOURCES_LINE = re.compile(
    r"^\s*[-*]?\s*\[?(\d+)\]?\s*[-:.\s]\s*(.*?)$"
)


def _split_sources(content: str) -> tuple[str, str]:
    """Split a findings file into (body, sources_block).

    Sources block is everything from the first ``## Sources`` (or similar)
    to the next top-level header or EOF.
    """
    match = _SOURCES_HEADER.search(content)
    if not match:
        return content, ""
    body = content[: match.start()]
    rest = content[match.end():]
    # Stop at the next header line, if any
    next_header = re.search(r"(?m)^\s*#{1,6}\s+\S", rest)
    if next_header:
        sources_block = rest[: next_header.start()]
    else:
        sources_block = rest
    return body, sources_block


def _parse_sources_map(sources_block: str) -> dict[int, str]:
    """Parse ``[n] ... URL`` lines into ``{n: url}``."""
    if not sources_block.strip():
        return {}
    url_re = URL_PATTERN
    n_to_url: dict[int, str] = {}
    for raw in sources_block.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SOURCES_LINE.match(line)
        if not m:
            # Try bare "[n] url" or "n. url"
            alt = re.match(r"^\s*[-*]?\s*\[?(\d+)\]?[\.\)]?\s+(.*)$", line)
            if not alt:
                continue
            n = int(alt.group(1))
            tail = alt.group(2)
        else:
            n = int(m.group(1))
            tail = m.group(2)
        url_match = url_re.search(tail)
        if url_match:
            n_to_url[n] = url_match.group(0).rstrip(".,;:")
    return n_to_url


def _iter_sentences(text: str) -> list[str]:
    """Yield sentence-ish chunks from a markdown body.

    Splits on sentence terminators and on line/list boundaries so a bullet
    point counts as its own claim even without a final period.
    """
    chunks: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Treat each line as a candidate, then further split on .!? boundaries
        for sentence in re.split(r"(?<=[.!?])\s+", stripped):
            s = sentence.strip()
            if s:
                chunks.append(s)
    return chunks


_INLINE_CITATION = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")


def _strip_citation_markers(sentence: str) -> str:
    return _INLINE_CITATION.sub("", sentence).strip()


def _get_claim_context(lines: list[str], idx: int) -> str:
    """Get the surrounding text context for a citation."""
    start = max(0, idx - 1)
    end = min(len(lines), idx + 2)
    return " ".join(lines[start:end]).strip()[:500]


async def nli_check(
    claim: str,
    source_text: str,
    *,
    meter: Any = None,
) -> _NliVerdict:
    """Run NLI faithfulness check on a single claim against source text."""
    if not source_text.strip():
        return "not_mentioned"

    model_id = get_model("verifier")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    llm = _attach_usage(llm, meter, "verifier")

    prompt = VERIFIER_NLI_PROMPT.format(
        claim=claim[:1000],
        source_text=source_text[:3000],
    )

    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = resp.content
        if isinstance(content, list):
            content = " ".join(str(p) for p in content)
        verdict = content.strip().upper()
        if "ENTAILS" in verdict:
            return "entails"
        elif "CONTRADICTS" in verdict:
            return "contradicts"
        else:
            return "not_mentioned"
    except Exception as exc:
        log.warning("NLI check failed: %s", exc)
        return "not_mentioned"


_VERDICT_LINE = re.compile(r"^\s*(\d+)\s*[:.\-)]\s*(\w+)\s*$", re.MULTILINE)


def _parse_batch_verdicts(
    text: str, n_claims: int
) -> list[_NliVerdict]:
    """Parse a multi-claim verifier response into ``n_claims`` verdicts.

    Expected response format is one line per claim::

        1: ENTAILS
        2: NOT_MENTIONED
        3: CONTRADICTS

    Missing or unparseable lines fall back to ``not_mentioned``.
    """
    verdicts: list[_NliVerdict] = ["not_mentioned"] * n_claims
    for m in _VERDICT_LINE.finditer(text):
        try:
            idx = int(m.group(1)) - 1
        except ValueError:
            continue
        if not (0 <= idx < n_claims):
            continue
        token = m.group(2).strip().upper()
        if "ENTAIL" in token:
            verdicts[idx] = "entails"
        elif "CONTRADICT" in token:
            verdicts[idx] = "contradicts"
        else:
            verdicts[idx] = "not_mentioned"
    return verdicts


async def nli_check_batch(
    claims: list[str],
    source_text: str,
    *,
    meter: Any = None,
) -> list[_NliVerdict]:
    """Run NLI on multiple claims against ONE source page in a single LLM call.

    Returns one verdict per claim in input order. Falls back to ``not_mentioned``
    for unparseable rows. Empty source -> all ``not_mentioned``.
    """
    if not claims:
        return []
    if len(claims) == 1:
        return [await nli_check(claims[0], source_text, meter=meter)]
    if not source_text.strip():
        return ["not_mentioned"] * len(claims)

    model_id = get_model("verifier")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    llm = _attach_usage(llm, meter, "verifier")

    numbered = "\n".join(
        f"{i + 1}. {c[:800]}" for i, c in enumerate(claims)
    )
    prompt = VERIFIER_NLI_BATCH_PROMPT.format(
        source_text=source_text[:6000],
        claims=numbered,
        n=len(claims),
    )

    try:
        resp = await llm.ainvoke([{"role": "user", "content": prompt}])
        content = resp.content
        if isinstance(content, list):
            content = " ".join(str(p) for p in content)
        return _parse_batch_verdicts(content, len(claims))
    except Exception as exc:
        log.warning("Batch NLI check failed: %s — falling back to per-claim", exc)
        # Per-claim fallback so a single bad page doesn't lose all verdicts.
        results: list[_NliVerdict] = []
        for c in claims:
            results.append(await nli_check(c, source_text, meter=meter))
        return results


async def _fetch_page_text(
    url: str, cache: RunCache | None
) -> str:
    """Fetch a URL via the existing RunCache + fetch_url. Returns ''."""
    if cache and cache.has("fetch", url):
        return cache.get("fetch", url) or ""
    text = await fetch_url(url)
    if cache and text:
        cache.put("fetch", url, text)
    return text


async def _fetch_pages_batch(
    urls: list[str], cache: RunCache | None
) -> dict[str, str]:
    """Concurrent page fetch with a semaphore cap."""
    sem = asyncio.Semaphore(PAGE_FETCH_CONCURRENCY)
    results: dict[str, str] = {}

    async def _one(u: str) -> None:
        async with sem:
            results[u] = await _fetch_page_text(u, cache)

    await asyncio.gather(*[_one(u) for u in urls], return_exceptions=True)
    return results


def _aggregate_verdicts(verdicts: list[_NliVerdict]) -> _NliVerdict:
    """Reduce per-claim verdicts for a single URL to one URL-level verdict.

    A URL counts as ``entails`` if at least one of its claims is supported.
    Otherwise ``contradicts`` if any claim is contradicted (so the source
    appears in `contested_claims`). Else ``not_mentioned``.
    """
    if not verdicts:
        return "not_mentioned"
    if "entails" in verdicts:
        return "entails"
    if "contradicts" in verdicts:
        return "contradicts"
    return "not_mentioned"


async def verify_findings(
    vfs: VirtualFS,
    *,
    skip_nli: bool = False,
    cache: RunCache | None = None,
    meter: Any = None,
) -> tuple[list[Citation], VerificationReport]:
    """Run full verification pipeline on all findings in the VFS.

    1. Extract all citations
    2. Batch URL liveness check (HEAD)
    3. Fetch the real page text (live URL or Wayback snapshot)
    4. NLI-check claims for each URL in a single batched LLM call,
       running URLs concurrently with a small semaphore
    5. Write /verified_findings.md
    6. Return citations and verification report
    """
    citation_pairs = extract_citations_from_findings(vfs)

    if not citation_pairs:
        vfs.write("/verified_findings.md", "No citations found to verify.")
        return [], VerificationReport()

    # Group claims per URL (preserving order), so each URL maps to all the
    # sentences that cite it. The previous code dropped claims 2..N silently
    # because of an early ``if url in seen_urls: continue``.
    claims_per_url: dict[str, list[str]] = {}
    for claim, url in citation_pairs:
        claims_per_url.setdefault(url, []).append(claim)

    unique_urls = list(claims_per_url.keys())

    # Batch URL liveness checks (cache hits short-circuit as live)
    url_status = await check_urls_batch(unique_urls, cache=cache)

    # Fetch real page text for each URL we want to NLI against
    fetch_targets: list[str] = []
    for url in unique_urls:
        is_live, wayback = url_status.get(url, (True, None))
        if is_live:
            fetch_targets.append(url)
        elif wayback:
            fetch_targets.append(wayback)
    page_texts: dict[str, str] = {}
    if not skip_nli and fetch_targets:
        page_texts = await _fetch_pages_batch(fetch_targets, cache)

    # Per-URL batched NLI, run concurrently with a small cap.
    nli_sem = asyncio.Semaphore(NLI_CONCURRENCY)
    verdicts_per_url: dict[str, list[_NliVerdict]] = {}

    async def _nli_for_url(url: str) -> None:
        if skip_nli:
            verdicts_per_url[url] = ["unchecked"] * len(claims_per_url[url])  # type: ignore[list-item]
            return
        is_live, wayback = url_status.get(url, (True, None))
        page_text = ""
        if is_live:
            page_text = page_texts.get(url, "")
        elif wayback:
            page_text = page_texts.get(wayback, "")
        claims = claims_per_url[url]
        if not page_text:
            verdicts_per_url[url] = ["not_mentioned"] * len(claims)
            return
        async with nli_sem:
            verdicts_per_url[url] = await nli_check_batch(
                claims, page_text, meter=meter
            )

    await asyncio.gather(
        *(_nli_for_url(u) for u in unique_urls), return_exceptions=False
    )

    log.info(
        "[verifier] NLI batched: %d URLs, %d claims (vs %d serial calls before)",
        len(unique_urls),
        sum(len(v) for v in claims_per_url.values()),
        sum(len(v) for v in claims_per_url.values()),
    )

    # Build one Citation per URL (matches the existing source-map contract).
    # The span shows the first claim; the verdict aggregates all claims.
    citations: list[Citation] = []
    for idx, url in enumerate(unique_urls):
        is_live, wayback = url_status.get(url, (True, None))
        url_verdicts = verdicts_per_url.get(url, ["not_mentioned"])
        first_claim = claims_per_url[url][0]
        agg = _aggregate_verdicts([v for v in url_verdicts if v != "unchecked"])  # type: ignore[list-item]
        nli_verdict: Literal["entails", "contradicts", "not_mentioned", "unchecked"] = (
            "unchecked" if skip_nli else agg
        )
        citation = Citation(
            index=idx + 1,
            url=url,
            title="",
            span=first_claim[:200],
            verified=True,
            live=is_live,
            wayback_url=wayback,
            nli_verdict=nli_verdict,
        )
        citations.append(citation)

    # Build verification report
    hallucinated = [c.url for c in citations if not c.live and not c.wayback_url]
    dead_with_wayback = [c.url for c in citations if not c.live and c.wayback_url]
    low_conf = [c.span for c in citations if c.nli_verdict == "not_mentioned"]
    contested = [c.span for c in citations if c.nli_verdict == "contradicts"]

    report = VerificationReport(
        total_citations=len(citations),
        verified_count=len([c for c in citations if c.nli_verdict == "entails"]),
        hallucinated_urls=hallucinated,
        dead_urls=[c.url for c in citations if not c.live],
        wayback_substituted=dead_with_wayback,
        low_confidence_claims=low_conf,
        contested_claims=contested,
    )

    # Write verified findings to VFS
    verified_content = _build_verified_findings(vfs, citations, report)
    vfs.write("/verified_findings.md", verified_content)

    return citations, report


def _build_verified_findings(
    vfs: VirtualFS,
    citations: list[Citation],
    report: VerificationReport,
) -> str:
    """Compile all findings into a single verified document."""
    parts: list[str] = ["# Verified Research Findings\n"]

    # Include all raw findings
    for path, content in vfs.files.items():
        if path.startswith("/findings_") or path.startswith("/finding_"):
            parts.append(f"\n---\n## From: {path}\n\n{content}")

    # Add verification annotations
    parts.append("\n---\n## Verification Summary\n")
    parts.append(f"- Total citations: {report.total_citations}")
    parts.append(f"- Verified (entails): {report.verified_count}")
    parts.append(f"- Dead URLs: {len(report.dead_urls)}")
    parts.append(f"- Wayback substituted: {len(report.wayback_substituted)}")
    parts.append(f"- Low confidence claims: {len(report.low_confidence_claims)}")
    parts.append(f"- Contested claims: {len(report.contested_claims)}")

    if report.hallucinated_urls:
        parts.append("\n### Hallucinated URLs (omit from report)")
        for url in report.hallucinated_urls:
            parts.append(f"- {url}")

    if report.wayback_substituted:
        parts.append("\n### Wayback substitutions")
        for c in citations:
            if c.wayback_url:
                parts.append(f"- {c.url} → {c.wayback_url}")

    # Deduplicated source list — drop dead-without-Wayback, not_mentioned
    # (page didn't support the claim), and contradicts (page literally
    # disagreed). Verdict tags are not surfaced inline; they leak into the
    # synthesized report as visual noise.
    parts.append("\n## Sources (deduplicated)")
    for c in citations:
        if not (c.live or c.wayback_url):
            continue
        if c.nli_verdict in ("not_mentioned", "contradicts"):
            continue
        display_url = c.wayback_url if not c.live else c.url
        parts.append(f"[{c.index}] {display_url}")

    return "\n".join(parts)
