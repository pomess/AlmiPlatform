"""Report synthesizer: reads verified findings and produces final markdown report.

Adaptive length per depth_tier, inline [n] citations, confidence tags,
anti-LLM-trope discipline.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from kairos_runtime.config import require

from .config import DepthTier, get_model
from .filesystem import VirtualFS
from .prompts import format_synthesizer_prompt
from .state import Citation, VerificationReport
from .usage import attach as _attach_usage

log = logging.getLogger(__name__)

# Recognises capitalised proper-noun-ish tokens that strongly suggest a
# specific claim (model names, products, hardware) — and bare numbers,
# percentages, version strings. Used by the citation gate to decide
# whether the report has too many specific claims for too few [n] markers.
_SPECIFIC_CLAIM = re.compile(
    r"\b("
    r"\d+(?:[.,]\d+)?(?:\s?(?:%|k|m|b|tps|tflops|tb|gb|fps|ms|s|x))?"  # numbers/units
    r"|v?\d+(?:\.\d+){1,3}"                                            # version strings
    r"|(?:GPT|Claude|Gemini|Llama|Mistral|DeepSeek|Qwen|Grok)[-\s]?[\w.\d]*"  # model names
    r")\b",
    re.IGNORECASE,
)
_CITATION_MARKER = re.compile(r"\[(\d+)\](?!\()")  # [n] but not markdown link [n](...)


def _flatten_content(content: Any) -> str:
    """Coerce a Gemini/LangChain message content into plain text.

    Gemini returns content as a list of blocks like
    ``[{"type": "text", "text": "...", "extras": {...signature...}}, ...]``.
    Joining the raw dicts with ``str(p)`` produces the dict repr — which is
    exactly the bug the previous synthesizer had. This pulls only the text
    block payloads.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


async def synthesize_report(
    vfs: VirtualFS,
    citations: list[Citation],
    verification: VerificationReport,
    *,
    depth_tier: DepthTier = "standard",
    budget_early_stop: bool = False,
    meter: Any = None,
) -> str:
    """Read verified findings and produce the final research report.

    Returns the complete markdown report with inline [n] citations.
    """
    model_id = get_model("synthesizer")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.1,
    )
    llm = _attach_usage(llm, meter, "synthesizer")

    # Read the key files from VFS
    verified = vfs.read("/verified_findings.md")
    brief = vfs.read("/brief.md")

    if not verified:
        # Fallback: concatenate all findings if verified isn't ready
        all_findings = []
        for path, content in vfs.files.items():
            if "finding" in path.lower():
                all_findings.append(content)
        verified = "\n\n---\n\n".join(all_findings) if all_findings else "No findings available."

    # Build source mapping for the synthesizer
    source_map = _build_source_map(citations)

    budget_note = ""
    if budget_early_stop:
        budget_note = (
            "**[BUDGET_EARLY_STOP]** Research was truncated at 80% of the token budget. "
            "Findings are based on partial coverage. Note this in the report metadata "
            "but do NOT apologize or hedge excessively in the report content."
        )

    system_prompt = format_synthesizer_prompt(depth_tier, budget_note=budget_note)

    user_content = (
        f"## Brief\n{brief}\n\n"
        f"## Verified Findings\n{verified}\n\n"
        f"## Source Map\n{source_map}\n\n"
        "Now produce the final report."
    )

    resp = await llm.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    )

    report = _flatten_content(resp.content).strip()

    # Citation gate: if the report has specific claims but no/few [n]
    # markers, retry once with the offending sentences quoted back. If the
    # second pass also fails, replace the whole thing with an explicit
    # "insufficient grounded data" notice rather than ship confabulation.
    has_sources = bool(citations) and any(
        c.live or c.wayback_url for c in citations
    )
    if has_sources:
        report = await _enforce_citations(
            llm,
            system_prompt,
            user_content,
            report,
            len(citations),
        )

    # Linkify inline [n] markers so the chat UI shows clickable footnotes.
    # The Sources section is left alone — its URLs are already explicit.
    report = _linkify_citations(report, citations)

    return report


def _evaluate_citations(report: str) -> tuple[int, int, list[str]]:
    """Return (citation_marker_count, specific_claim_sentence_count, offending_sentences)."""
    # Drop the Sources section from the analysis — citation markers there
    # don't count as inline claims, and the Sources lines are themselves
    # specific by design.
    body = re.split(r"^##\s*Sources\b", report, maxsplit=1, flags=re.MULTILINE)[0]
    citation_count = len(_CITATION_MARKER.findall(body))
    sentences = re.split(r"(?<=[.!?])\s+", body)
    offending: list[str] = []
    for s in sentences:
        s_stripped = s.strip()
        if len(s_stripped) < 20:
            continue
        if not _SPECIFIC_CLAIM.search(s_stripped):
            continue
        if _CITATION_MARKER.search(s_stripped):
            continue
        offending.append(s_stripped)
    specific_count = sum(1 for s in sentences if _SPECIFIC_CLAIM.search(s))
    return citation_count, specific_count, offending


