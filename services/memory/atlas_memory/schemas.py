"""Pydantic schemas for the Atlas Memory HTTP API."""

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
    layer: str  # node_type: company | drug | indication | mechanism | trial | kol | institution


class GraphEdge(BaseModel):
    source: str
    target: str


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
