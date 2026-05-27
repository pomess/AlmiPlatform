"""Query classifier and research brief writer.

Uses Flash-Lite structured output to classify the query and determine
effort tier, domain, and whether clarification is needed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from disease360_runtime.config import require

from .config import get_model
from .state import Classification, Domain, QueryType, ResearchBrief
from .usage import attach as _attach_usage

log = logging.getLogger(__name__)

CLASSIFIER_PROMPT = """\
You are a research query classifier. Analyze the user's query and output a JSON \
object with the following fields:

- query_type: one of "specific_fact", "comparison", "broad_survey", \
"trend_analysis", "technical_debug", "market_opportunity_scan", "academic_synthesis"
- domain: one of "ai_ml", "software_eng", "market", "scientific", "news", "general"
- depth_tier: one of "quick", "standard", "deep", "exhaustive"
- ambiguity_score: float 0.0 to 1.0 (how unclear/ambiguous the query is)
- suggested_clarifications: list of at most 3 strings (questions to ask if ambiguous)
- estimated_subagents: integer 1-10 (how many parallel researchers needed)
- estimated_tokens: integer estimate of total tokens the research will consume

Classification rules:
- specific_fact: single factual answer, 1 subagent, 3-10 tool calls
- comparison: comparing N items, 1 subagent per item (2-4), 10-15 calls each
- broad_survey: covering a wide topic, 6-10 subagents
- trend_analysis: tracking evolution over time, 4-6 subagents
- technical_debug: code/API troubleshooting, 1-2 subagents
- market_opportunity_scan: companies/funding/competitors, 5-8 subagents
- academic_synthesis: literature review, 4-8 subagents

Depth rules:
- quick: simple lookup, <5 searches needed
- standard: moderate depth, 5-15 searches
- deep: thorough coverage, 15-40 searches
- exhaustive: comprehensive, 40+ searches

Respond ONLY with the JSON object, no other text.\
"""


COMBINED_PROMPT = """\
You are a research query classifier and brief writer. Given a user query and \
today's date, produce a single JSON object with TWO top-level keys: \
``classification`` and ``brief``.

Today's date: {date}

The ``classification`` object contains:
- query_type: one of "specific_fact", "comparison", "broad_survey", \
"trend_analysis", "technical_debug", "market_opportunity_scan", "academic_synthesis"
- domain: one of "ai_ml", "software_eng", "market", "scientific", "news", "general"
- depth_tier: one of "quick", "standard", "deep", "exhaustive"
- ambiguity_score: float 0.0 to 1.0
- suggested_clarifications: list of at most 3 strings
- estimated_subagents: integer 1-10
- estimated_tokens: integer estimate

The ``brief`` object contains:
- title: concise title for this research task
- objective: 1-2 sentence description of what needs to be found
- scope: what is in-scope and what is explicitly out-of-scope
- constraints: list of constraints (time sensitivity, source preferences, etc.)
- output_format: "markdown" (always)

Classification rules:
- specific_fact: single factual answer, 1 subagent, 3-10 tool calls
- comparison: comparing N items, 1 subagent per item (2-4), 10-15 calls each
- broad_survey: covering a wide topic, 6-10 subagents
- trend_analysis: tracking evolution over time, 4-6 subagents
- technical_debug: code/API troubleshooting, 1-2 subagents
- market_opportunity_scan: companies/funding/competitors, 5-8 subagents
- academic_synthesis: literature review, 4-8 subagents

Depth rules:
- quick: simple lookup, <5 searches needed
- standard: moderate depth, 5-15 searches
- deep: thorough coverage, 15-40 searches
- exhaustive: comprehensive, 40+ searches

CRITICAL for the brief: The title and objective MUST use only terms the user \
explicitly stated. Do NOT expand the query with specific entity names (model \
names, product names, version numbers) from your training data — your knowledge \
is likely outdated. Use generic categorical terms instead. Let the search phase \
discover current specifics.

Respond ONLY with the JSON object, no other text.\
"""

BRIEF_PROMPT = """\
You are a research brief writer. Given a user query and its classification, \
produce a structured research brief that a team of researcher subagents can act on.

Query: {query}
Classification: {classification}
Date: {date}

Output a JSON object with:
- title: concise title for this research task
- objective: 1-2 sentence description of what needs to be found
- scope: what is in-scope and what is explicitly out-of-scope
- constraints: list of constraints (time sensitivity, source preferences, etc.)
- output_format: "markdown" (always)

Important: The title and objective MUST use only terms the user explicitly stated.
Do NOT expand the query with specific entity names (model names, product names,
version numbers) from your training data — your knowledge is likely outdated.
Use generic categorical terms instead. Let the search phase discover current specifics.