async def _enforce_citations(
    llm: ChatGoogleGenerativeAI,
    system_prompt: str,
    original_user: str,
    report: str,
    source_count: int,
) -> str:
    citations_n, specific_n, offending = _evaluate_citations(report)
    log.info(
        "[synthesizer] citation gate: markers=%d specific=%d offending=%d",
        citations_n,
        specific_n,
        len(offending),
    )
    needs_retry = (
        (citations_n == 0 and specific_n > 0)
        or (specific_n > 0 and citations_n / max(1, specific_n) < 0.7)
    )
    if not needs_retry:
        return report

    quoted = "\n".join(f"- {s[:240]}" for s in offending[:8])
    correction = (
        "Your previous draft contained specific claims without [n] citations.\n"
        "Below are sentences from your draft that name numbers, models, products, "
        "or version strings but lack a [n] marker:\n\n"
        f"{quoted}\n\n"
        "Rewrite the report so that EVERY such claim is either:\n"
        "  (a) followed by a [n] marker that maps to the Source Map, OR\n"
        "  (b) removed entirely.\n"
        "Do NOT invent new citation numbers. Do NOT add specifics not in the findings.\n"
        "If you cannot ground a claim, drop it."
    )

    log.warning(
        "[synthesizer] retrying with citation correction (%d offending sentences)",
        len(offending),
    )
    resp = await llm.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": original_user},
            {"role": "assistant", "content": report},
            {"role": "user", "content": correction},
        ]
    )
    retried = _flatten_content(resp.content).strip()

    citations_n2, specific_n2, offending2 = _evaluate_citations(retried)
    log.info(
        "[synthesizer] citation gate post-retry: markers=%d specific=%d offending=%d",
        citations_n2,
        specific_n2,
        len(offending2),
    )
    still_failing = bool(offending2) or (
        specific_n2 > 0 and citations_n2 / max(1, specific_n2) < 0.7
    )
    if still_failing:
        log.warning(
            "[synthesizer] citation gate failed twice — emitting insufficient-data notice"
        )
        ungrounded = "\n".join(f"- {s[:240]}" for s in offending2[:10]) or "(none extracted)"
        return (
            "## Insufficient grounded data\n\n"
            f"The research pipeline returned {source_count} verified source(s), but the "
            "synthesizer could not produce a citation-grounded report. The model kept "
            "introducing specific claims (numbers, model names, version strings) that "
            "are not traceable to those sources.\n\n"
            "### Claims the model wanted to make but could not ground\n\n"
            f"{ungrounded}\n\n"
            "This usually means the subagents' findings did not capture the specific "
            "facts the question asks for, or the sources cited do not actually contain "
            "the claimed numbers. Try a narrower query, or rerun once more — transient "
            "grounding failures sometimes clear on retry."
        )
    return retried


def _linkify_citations(report: str, citations: list[Citation]) -> str:
    """Rewrite inline ``[n]`` markers into ``[\\[n\\]](url)`` markdown links.

    Only touches the body (everything before ``## Sources``); the Sources
    section already has explicit URLs. Skips ``[n]`` that is already part of
    a markdown link like ``[n](http...)``. Drops citations whose target URL
    is unusable (dead, no Wayback, or NLI not_mentioned).
    """
    if not citations:
        return report

    # Build n -> url map. Prefer the live URL; fall back to Wayback. Skip
    # citations the source map already filters out so we don't link to a
    # dead URL.
    url_for: dict[int, str] = {}
    for c in citations:
        if c.nli_verdict in ("not_mentioned", "contradicts"):
            continue
        if c.live:
            url_for[c.index] = c.url
        elif c.wayback_url:
            url_for[c.index] = c.wayback_url

    if not url_for:
        return report

    # Split off the Sources section so we don't rewrite its [n] entries.
    parts = re.split(r"(?m)^(##\s*Sources\b.*)$", report, maxsplit=1)
    body = parts[0]
    tail = "".join(parts[1:])

    def _replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        url = url_for.get(n)
        if not url:
            return match.group(0)
        # Plain "[n](url)" — no escaped brackets, no non-breaking space.
        # Escaped `\[`/`\]` get normalized to literal `[`/`]` by some
        # renderers, producing `[[1]]` text that triggers the [[wikilink]]
        # regex in apps/web/src/lib/markdown.tsx and paints the citation
        # yellow. The synthesizer pads the surrounding text on its own.
        return f"[{n}]({url})"

    body = _CITATION_MARKER.sub(_replace, body)
    return body + tail


def _build_source_map(citations: list[Citation]) -> str:
    """Build a numbered source map for the synthesizer to reference."""
    if not citations:
        return "No verified sources available."

    lines = ["Deduplicated source list (use these [n] references):"]
    for c in citations:
        if not c.live and not c.wayback_url:
            continue  # Skip completely dead URLs
        if c.nli_verdict == "not_mentioned":
            continue  # Skip pages that don't actually support the claim
        if c.nli_verdict == "contradicts":
            continue  # Skip sources whose page contradicts the claim
        url = c.wayback_url if not c.live else c.url
        lines.append(f"[{c.index}] {c.title or 'Untitled'} — {url}")

    return "\n".join(lines)
