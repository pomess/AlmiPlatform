"""SQLite-backed approval queue.

This is the *user-facing* mirror of langgraph's interrupt state. The actual
agent pause/resume is handled by a langgraph checkpointer; this table is what
the CLI and web app query and mutate.

Schema:
    approvals(
        id              TEXT PRIMARY KEY,   -- uuid4
        thread_id       TEXT NOT NULL,      -- langgraph thread to resume
        tool            TEXT NOT NULL,
        args_json       TEXT NOT NULL,
        rationale       TEXT,
        status          TEXT NOT NULL,      -- pending|approved|denied|expired|dnd_held
        created_at      TEXT NOT NULL,      -- ISO8601 UTC
        expires_at      TEXT NOT NULL,
        resolved_at     TEXT,
        resolved_by     TEXT                -- 'cli' | 'web' | 'gesture' | 'timeout'
    )
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from kairos_runtime.config import get, repo_root

from . import audit

PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"
EXPIRED = "expired"
DND_HELD = "dnd_held"

DEFAULT_TENANT_ID = "local"


def _db_path() -> Path:
    p = repo_root() / "services" / "harness" / "data" / "approvals.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_db_path())
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id          TEXT PRIMARY KEY,
            thread_id   TEXT NOT NULL,
            tenant_id   TEXT NOT NULL DEFAULT 'local',
            tool        TEXT NOT NULL,
            args_json   TEXT NOT NULL,
            rationale   TEXT,
            status      TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        )
        """
    )
    # Backfill the column on databases created before tenant_id was added.
    cols = {row[1] for row in c.execute("PRAGMA table_info(approvals)").fetchall()}
    if "tenant_id" not in cols:
        c.execute(
            "ALTER TABLE approvals ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'local'"
        )
    c.execute("CREATE INDEX IF NOT EXISTS idx_status ON approvals(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_thread ON approvals(thread_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON approvals(tenant_id)")
    return c


@dataclass
class Approval:
    id: str
    thread_id: str
    tool: str
    args: dict[str, Any]
    rationale: str | None
    status: str
    created_at: str
    expires_at: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    tenant_id: str = DEFAULT_TENANT_ID

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _select_columns() -> str:
    """Explicit column list keeps row tuples stable across schema migrations."""
    return (
        "id, thread_id, tool, args_json, rationale, status, "
        "created_at, expires_at, resolved_at, resolved_by, tenant_id"
    )


def _row_to_approval(row: tuple) -> Approval:
    return Approval(
        id=row[0],
        thread_id=row[1],
        tool=row[2],
        args=json.loads(row[3]),
        rationale=row[4],
        status=row[5],
        created_at=row[6],
        expires_at=row[7],
        resolved_at=row[8],
        resolved_by=row[9],
        tenant_id=row[10] if len(row) > 10 and row[10] else DEFAULT_TENANT_ID,
    )


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _is_in_dnd(now: datetime | None = None) -> bool:
    """Return True if current local time is within the DND window."""
    tz_name = get("KAIROS_TIMEZONE", "Europe/Madrid") or "Europe/Madrid"
    start_s = (get("KAIROS_DND_START", "01:00") or "01:00").strip()
    end_s = (get("KAIROS_DND_END", "07:00") or "07:00").strip()
    try:
        sh, sm = (int(x) for x in start_s.split(":"))
        eh, em = (int(x) for x in end_s.split(":"))
    except ValueError:
        return False
    now = now or _now_utc()
    local = now.astimezone(ZoneInfo(tz_name))
    t = local.time()
    start = time(sh, sm)
    end = time(eh, em)
    if start <= end:
        return start <= t < end
    # window crosses midnight
    return t >= start or t < end


