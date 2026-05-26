"""FastAPI REST shim for the harness.

Endpoints:
    GET    /healthz
    POST   /chat                     {message, brain?, thread_id?, profile?} -> {messages, interrupts, approvals}
    GET    /approvals                ?status=pending  -> list
    POST   /approvals/{id}/approve   -> resumes the paused agent thread
    POST   /approvals/{id}/deny      -> rejects + resumes with feedback
    POST   /approvals/drain-dnd      -> moves dnd_held -> pending
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class _SuppressApprovalsPolling(logging.Filter):
    """Silence successful GET /approvals access-log lines.

    The web cockpit polls this endpoint every 3s while open, which drowns
    out interesting traces (research progress, tool calls). Other status
    codes and other endpoints still log normally.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/approvals" not in msg:
            return True
        # Only suppress 2xx GETs; keep errors/4xx/5xx visible.
        return not ('"GET /approvals' in msg and " 200 " in msg)


logging.getLogger("uvicorn.access").addFilter(_SuppressApprovalsPolling())

from kairos_runtime.config import get as config_get

from . import approval_store, audit
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
from kairos_runtime.research.tool import reset_research_budget
from .voice import router as voice_router
from .voice import warm_cue_cache, warm_genai_client

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
    interrupted: bool
    approvals: list[dict]
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
        # /voice + map page, chat for everything else. This drives the
        # `# SURFACE` block in the assembled system prompt, which stops
        # the chat agent from mirroring leftover dashboard-style replies
        # in a thread that spans both surfaces.
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
    """Coerce a LangChain message content (str | list[block]) into plain text.

    Gemini (and other providers) return content as a list of blocks like
    `[{"type": "text", "text": "...", "extras": {...}}, ...]`. We join the
    text blocks and ignore non-text parts (tool calls, signatures, etc).
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
    """Audit-log tool calls and tool results visible on a non-streaming reply.

    The SSE path logs from per-chunk events; the sync ``/chat`` path only
    sees the final message list, so we walk it here. Idempotency across
    paths is provided by ``tool_call_id`` — replaying the same id just
    appends another row, which is fine for an append-only log.
    """
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


def _persist_interrupts(
    thread_id: str, result: dict, tenant_id: str = DEFAULT_TENANT_ID
) -> list[dict]:
    """Inspect a langgraph result for `__interrupt__` and persist approval rows."""
    persisted: list[dict] = []
    interrupts = result.get("__interrupt__") or []
    if not isinstance(interrupts, (list, tuple)):
        interrupts = [interrupts]
    # LangChain 1.x HumanInTheLoopMiddleware emits:
    #   interrupt(HITLRequest{"action_requests": [ActionRequest{name, args, description}], ...})
    # Older HITL shapes used a bare list of action dicts. Normalize both into
    # a flat list of ActionRequest-like dicts.
    flat: list[dict] = []
    for it in interrupts:
        value = getattr(it, "value", it)
        if isinstance(value, dict) and "action_requests" in value:
            reqs = value.get("action_requests") or []
            flat.extend(r for r in reqs if isinstance(r, dict))
        elif isinstance(value, list):
            flat.extend(r for r in value if isinstance(r, dict))
        elif isinstance(value, dict):
            flat.append(value)
    for action in flat:
        tool = action.get("name") or action.get("tool") or action.get("action") or "unknown"
        args = action.get("args") or {}
        rationale = action.get("description") or action.get("rationale")
        args_payload = args if isinstance(args, dict) else {"_": args}
        # Enrich apply_* approvals with the full plan from the memory service
        # so the UI can render the diff without a second fetch.
        if tool in ("apply_ingest", "apply_solve"):
            plan = _fetch_plan(
                tenant_id, args_payload.get("brain"), args_payload.get("plan_id")
            )
            if plan is not None:
                args_payload = {**args_payload, "plan": plan}
        row = approval_store.create(
            thread_id=thread_id,
            tenant_id=tenant_id,
            tool=tool,
            args=args_payload,
            rationale=rationale,
        )
        persisted.append(row.to_dict())
    return persisted


def _fetch_plan(tenant_id: Any, brain: Any, plan_id: Any) -> dict | None:
    """Fetch an ingest/solve plan from the memory service for approval display."""
    if not brain or not plan_id:
        return None
    tenant = tenant_id or DEFAULT_TENANT_ID
    base = (
        config_get("KAIROS_MEMORY_URL", "http://127.0.0.1:8001")
        or "http://127.0.0.1:8001"
    )
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{base}/tenant/{tenant}/brain/{brain}/plan/{plan_id}")
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None


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
    approvals = _persist_interrupts(
        thread_id,
        result if isinstance(result, dict) else {},
        tenant_id=req.tenant_id,
    )
    return ChatResponse(
        thread_id=thread_id,
        final_text=_final_text(messages),
        interrupted=bool(approvals),
        approvals=approvals,
        raw_messages=[_msg_dict(m) for m in messages],
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events stream of model tokens.

    Emits:
        {"type":"meta","thread_id":...}             â€” once at the start
        {"type":"tool","name":"...","args":{...}}   â€” when the agent calls a tool
        {"type":"token","text":"..."}                â€” for each text chunk
        {"type":"done","interrupted":bool,
                       "approvals":[...],
                       "thread_id":...}              â€” at completion
        {"type":"error","message":"..."}             â€” on failure
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
        interrupted = False
        persisted: list[dict] = []
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
                stream_mode=["messages", "updates", "custom"],
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
                    # Nested tool calls (e.g. deep_research internal LLMs)
                    # produce chunks from other nodes — skip them.
                    # langchain.agents.factory names the LLM node "model";
                    # older / custom graphs may use "agent".
                    node = (_meta or {}).get("langgraph_node", "")
                    if node and node not in ("model", "agent"):
                        continue

                    text = _flatten_content(getattr(chunk, "content", None))
                    if text:
                        yield _sse({"type": "token", "text": text})
                elif mode == "updates":
                    if isinstance(data, dict) and "__interrupt__" in data:
                        interrupted = True
                        persisted.extend(
                            _persist_interrupts(thread_id, data, tenant_id=req.tenant_id)
                        )
                elif mode == "custom":
                    print(f"[harness] custom event: type={type(data).__name__} data={data!r:.300}")
                    if isinstance(data, dict) and "name" in data:
                        evt_name = data["name"]
                        payload = data.get("data", data)
                    elif isinstance(data, tuple) and len(data) == 2:
                        evt_name, payload = data
                    else:
                        evt_name, payload = "progress", data
                    print(f"[harness] custom event parsed name={evt_name!r} payload_type={type(payload).__name__}")
                    if evt_name == "research_progress" and isinstance(payload, dict):
                        stage = payload.get("stage", "")
                        message = payload.get("message", "")
                        detail = payload.get("detail") or {}
                        print(f"[harness] forwarded research_progress stage={stage!r} message={message!r} detail_keys={list(detail.keys()) if isinstance(detail, dict) else type(detail).__name__}")
                        yield _sse({
                            "type": "tool_progress",
                            "name": "deep_research",
                            "message": message,
                            "stage": stage,
                            "detail": detail if isinstance(detail, dict) else {},
                        })
            print(f"[harness] astream end thread={thread_id} interrupted={interrupted}")
            yield _sse(
                {
                    "type": "done",
                    "thread_id": thread_id,
                    "interrupted": interrupted,
                    "approvals": persisted,
                }
            )
        except Exception as e:  # noqa: BLE001
            import traceback as _tb

            print(f"[harness] astream raised {type(e).__name__}: {e}")
            print(_tb.format_exc())
            from langgraph.errors import GraphRecursionError

            if isinstance(e, GraphRecursionError):
                yield _sse(
                    {
                        "type": "token",
                        "text": (
                            "\n\n_(Search budget reached â€” answering with what I have. "
                            "If this isn't enough, ask a more specific question or capture the "
                            "missing fact into the brain.)_"
                        ),
                    }
                )
                yield _sse(
                    {
                        "type": "done",
                        "thread_id": thread_id,
                        "interrupted": False,
                        "approvals": [],
                    }
                )
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


@app.get("/approvals")
def list_approvals(status: str | None = None) -> list[dict]:
    return [a.to_dict() for a in approval_store.list_(status)]


async def _resume_thread(thread_id: str, decisions: list[dict]) -> dict:
    """Resume a paused agent thread with the given decisions."""
    from langgraph.types import Command

    reset_turn_budget()
    reset_research_budget()
    # We don't know which (profile, brain) pair owns this thread; try them all.
    last_result: dict = {}
    for agent in _AGENTS.values():
        try:
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 60,
            }
            result = await agent.ainvoke(Command(resume={"decisions": decisions}), config=config)
            if isinstance(result, dict):
                last_result = result
                if result.get("messages"):
                    break
        except Exception:
            continue
    return last_result


class ApproveRequest(BaseModel):
    by: str = "web"
    edited_args: dict | None = None


class DenyRequest(BaseModel):
    by: str = "web"
    feedback: str | None = None


@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, req: ApproveRequest) -> dict:
    item = approval_store.get_by_id(approval_id)
    if not item:
        raise HTTPException(404, "approval not found")
    if item.status not in (approval_store.PENDING, approval_store.DND_HELD):
        raise HTTPException(409, f"approval already {item.status}")
    updated = approval_store.resolve(approval_id, decision=approval_store.APPROVED, by=req.by)
    decision: dict = {"type": "approve"}
    if req.edited_args:
        decision = {
            "type": "edit",
            "edited_action": {"name": item.tool, "args": req.edited_args},
        }
    set_active_tenant(item.tenant_id)
    result = await _resume_thread(item.thread_id, [decision])
    if result:
        _audit_messages(item.thread_id, result.get("messages", []), tenant_id=item.tenant_id)
    new_approvals = _persist_interrupts(item.thread_id, result, tenant_id=item.tenant_id)
    return {
        "approval": updated.to_dict() if updated else None,
        "new_approvals": new_approvals,
        "final_text": _final_text(result.get("messages", [])) if result else "",
    }


@app.post("/approvals/{approval_id}/deny")
async def deny(approval_id: str, req: DenyRequest) -> dict:
    item = approval_store.get_by_id(approval_id)
    if not item:
        raise HTTPException(404, "approval not found")
    if item.status not in (approval_store.PENDING, approval_store.DND_HELD):
        raise HTTPException(409, f"approval already {item.status}")
    updated = approval_store.resolve(approval_id, decision=approval_store.DENIED, by=req.by)
    decision = {
        "type": "reject",
        "feedback": req.feedback or "Denied by user.",
    }
    set_active_tenant(item.tenant_id)
    result = await _resume_thread(item.thread_id, [decision])
    if result:
        _audit_messages(item.thread_id, result.get("messages", []), tenant_id=item.tenant_id)
    new_approvals = _persist_interrupts(item.thread_id, result, tenant_id=item.tenant_id)
    return {
        "approval": updated.to_dict() if updated else None,
        "new_approvals": new_approvals,
        "final_text": _final_text(result.get("messages", [])) if result else "",
    }


@app.post("/approvals/drain-dnd")
def drain_dnd() -> dict:
    return {"drained": approval_store.drain_dnd()}


def run() -> None:
    import uvicorn

    uvicorn.run("kairos_harness.api:app", host="127.0.0.1", port=8002, reload=False)


if __name__ == "__main__":
    run()
