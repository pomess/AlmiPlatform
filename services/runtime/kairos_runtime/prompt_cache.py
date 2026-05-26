"""Gemini context-cache helper for the agent system prompt.

Background
----------
Every voice / chat turn currently re-uploads the full ~8 KB system prompt
(SOUL + USER + WIKI POLICY + KNOWLEDGE LANDSCAPE + active brain hot.md +
index.md head) plus the JSON schemas for every bound tool. On Gemini
Flash this costs ~150-400 ms of TTFB on the first token even though the
exact same bytes are sent on every turn.

Two layers of caching exist on the Gemini side:

1. **Implicit caching** (automatic, no code needed). For Gemini 2.0/2.5
   models, the API automatically deduplicates repeated prompt prefixes
   over a short rolling window. Gives a measurable but variable TTFB
   reduction. The `cached_content_token_count` field in `usage_metadata`
   reports how much of the request was a cache hit -- our chat-model
   wrapper already plumbs that through. A non-zero value confirms the
   prefix is being recognised.

2. **Explicit caching** via `client.caches.create(...)` (this module).
   Guaranteed cache hit on the prefix you register, plus a 75% input-token
   billing discount. Trades roughly 100-300 ms off TTFB on Gemini Flash.

   The HARD constraint, per the LangChain wrapper docs, is that when
   `cached_content` is set on `ChatGoogleGenerativeAI`, you cannot also
   pass `system_instruction` or bound tools in the request -- they MUST
   be part of the cache. This is incompatible with the deepagents /
   `langchain.agents.create_agent` flow, which calls `.bind_tools()`
   internally. Wiring explicit caching cleanly therefore requires
   either (a) including all tool schemas in the cache and patching
   `create_agent` to skip its own bind, or (b) running tools-free
   chat-only agents.

   So this module is implemented as opt-in plumbing gated behind the
   `KAIROS_USE_CONTEXT_CACHE` config flag (default OFF). Enable only on
   chat-only / no-tools agents until the bind-tools coupling is unwound.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Iterable
from typing import Any

from . import config

log = logging.getLogger(__name__)


# --- public API ------------------------------------------------------------


def context_cache_enabled() -> bool:
    """Truthy iff `KAIROS_USE_CONTEXT_CACHE` is set to a truthy value."""
    raw = (config.get("KAIROS_USE_CONTEXT_CACHE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_or_create_cache(
    *,
    model: str,
    system_prompt: str,
    tool_signatures: Iterable[str] | None = None,
    ttl_seconds: int = 3600,
) -> str | None:
    """Return a Gemini `cachedContents/...` name for `(model, system_prompt)`.

    Returns ``None`` and logs a warning on any failure -- callers should
    treat ``None`` as "no cache available, send the prompt inline as
    usual." That keeps every caller crash-safe even if the Gemini caching
    API is unreachable, the prompt is below Gemini's minimum cache size
    (1024 tokens for 2.5 Flash, 4096 for 2.5 Pro), or the model rejects
    the request.

    Caches are reused across calls within this process and refreshed
    when their TTL has more than ``_TTL_REFRESH_SECONDS`` left. Tool
    signatures are folded into the cache key so a tools change forces a
    new cache.
    """
    if not context_cache_enabled():
        return None

    key = _cache_key(model, system_prompt, tool_signatures or [])
    now = time.time()
    with _LOCK:
        entry = _CACHES.get(key)
        if entry is not None and entry["expires_at"] - now > _TTL_REFRESH_SECONDS:
            return entry["name"]

    try:
        from google import genai
        from google.genai import types
    except Exception:
        log.warning("google-genai SDK missing; context cache disabled")
        return None

    api_key = config.require("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                ttl=f"{int(ttl_seconds)}s",
            ),
        )
    except Exception as exc:
        log.warning("context cache create failed for model=%s: %s", model, exc)
        return None

    name = getattr(cache, "name", None)
    if not name:
        log.warning("context cache returned no name; falling back to inline prompt")
        return None

    with _LOCK:
        _CACHES[key] = {"name": name, "expires_at": now + ttl_seconds}
    log.info("context cache created: %s (model=%s, ttl=%ss)", name, model, ttl_seconds)
    return name


def invalidate_all() -> None:
    """Forget every memoised cache name. Next caller will create a new one."""
    with _LOCK:
        _CACHES.clear()


# --- internals -------------------------------------------------------------

# Refresh the cache when this much TTL is left (so a long-running session
# doesn't suddenly miss the cache mid-conversation when it expires).
_TTL_REFRESH_SECONDS = 60

_CACHES: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _cache_key(model: str, system_prompt: str, tool_signatures: Iterable[str]) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(system_prompt.encode("utf-8"))
    for sig in tool_signatures:
        h.update(b"\x00")
        h.update(sig.encode("utf-8"))
    return h.hexdigest()
