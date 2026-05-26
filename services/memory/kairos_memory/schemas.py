"""Pydantic schemas for the memory HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BrainSummary(BaseModel):
    id: str
    title: str
    page_count: int
    has_hot: bool


class WikiLink(BaseModel):
    target: str
    alias: str | None = None


class Page(BaseModel):
    path: str
    title: str
    frontmatter: dict = Field(default_factory=dict)
    body: str
    wikilinks: list[WikiLink] = Field(default_factory=list)


class SearchHit(BaseModel):
    path: str
    title: str
    snippet: str
    score: float
    brain: str | None = None


class GraphNode(BaseModel):
    id: str
    title: str
    layer: str  # "raw" | "wiki" | "index" | "hot"


class GraphEdge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class AppendHotRequest(BaseModel):
    text: str
    section: str | None = None  # appends under a markdown ## section if provided


class ReplaceHotRequest(BaseModel):
    full_text: str
    rationale: str | None = None


class NoteRequest(BaseModel):
    path: str  # e.g. "concepts/agency.md"
    title: str
    body: str
    frontmatter: dict = Field(default_factory=dict)


class IngestRawRequest(BaseModel):
    filename: str  # written under raw/
    content: str
    source_url: str | None = None


# --- Wiki maintenance: ingest / lint / solve --------------------------------


class WikiEditOp(BaseModel):
    """A single proposed change to the vault. Diffable in the UI."""

    kind: str  # "create" | "update"
    path: str
    title: str | None = None
    before: str | None = None  # full text of the existing page (None for create)
    after: str  # full text after the edit


class IngestPlan(BaseModel):
    """A proposed set of vault edits, awaiting approval."""

    plan_id: str
    brain: str
    kind: str  # "ingest" | "solve"
    summary: str
    ops: list[WikiEditOp] = Field(default_factory=list)
    # Whole-file replacements for the special files. Empty string means "no change".
    hot_before: str = ""
    hot_after: str = ""
    index_before: str = ""
    index_after: str = ""
    overview_before: str = ""
    overview_after: str = ""
    log_entry: str = ""
    raw_path: str | None = None  # if ingest dropped a file under raw/
    created_at: str  # ISO8601
    expires_at: str  # ISO8601


class IngestPlanRequest(BaseModel):
    title: str
    content: str


class ApplyPlanRequest(BaseModel):
    plan_id: str


class ApplyResult(BaseModel):
    ok: bool
    plan_id: str
    pages_touched: list[str] = Field(default_factory=list)
    summary: str = ""


class LintIssue(BaseModel):
    type: str  # contradiction|stale|orphan|missing_page|sparse|missing_xref|index_drift|data_gap
    severity: str  # high|medium|low
    description: str
    page: str = ""
    suggestion: str = ""


class LintReport(BaseModel):
    issues: list[LintIssue] = Field(default_factory=list)
    summary: str = ""
    stats: dict = Field(default_factory=dict)
