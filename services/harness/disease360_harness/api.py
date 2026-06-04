"""FastAPI REST shim for the harness.

Endpoints:
    GET    /healthz
    GET    /news
    POST   /chat                     {message, brain?, thread_id?, profile?} -> {messages}
    POST   /chat/stream              SSE token stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Any

import httpx
from disease360_runtime.config import get as config_get
from disease360_runtime.research.tool import reset_research_budget
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import audit
from .agent import build_agent
from .news import get_briefing as get_news_briefing
from .news import warm_cache as warm_news_cache
from .system_prompt import DEFAULT_BRAIN
from .tools import base_tools_for_page, prompt_for_page, tools_for_page
from .tools.memory_tools import (
    DEFAULT_TENANT_ID,
    reset_turn_budget,
    set_active_tenant,
)
from .voice import router as voice_router

log = logging.getLogger(__name__)

app = FastAPI(title="Disease360 Harness", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)


@app.on_event("startup")
async def _warmup() -> None:
    """Warm up cheap, always-on resources at startup.

    Voice warming is intentionally NOT done here: the voice agent is
    opt-in, so `warm_genai_client()` + `warm_cue_cache()` only run when the
    cockpit hits `POST /voice/warm` (i.e. when the user flips Voice
    Activation on). An idle dashboard never spins up TTS or pre-renders
    cue phrases. Only the news cache — which is unrelated to voice — warms
    eagerly here.
    """
    asyncio.create_task(warm_news_cache())


class ChatRequest(BaseModel):
    message: str
    brain: str = DEFAULT_BRAIN
    tenant_id: str = DEFAULT_TENANT_ID
    thread_id: str | None = None
    profile: str = "chat"  # "chat" | "local" | "private"
    use_research: bool = False


class ChatResponse(BaseModel):
    thread_id: str
    final_text: str
    raw_messages: list[dict]


class VeraMessage(BaseModel):
    role: str
    content: str


class VeraRequest(BaseModel):
    messages: list[VeraMessage]
    tenant_id: str = DEFAULT_TENANT_ID
    thread_id: str | None = None


# Default Databricks serving endpoint for Vera (the genai-d360-assistant
# MLflow ResponsesAgent). Overridable via DATABRICKS_VERA_ENDPOINT.
DEFAULT_VERA_ENDPOINT = (
    "https://adb-3337810075168014.14.azuredatabricks.net"
    "/serving-endpoints/genai-d360-assistant/invocations"
)


_AGENTS: dict[tuple[str, str, str, bool], Any] = {}


def _agent_for(
    profile: str,
    brain: str,
    page: str | None = None,
    *,
    voice: bool = False,
):
    """Return (and cache) an agent specialized for a given surface.

    `page=None` is the default chat agent (no page-scoped tools).
    `page="dashboard"` adds the map's `fly_to_location` etc.
    `voice=True` layers the JARVIS delivery persona on top of the normal
    Disease360 system prompt (typed chat keeps `voice=False`).
    """
    key = (profile, brain, page or "", voice)
    if key not in _AGENTS:
        extra_tools = tools_for_page(page)
        base_tools = base_tools_for_page(page)
        page_prompt = prompt_for_page(page)
        # Compose layered system-prompt addendums: JARVIS first (voice
        # delivery cues), then the page's "skill" so it has the strongest
        # grip as the most specific layer.
        chunks: list[str] = []
        if voice:
            from .voice import JARVIS_STYLE

            chunks.append(JARVIS_STYLE)
        if page_prompt:
            chunks.append(page_prompt)
        extra_system = "\n\n".join(chunks) if chunks else None
        # Anchor each cached agent to its surface: dashboard for the
        # /voice + map page, chat for everything else.
        surface = "dashboard" if (page or "").strip().lower() == "dashboard" else "chat"
        _AGENTS[key] = build_agent(
            profile=profile,
            active_brain=brain,
            extra_tools=extra_tools or None,
            extra_system_prompt=extra_system,
            base_tools=base_tools,
            surface=surface,
        )
    return _AGENTS[key]


def _flatten_content(content: Any) -> str:
    """Coerce a LangChain message content (str | list[block]) into plain text."""
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
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "".join(parts)
    return str(content)


def _msg_dict(m: Any) -> dict:
    role = getattr(m, "type", None) or getattr(m, "role", "assistant")
    return {"role": role, "content": _flatten_content(getattr(m, "content", str(m)))}


def _final_text(messages: list[Any]) -> str:
    for m in reversed(messages):
        text = _flatten_content(getattr(m, "content", None))
        if text:
            return text
    return ""


def _audit_messages(
    thread_id: str, messages: list[Any], tenant_id: str = DEFAULT_TENANT_ID
) -> None:
    """Audit-log tool calls and tool results visible on a non-streaming reply."""
    seen_calls: set[str] = set()
    seen_results: set[str] = set()
    for m in messages:
        m_type = getattr(m, "type", None) or getattr(m, "role", None)
        if m_type in ("ai", "AIMessage", "AIMessageChunk"):
            for tc in getattr(m, "tool_calls", None) or []:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                tc_id = (
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                ) or name
                if not name or tc_id in seen_calls:
                    continue
                seen_calls.add(tc_id)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                audit.log_event(
                    "tool_call",
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    tool=name,
                    tool_call_id=tc_id,
                    args_redacted=audit.redact_args(args or {}),
                )
        elif m_type == "tool":
            tc_id = getattr(m, "tool_call_id", None) or getattr(m, "id", None)
            if tc_id and tc_id not in seen_results:
                seen_results.add(tc_id)
                audit.log_event(
                    "tool_result",
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    tool=getattr(m, "name", "") or "",
                    tool_call_id=tc_id,
                    result_summary=audit.summarize_result(getattr(m, "content", None)),
                )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "harness"}


@app.get("/news")
async def news(force: int = 0) -> dict:
    """Daily news briefing (world / tech / ai). Cached for 24h server-side."""
    return await get_news_briefing(force=bool(force))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    agent = _agent_for(req.profile, req.brain)
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 60,
    }
    user_content = req.message
    if req.use_research:
        user_content = (
            "[INSTRUCTION: You MUST use the deep_research tool to answer this query. "
            "Do NOT answer from memory — invoke deep_research immediately.]\n\n"
            + req.message
        )
    set_active_tenant(req.tenant_id)
    reset_turn_budget()
    reset_research_budget()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_content}]},
        config=config,
    )

    messages = result.get("messages", []) if isinstance(result, dict) else []
    _audit_messages(thread_id, messages, tenant_id=req.tenant_id)
    return ChatResponse(
        thread_id=thread_id,
        final_text=_final_text(messages),
        raw_messages=[_msg_dict(m) for m in messages],
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _tool_narration(name: str, args: dict) -> str:
    """Short spoken narration for each tool call, streamed to the UI immediately."""
    query = args.get("query", "") or args.get("q", "") or ""
    path = args.get("path", "") or ""
    brain = args.get("brain", "") or ""
    if name == "search_wiki":
        return f"Searching the database{f' for {query}' if query else ''}..."
    if name == "get_page":
        return f"Reading {path or 'a page'}..."
    if name == "deep_research":
        return f"Nothing found locally — researching online{f': {query}' if query else ''}..."
    if name == "fly_to_location":
        place = args.get("place", "") or ""
        return f"Locating {place}..." if place else "Flying to location..."
    return f"Running {name}..."


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events stream of model tokens.

    Emits:
        {"type":"meta","thread_id":...}             — once at the start
        {"type":"tool","name":"...","args":{...}}   — when the agent calls a tool
        {"type":"token","text":"..."}                — for each text chunk
        {"type":"done","thread_id":...}              — at completion
        {"type":"error","message":"..."}             — on failure
    """
    agent = _agent_for(req.profile, req.brain)
    thread_id = req.thread_id or str(uuid.uuid4())
    # Research queries are self-contained; use a fresh thread to avoid
    # the model copying a hallucinated query from prior conversation history.
    if req.use_research:
        thread_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 60,
    }
    set_active_tenant(req.tenant_id)
    reset_turn_budget()
    reset_research_budget()

    async def gen():
        seen_tool_calls: set[str] = set()
        seen_tool_results: set[str] = set()
        user_content = req.message
        if req.use_research:
            user_content = (
                "[INSTRUCTION: You MUST use the deep_research tool to answer this query. "
                "Do NOT answer from memory — invoke deep_research immediately.]\n\n"
                + req.message
            )
        try:
            yield _sse({"type": "meta", "thread_id": thread_id})
            print(f"[harness] astream start thread={thread_id} use_research={req.use_research}")
            async for mode, data in agent.astream(
                {"messages": [{"role": "user", "content": user_content}]},
                config=config,
                stream_mode=["messages", "custom"],
            ):
                if mode == "messages":
                    chunk, _meta = data
                    chunk_type = getattr(chunk, "type", None)

                    # Surface tool RESULTS so the UI can mark a running tool as
                    # finished. Tool messages have type="tool" and a
                    # `tool_call_id` matching the originating call.
                    if chunk_type == "tool":
                        tc_id = getattr(chunk, "tool_call_id", None) or getattr(
                            chunk, "id", None
                        )
                        if tc_id and tc_id not in seen_tool_results:
                            seen_tool_results.add(tc_id)
                            tool_name = getattr(chunk, "name", "") or ""
                            audit.log_event(
                                "tool_result",
                                thread_id=thread_id,
                                tenant_id=req.tenant_id,
                                tool=tool_name,
                                tool_call_id=tc_id,
                                result_summary=audit.summarize_result(
                                    getattr(chunk, "content", None)
                                ),
                            )
                            yield _sse(
                                {
                                    "type": "tool_done",
                                    "name": tool_name,
                                    "tool_call_id": tc_id,
                                }
                            )
                        continue

                    if chunk_type not in ("ai", "AIMessageChunk", "AIMessage"):
                        continue

                    # Surface tool calls as ephemeral status events so the UI
                    # can show "Searching brain…" while the agent thinks.
                    tool_calls = getattr(chunk, "tool_calls", None) or []
                    for tc in tool_calls:
                        name = (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None))
                        tc_id = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or name
                        if not name or tc_id in seen_tool_calls:
                            continue
                        seen_tool_calls.add(tc_id)
                        args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                        audit.log_event(
                            "tool_call",
                            thread_id=thread_id,
                            tenant_id=req.tenant_id,
                            tool=name,
                            tool_call_id=tc_id,
                            args_redacted=audit.redact_args(args or {}),
                        )
                        yield _sse(
                            {
                                "type": "tool",
                                "name": name,
                                "args": args or {},
                                "tool_call_id": tc_id,
                                "narration": _tool_narration(name, args or {}),
                            }
                        )

                    # Only stream TEXT tokens from the top-level agent node.
                    node = (_meta or {}).get("langgraph_node", "")
                    if node and node not in ("model", "agent"):
                        continue

                    text = _flatten_content(getattr(chunk, "content", None))
                    if text:
                        yield _sse({"type": "token", "text": text})
                elif mode == "custom":
                    if isinstance(data, dict) and "name" in data:
                        evt_name = data["name"]
                        payload = data.get("data", data)
                    elif isinstance(data, tuple) and len(data) == 2:
                        evt_name, payload = data
                    else:
                        evt_name, payload = "progress", data
                    if evt_name == "research_progress" and isinstance(payload, dict):
                        stage = payload.get("stage", "")
                        message = payload.get("message", "")
                        detail = payload.get("detail") or {}
                        yield _sse({
                            "type": "tool_progress",
                            "name": "deep_research",
                            "message": message,
                            "stage": stage,
                            "detail": detail if isinstance(detail, dict) else {},
                        })
            print(f"[harness] astream end thread={thread_id}")
            yield _sse({"type": "done", "thread_id": thread_id})
        except Exception as e:
            import traceback as _tb

            print(f"[harness] astream raised {type(e).__name__}: {e}")
            print(_tb.format_exc())
            from langgraph.errors import GraphRecursionError

            if isinstance(e, GraphRecursionError):
                yield _sse(
                    {
                        "type": "token",
                        "text": (
                            "\n\n_(Search budget reached — answering with what I have. "
                            "If this isn't enough, ask a more specific question.)_"
                        ),
                    }
                )
                yield _sse({"type": "done", "thread_id": thread_id})
            else:
                yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _extract_vera_text(data: Any) -> str:
    """Normalize a Databricks / MLflow ResponsesAgent reply to plain text.

    Databricks-served agents return a few different shapes depending on the
    underlying interface (OpenAI Responses, chat completions, or a raw MLflow
    predictions envelope). We probe the common ones in order and fall back to a
    string dump so the UI always gets *something* rather than a blank turn.
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    if isinstance(data, dict):
        # OpenAI Responses convenience field.
        direct = data.get("output_text")
        if isinstance(direct, str) and direct:
            return direct

        # OpenAI Responses: output is a list of items, assistant message items
        # carry a `content` list of {type: output_text|text, text: ...} blocks.
        output = data.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
                        elif isinstance(block, str):
                            parts.append(block)
            if parts:
                return "".join(parts)

        # Chat-completions shape.
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message") or {}
                if isinstance(msg, dict):
                    return _flatten_content(msg.get("content"))
                if isinstance(first.get("text"), str):
                    return first["text"]

        # messages[-1] envelope.
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                return _flatten_content(last.get("content"))

        # Raw MLflow predictions.
        preds = data.get("predictions")
        if isinstance(preds, list) and preds:
            head = preds[0]
            if isinstance(head, str):
                return head
            return _flatten_content(head)
        if isinstance(preds, str):
            return preds

    if isinstance(data, list):
        parts = [p for p in (_extract_vera_text(x) for x in data) if p]
        if parts:
            return "".join(parts)

    return str(data)


@app.post("/vera/stream")
async def vera_stream(req: VeraRequest):
    """Proxy a turn to the Databricks-served Vera agent.

    The browser sends the visible conversation history; we forward it to the
    Databricks serving endpoint with a server-side PAT (never exposed to the
    client) and re-emit the reply over the same SSE envelope the Chat tab uses
    (`meta` / `token` / `done` / `error`).
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    endpoint = config_get("DATABRICKS_VERA_ENDPOINT") or DEFAULT_VERA_ENDPOINT
    token = config_get("DATABRICKS_VERA_TOKEN") or config_get("DATABRICKS_TOKEN")

    async def gen():
        yield _sse({"type": "meta", "thread_id": thread_id})
        if not token:
            yield _sse(
                {
                    "type": "error",
                    "message": (
                        "Vera is not configured: set DATABRICKS_VERA_TOKEN (or "
                        "DATABRICKS_TOKEN) in policies/secrets.env."
                    ),
                }
            )
            return

        payload = {
            "input": [{"role": m.role, "content": m.content} for m in req.messages],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
            text = _extract_vera_text(data)
            if text:
                yield _sse({"type": "token", "text": text})
            yield _sse({"type": "done", "thread_id": thread_id})
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response is not None else ""
            yield _sse(
                {
                    "type": "error",
                    "message": f"Databricks returned {e.response.status_code}: {body}",
                }
            )
        except Exception as e:  # pragma: no cover - network/runtime failures
            yield _sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class CompetitorUpdateRequest(BaseModel):
    company: str


@app.post("/competitor-update")
async def competitor_update(req: CompetitorUpdateRequest):
    """Lightweight competitor intel update using deep research + BioMCP.

    Fires a quick research pass and returns structured update entries.
    Does NOT persist — the frontend merges into its in-memory state.
    """
    now = asyncio.get_event_loop().time()
    entries: list[dict[str, Any]] = []

    # BioMCP trial search (non-blocking, best-effort)
    try:
        from biomcp.individual_tools import trial_searcher

        result = await trial_searcher(
            query=f"{req.company} dermatology", status="RECRUITING"
        )
        text = result if isinstance(result, str) else str(result)
        if "NCT" in text:
            entries.append({
                "type": "trial_update",
                "title": f"Active trials for {req.company}",
                "detail": text[:500],
            })
    except Exception as e:
        log.debug("BioMCP trial search failed for %s: %s", req.company, e)

    # Quick deep research (standard depth, narrow query)
    try:
        from disease360_runtime.research.runner import run_research

        query = (
            f"Latest {req.company} pharma news pipeline updates 2026 "
            f"dermatology immunology in the last 30 days"
        )
        report = await asyncio.wait_for(
            run_research(query=query, depth="standard"),
            timeout=60.0,
        )
        markdown = getattr(report, "markdown", report) if report else ""
        if markdown and len(str(markdown)) > 100:
            lines = [l.strip() for l in str(markdown).split("\n")
                     if l.strip() and not l.startswith("#")]
            summary = " ".join(lines[:3])[:400]
            entries.append({
                "type": "news",
                "title": f"Research update for {req.company}",
                "detail": summary,
            })
    except asyncio.TimeoutError:
        log.warning("Deep research timed out for %s", req.company)
    except Exception as e:
        log.debug("Deep research failed for %s: %s", req.company, e)

    from datetime import datetime as dt, timezone

    return {
        "timestamp": dt.now(tz=timezone.utc).isoformat(),
        "source": "deep_research+biomcp",
        "entries": entries,
    }


def _configure_logging() -> None:
    """Route INFO logs from our packages to stdout so the harness console
    shows what the agent + deep-research pipeline are doing in real time.

    Without this, Python's last-resort handler only surfaces WARNING+ — which
    is why deep-research progress (`[research] ...`) was invisible while errors
    leaked through. Level is overridable via DISEASE360_LOG_LEVEL.
    """
    level_name = os.environ.get("DISEASE360_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")
    )

    for name in ("disease360_harness", "disease360_runtime", "disease360_memory"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        # Guard against duplicate handlers if run() is re-entered (e.g. reload).
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            logger.addHandler(handler)
        # Our handler already prints to stdout; don't double-log via root/uvicorn.
        logger.propagate = False


def run() -> None:
    import uvicorn

    _configure_logging()
    uvicorn.run("disease360_harness.api:app", host="127.0.0.1", port=8002, reload=False)


if __name__ == "__main__":
    run()