def create(
    *,
    thread_id: str,
    tool: str,
    args: dict[str, Any],
    rationale: str | None = None,
    timeout_seconds: int | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> Approval:
    timeout = timeout_seconds or int(get("KAIROS_APPROVAL_TIMEOUT_SECONDS", "300") or 300)
    now = _now_utc()
    expires = now + timedelta(seconds=timeout)
    status = DND_HELD if _is_in_dnd(now) else PENDING
    item = Approval(
        id=str(uuid.uuid4()),
        thread_id=thread_id,
        tool=tool,
        args=args,
        rationale=rationale,
        status=status,
        created_at=_iso(now),
        expires_at=_iso(expires),
        tenant_id=tenant_id or DEFAULT_TENANT_ID,
    )
    c = _conn()
    try:
        c.execute(
            """INSERT INTO approvals(
                id, thread_id, tool, args_json, rationale, status,
                created_at, expires_at, tenant_id
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                item.id,
                item.thread_id,
                item.tool,
                json.dumps(item.args),
                item.rationale,
                item.status,
                item.created_at,
                item.expires_at,
                item.tenant_id,
            ),
        )
        c.commit()
    finally:
        c.close()
    audit.log_event(
        "approval_created",
        approval_id=item.id,
        thread_id=item.thread_id,
        tenant_id=item.tenant_id,
        tool=item.tool,
        args_redacted=audit.redact_args(item.args),
        rationale=item.rationale,
        status=item.status,
        expires_at=item.expires_at,
    )
    return item


def list_(status: str | None = None, tenant_id: str | None = None) -> list[Approval]:
    _expire_overdue()
    c = _conn()
    cols = _select_columns()
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "ORDER BY created_at" if status else "ORDER BY created_at DESC"
        rows = c.execute(
            f"SELECT {cols} FROM approvals {where} {order}", params
        ).fetchall()
        return [_row_to_approval(r) for r in rows]
    finally:
        c.close()


def get_by_id(approval_id: str) -> Approval | None:
    c = _conn()
    try:
        row = c.execute(
            f"SELECT {_select_columns()} FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return _row_to_approval(row) if row else None
    finally:
        c.close()


def resolve(approval_id: str, *, decision: str, by: str) -> Approval | None:
    """Mark an approval row as approved/denied. Returns the updated row."""
    if decision not in (APPROVED, DENIED):
        raise ValueError(f"decision must be {APPROVED!r} or {DENIED!r}")
    c = _conn()
    try:
        c.execute(
            """UPDATE approvals
                  SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE id = ? AND status IN (?, ?)""",
            (decision, _iso(_now_utc()), by, approval_id, PENDING, DND_HELD),
        )
        c.commit()
    finally:
        c.close()
    updated = get_by_id(approval_id)
    if updated and updated.status == decision and updated.resolved_by == by:
        audit.log_event(
            "approval_resolved",
            approval_id=updated.id,
            thread_id=updated.thread_id,
            tenant_id=updated.tenant_id,
            tool=updated.tool,
            decision=decision,
            resolved_by=by,
            resolved_at=updated.resolved_at,
        )
    return updated


def drain_dnd() -> int:
    """Move all `dnd_held` rows to `pending`. Returns count drained."""
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, thread_id, tool FROM approvals WHERE status = ?",
            (DND_HELD,),
        ).fetchall()
        cur = c.execute(
            "UPDATE approvals SET status = ? WHERE status = ?",
            (PENDING, DND_HELD),
        )
        c.commit()
        drained = cur.rowcount or 0
    finally:
        c.close()
    if drained:
        audit.log_event(
            "approval_drained",
            count=drained,
            ids=[r[0] for r in rows],
        )
    return drained


def _expire_overdue() -> int:
    """Mark `pending` items past their expires_at as `expired`."""
    now_iso = _iso(_now_utc())
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id, thread_id, tool FROM approvals WHERE status = ? AND expires_at < ?",
            (PENDING, now_iso),
        ).fetchall()
        cur = c.execute(
            """UPDATE approvals
                  SET status = ?, resolved_by = ?, resolved_at = ?
                WHERE status = ? AND expires_at < ?""",
            (EXPIRED, "timeout", now_iso, PENDING, now_iso),
        )
        c.commit()
        expired = cur.rowcount or 0
    finally:
        c.close()
    for row in rows:
        audit.log_event(
            "approval_resolved",
            approval_id=row[0],
            thread_id=row[1],
            tool=row[2],
            decision=EXPIRED,
            resolved_by="timeout",
            resolved_at=now_iso,
        )
    return expired
