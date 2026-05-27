"""Fire-and-forget run store backed by SQLite.

submit_run() spawns the research coroutine as a background task and persists
progress/results to research_runs.sqlite. get_run() retrieves status.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from disease360_runtime.config import repo_root

from .config import DepthTier
from .state import ProgressEvent, ResearchReport, RunStatus

log = logging.getLogger(__name__)

_DB_PATH: Path | None = None
_ACTIVE_TASKS: dict[str, asyncio.Task] = {}


def _db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        p = repo_root() / "services" / "harness" / "data" / "research_runs.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        _DB_PATH = p
    return _DB_PATH


def _init_db() -> None:
    """Create the runs table if it doesn't exist."""
    conn = sqlite3.connect(str(_db_path()))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            query TEXT NOT NULL,
            depth_tier TEXT,
            progress TEXT DEFAULT '[]',
            report TEXT,
            error TEXT,
            started_at TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _update_run(run_id: str, **fields: Any) -> None:
    """Update fields on a run record."""
    conn = sqlite3.connect(str(_db_path()))
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values())
    vals.append(run_id)
    conn.execute(f"UPDATE research_runs SET {sets} WHERE run_id = ?", vals)
    conn.commit()
    conn.close()


async def submit_run(
    query: str,
    *,
    depth_tier: DepthTier | None = None,
) -> str:
    """Submit a research run as a background task. Returns the run_id immediately."""
    from .runner import deep_research

    _init_db()
    run_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(str(_db_path()))
    conn.execute(
        "INSERT INTO research_runs (run_id, status, query, depth_tier, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (run_id, "running", query, depth_tier, now),
    )
    conn.commit()
    conn.close()

    progress_events: list[dict] = []

    def _on_progress(event: ProgressEvent) -> None:
        progress_events.append(event.model_dump(mode="json"))
        try:
            _update_run(run_id, progress=json.dumps(progress_events))
        except Exception:
            pass

    async def _run() -> None:
        try:
            report = await deep_research(
                query, depth_tier=depth_tier, on_progress=_on_progress, run_id=run_id
            )
            _update_run(
                run_id,
                status="completed",
                report=report.model_dump_json(),
                completed_at=datetime.now().isoformat(),
                progress=json.dumps(progress_events),
            )
        except asyncio.CancelledError:
            _update_run(run_id, status="cancelled")
        except Exception as exc:
            log.error("Background research run %s failed: %s", run_id, exc)
            _update_run(
                run_id,
                status="failed",
                error=str(exc),
                completed_at=datetime.now().isoformat(),
            )
        finally:
            _ACTIVE_TASKS.pop(run_id, None)

    task = asyncio.create_task(_run())
    _ACTIVE_TASKS[run_id] = task
    return run_id


def get_run(run_id: str) -> RunStatus:
    """Get the current status of a research run."""
    _init_db()
    conn = sqlite3.connect(str(_db_path()))
    row = conn.execute(
        "SELECT run_id, status, progress, report, error, started_at, completed_at "
        "FROM research_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    conn.close()

    if not row:
        return RunStatus(run_id=run_id, status="pending", error="Run not found")

    run_id_, status, progress_json, report_json, error, started_at, completed_at = row

    progress: list[ProgressEvent] = []
    if progress_json:
        try:
            for ev in json.loads(progress_json):
                progress.append(ProgressEvent(**ev))
        except Exception:
            pass

    report: ResearchReport | None = None
    if report_json:
        try:
            report = ResearchReport.model_validate_json(report_json)
        except Exception:
            pass

    return RunStatus(
        run_id=run_id_,
        status=status,
        progress=progress,
        report=report,
        error=error,
        started_at=datetime.fromisoformat(started_at) if started_at else None,
        completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
    )
