"""Append-only JSONL audit log.

Every event the harness emits — tool calls and tool results — lands as
one line in ``logs/audit.jsonl``. The file is the compliance artifact.

Events share a flat schema:

    {"ts": "<iso8601 utc>", "kind": "<event_kind>", ...event-specific fields}

Event kinds emitted today:

    tool_call            agent invokes a tool
    tool_result          tool returns

Writes are guarded by a process-local lock. The file is opened, appended,
flushed, and closed per event — fine at expected event rates and avoids
holding a handle across long-lived async tasks.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kairos_runtime.config import get as config_get
from kairos_runtime.config import repo_root

_LOCK = threading.Lock()
_PATH: Path | None = None

_REDACT_KEY = re.compile(
    r"(api[_-]?key|secret|password|passwd|pwd|token|auth|credential|bearer)",
    re.IGNORECASE,
)
_RESULT_SUMMARY_MAX = 240


def _resolve_path() -> Path:
    """Return the audit log path, honoring ``KAIROS_AUDIT_PATH`` if set."""
    override = config_get("KAIROS_AUDIT_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "logs" / "audit.jsonl"


def _path() -> Path:
    global _PATH
    # Resolve lazily; tests use a per-test KAIROS_HOME and reset module state,
    # so we don't permanently cache across tests but do cache within a process.
    p = _resolve_path()
    if _PATH != p:
        _PATH = p
        _PATH.parent.mkdir(parents=True, exist_ok=True)
    return _PATH


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def redact_args(args: Any) -> Any:
    """Replace values for secret-shaped keys with ``"[REDACTED]"``.

    Recurses dicts and lists. Leaves primitives alone. Used for the
    ``args_redacted`` field on tool-call events so a raw API key
    sitting in a tool argument never lands in the audit log.
    """
    if isinstance(args, dict):
        return {
            k: ("[REDACTED]" if _REDACT_KEY.search(str(k)) else redact_args(v))
            for k, v in args.items()
        }
    if isinstance(args, list):
        return [redact_args(v) for v in args]
    return args


def summarize_result(content: Any) -> str:
    """Stringify and truncate a tool result for the audit log."""
    if content is None:
        return ""
    if not isinstance(content, str):
        try:
            content = json.dumps(content, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            content = str(content)
    if len(content) > _RESULT_SUMMARY_MAX:
        return content[:_RESULT_SUMMARY_MAX] + "…"
    return content


def log_event(kind: str, **fields: Any) -> None:
    """Append one JSONL event. Never raises — audit is best-effort.

    A failure to write the audit log must not break a tool call.
    Failures are swallowed; in dev they show up in stderr via the
    ``print`` fallback so they're not silently invisible.
    """
    record = {"ts": _now_iso(), "kind": kind, **fields}
    try:
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    except (TypeError, ValueError) as e:
        # Last-resort: stringify the whole thing.
        line = json.dumps(
            {"ts": record["ts"], "kind": kind, "_error": f"serialize_failed: {e}"},
            ensure_ascii=False,
        ) + "\n"
    try:
        with _LOCK:
            with _path().open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError as e:
        print(f"[audit] write failed: {e}")
