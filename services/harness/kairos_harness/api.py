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
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from kairos_runtime.research.tool import reset_research_budget
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
from .voice import warm_cue_cache, warm_genai_client

log = logging.getLogger(__name__)

app = FastAPI(title="Kairos Harness", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)


@app.on_event("startup")
async def _warmup() -> None:
    """Warm up expensive lazily-initialised resources so the first voice
    turn doesn't eat their setup cost on the hot path.

    - `warm_genai_client()` builds the shared `genai.Client` once.
    - `warm_cue_cache()` pre-renders TTS for tool cues + common openers
      so `TTSPipeline.speak_now(...)` returns instantly when the agent
      emits a verbal connector before a long-running tool.
    """
    warm_genai_client()
    asyncio.create_task(warm_cue_cache())
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
    Kairos system prompt (typed chat keeps `voice=False`).
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


def run() -> None:
    import uvicorn

    uvicorn.run("kairos_harness.api:app", host="127.0.0.1", port=8002, reload=False)


if __name__ == "__main__":
    run()
