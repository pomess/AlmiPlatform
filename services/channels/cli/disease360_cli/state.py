"""Per-session state on disk: active brain etc. ~/.disease360/state.json."""

from __future__ import annotations

import json
from pathlib import Path

STATE_PATH = Path.home() / ".disease360" / "state.json"
LEGACY_PATH = Path.home() / ".jarvis" / "state.json"
DEFAULT = {"active_brain": "Bruno's Brain", "tenant_id": "local", "thread_id": None}


def load() -> dict:
    # One-time migration from the pre-rename home (.jarvis → .disease360).
    if not STATE_PATH.is_file() and LEGACY_PATH.is_file():
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(LEGACY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    if not STATE_PATH.is_file():
        return dict(DEFAULT)
    try:
        return {**DEFAULT, **json.loads(STATE_PATH.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULT)


def save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
