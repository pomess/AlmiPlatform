"""Client-executed tool bridge.

Some agent tools — like the dashboard's `fly_to_location` — execute in the
browser, not in Python. The agent still calls them as if they were normal
LangChain tools; the tool body publishes a `tool_call` event onto a per-turn
queue and awaits a `Future` that the HTTP `tool_result` endpoint resolves
when the browser sends back its execution result.

The active per-turn bridge is exposed through a `ContextVar` so async tool
implementations don't need to be rebuilt per turn — they just read the
bridge from the context the SSE handler set up.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextvars import ContextVar
from typing import Any

log = logging.getLogger(__name__)


class ClientToolBridge:
    """Per-turn round-trip channel between the agent and the browser.

    `events` is the queue the SSE generator drains and forwards to the
    client. `pending` maps `call_id` -> Future that the HTTP result endpoint
    resolves when the browser POSTs back.
    """

    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._closed = False

    async def call(
        self,
        name: str,
        args: dict[str, Any],
        *,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Send a tool_call to the client, await its result, return it.

        Times out cleanly so a misbehaving client can't hang the agent
        forever. The returned dict is the raw JSON the client posted back.
        """
        if self._closed:
            return {"ok": False, "error": "bridge closed"}
        call_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[call_id] = fut
        await self.events.put(
            {"type": "tool_call", "id": call_id, "name": name, "args": args},
        )
        try:
            return await asyncio.wait_for(fut, timeout)
        except TimeoutError:
            return {"ok": False, "error": f"client timeout after {timeout:.0f}s"}
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, call_id: str, result: dict[str, Any]) -> bool:
        fut = self._pending.get(call_id)
        if fut is None or fut.done():
            return False
        fut.set_result(result)
        return True

    async def close(self) -> None:
        self._closed = True
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result({"ok": False, "error": "turn ended"})
        self._pending.clear()


# ---------------------------------------------------------------------------
# Active bridge (per asyncio task) so async tools can find it without being
# rebuilt every turn.
# ---------------------------------------------------------------------------

_active_bridge: ContextVar[ClientToolBridge | None] = ContextVar(
    "disease360_client_tool_bridge", default=None,
)


def set_active_bridge(bridge: ClientToolBridge | None):
    """Bind a bridge to the current async context. Returns the reset token."""
    return _active_bridge.set(bridge)


def reset_active_bridge(token: Any) -> None:
    _active_bridge.reset(token)


def get_active_bridge() -> ClientToolBridge | None:
    return _active_bridge.get()


# ---------------------------------------------------------------------------
# Per-turn registry — used by the HTTP `tool_result` endpoint to find the
# bridge created by the corresponding `/voice/turn` SSE generator.
# ---------------------------------------------------------------------------

_TURN_BRIDGES: dict[str, ClientToolBridge] = {}


def register_turn(turn_id: str, bridge: ClientToolBridge) -> None:
    _TURN_BRIDGES[turn_id] = bridge


def unregister_turn(turn_id: str) -> None:
    _TURN_BRIDGES.pop(turn_id, None)


def get_turn_bridge(turn_id: str) -> ClientToolBridge | None:
    return _TURN_BRIDGES.get(turn_id)