Respond ONLY with the JSON object, no other text.\
"""


async def classify_query(query: str, *, meter: Any = None) -> Classification:
    """Classify a research query using Flash-Lite structured output."""
    model_id = get_model("classifier")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    llm = _attach_usage(llm, meter, "classifier")

    resp = await llm.ainvoke(
        [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": query},
        ]
    )

    content = resp.content
    if isinstance(content, list):
        content = " ".join(str(p) for p in content)

    try:
        # Strip markdown code fences if present
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        return Classification(
            query_type=QueryType(data["query_type"]),
            domain=Domain(data["domain"]),
            depth_tier=data["depth_tier"],
            ambiguity_score=float(data.get("ambiguity_score", 0.2)),
            suggested_clarifications=data.get("suggested_clarifications", [])[:3],
            estimated_subagents=int(data.get("estimated_subagents", 3)),
            estimated_tokens=int(data.get("estimated_tokens", 100000)),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("Classifier parse failed, using defaults: %s", exc)
        return Classification(
            query_type=QueryType.BROAD_SURVEY,
            domain=Domain.GENERAL,
            depth_tier="standard",
            ambiguity_score=0.3,
            suggested_clarifications=[],
            estimated_subagents=3,
            estimated_tokens=200000,
        )


async def write_research_brief(
    query: str, classification: Classification, *, meter: Any = None
) -> ResearchBrief:
    """Generate a structured research brief from the query and classification."""
    model_id = get_model("classifier")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    llm = _attach_usage(llm, meter, "brief")

    prompt = BRIEF_PROMPT.format(
        query=query,
        classification=classification.model_dump_json(),
        date=datetime.now().strftime("%Y-%m-%d"),
    )

    resp = await llm.ainvoke(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]
    )

    content = resp.content
    if isinstance(content, list):
        content = " ".join(str(p) for p in content)

    try:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)

        # scope may come back as a dict (e.g. {"in_scope": [...], "out_of_scope": [...]})
        scope_raw = data.get("scope", "All relevant sources")
        if isinstance(scope_raw, dict):
            parts = []
            if scope_raw.get("in_scope"):
                parts.append("In scope: " + "; ".join(scope_raw["in_scope"]))
            if scope_raw.get("out_of_scope"):
                parts.append("Out of scope: " + "; ".join(scope_raw["out_of_scope"]))
            scope_raw = ". ".join(parts) if parts else "All relevant sources"

        # constraints may come back as strings or other types
        constraints_raw = data.get("constraints", [])
        if isinstance(constraints_raw, str):
            constraints_raw = [constraints_raw]
        elif not isinstance(constraints_raw, list):
            constraints_raw = []

        return ResearchBrief(
            title=data.get("title", query[:80]),
            objective=data.get("objective", query),
            scope=str(scope_raw),
            constraints=constraints_raw,
            output_format=data.get("output_format", "markdown"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("Brief writer parse failed, using defaults: %s", exc)
        return ResearchBrief(
            title=query[:80],
            objective=query,
            scope="All relevant sources",
            constraints=[],
            output_format="markdown",
        )


async def classify_and_brief(
    query: str, *, meter: Any = None
) -> tuple[Classification, ResearchBrief]:
    """Classify the query AND write its research brief in a single LLM call.

    Saves one cold-start round-trip vs calling ``classify_query`` then
    ``write_research_brief``. Falls back to per-stage defaults on parse error.
    """
    model_id = get_model("classifier")
    llm = ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=require("GOOGLE_API_KEY"),
        temperature=0.0,
    )
    llm = _attach_usage(llm, meter, "classify_and_brief")

    prompt = COMBINED_PROMPT.format(date=datetime.now().strftime("%Y-%m-%d"))

    resp = await llm.ainvoke(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ]
    )

    content = resp.content
    if isinstance(content, list):
        content = " ".join(str(p) for p in content)

    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    classification: Classification | None = None
    brief: ResearchBrief | None = None

    try:
        data = json.loads(text)
        c = data.get("classification") or {}
        classification = Classification(
            query_type=QueryType(c["query_type"]),
            domain=Domain(c["domain"]),
            depth_tier=c["depth_tier"],
            ambiguity_score=float(c.get("ambiguity_score", 0.2)),
            suggested_clarifications=c.get("suggested_clarifications", [])[:3],
            estimated_subagents=int(c.get("estimated_subagents", 3)),
            estimated_tokens=int(c.get("estimated_tokens", 100000)),
        )

        b = data.get("brief") or {}
        scope_raw = b.get("scope", "All relevant sources")
        if isinstance(scope_raw, dict):
            parts = []
            if scope_raw.get("in_scope"):
                parts.append("In scope: " + "; ".join(scope_raw["in_scope"]))
            if scope_raw.get("out_of_scope"):
                parts.append("Out of scope: " + "; ".join(scope_raw["out_of_scope"]))
            scope_raw = ". ".join(parts) if parts else "All relevant sources"

        constraints_raw = b.get("constraints", [])
        if isinstance(constraints_raw, str):
            constraints_raw = [constraints_raw]
        elif not isinstance(constraints_raw, list):
            constraints_raw = []

        brief = ResearchBrief(
            title=b.get("title", query[:80]),
            objective=b.get("objective", query),
            scope=str(scope_raw),
            constraints=constraints_raw,
            output_format=b.get("output_format", "markdown"),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning(
            "classify_and_brief parse failed, using defaults: %s", exc
        )

    if classification is None:
        classification = Classification(
            query_type=QueryType.BROAD_SURVEY,
            domain=Domain.GENERAL,
            depth_tier="standard",
            ambiguity_score=0.3,
            suggested_clarifications=[],
            estimated_subagents=3,
            estimated_tokens=200000,
        )
    if brief is None:
        brief = ResearchBrief(
            title=query[:80],
            objective=query,
            scope="All relevant sources",
            constraints=[],
            output_format="markdown",
        )

    return classification, brief
