"""Daily quota for Google grounded search.

Google's free tier covers ~5000 grounded-search requests per day. We cut off
at 4000 by default to leave a safety margin and fall back to DuckDuckGo for
the remainder of the day. State is persisted to a small JSON file so the
counter survives process restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from atlas_runtime.config import get, repo_root

log = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 4000

_lock = asyncio.Lock()


def _state_path() -> Path:
    p = repo_root() / "services" / "harness" / "data" / "grounding_quota.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _daily_limit() -> int:
    raw = get("DISEASE360_RESEARCH_GOOGLE_DAILY_LIMIT")
    if not raw:
        return DEFAULT_DAILY_LIMIT
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_DAILY_LIMIT


def _read() -> dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"date": "", "google_calls": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"date": "", "google_calls": 0}
        return data
    except Exception:
        return {"date": "", "google_calls": 0}


def _write(data: dict[str, Any]) -> None:
    try:
        _state_path().write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        log.exception("failed to persist grounding quota state")


async def acquire_google_slot() -> tuple[bool, int, int]:
    """Reserve a Google grounded-search slot for today.

    Returns ``(ok, used, limit)``. When ``ok`` is False the caller should
    fall back to DuckDuckGo — the daily Google budget is exhausted.
    """
    today = date.today().isoformat()
    limit = _daily_limit()
    async with _lock:
        data = _read()
        if data.get("date") != today:
            data = {"date": today, "google_calls": 0}
        used = int(data.get("google_calls", 0) or 0)
        if used >= limit:
            return False, used, limit
        data["date"] = today
        data["google_calls"] = used + 1
        _write(data)
        return True, data["google_calls"], limit


def peek_quota() -> tuple[int, int]:
    """Return ``(used_today, limit)`` without reserving a slot."""
    today = date.today().isoformat()
    data = _read()
    used = int(data.get("google_calls", 0) or 0) if data.get("date") == today else 0
    return used, _daily_limit()
