"""Postgres connection pool for the Postgres-canonical vault (ADR 0001).

Phase 2: the memory service connects with a service-role DSN and bypasses
RLS at the database layer. Tenant scoping is enforced at the query layer
by explicitly passing `tenant_id` into every WHERE clause. Phase 4 swaps
this for per-user JWTs that re-engage RLS.

The pool is a module-level singleton, lazily initialized on first use.
``DISEASE360_VAULT_BACKEND`` gates whether the disk or Postgres code path is
active; the connection pool only spins up when the flag flips to
``postgres``, so disk-only test runs keep their old behavior.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg

from disease360_runtime.config import get as config_get

DEFAULT_BACKEND = "disk"


def vault_backend() -> str:
    """Return the active vault backend: ``"disk"`` or ``"postgres"``.

    Checks the env at every call rather than caching, so tests can flip
    the backend per fixture without restarting the process.
    """
    val = (config_get("DISEASE360_VAULT_BACKEND", DEFAULT_BACKEND) or DEFAULT_BACKEND).strip().lower()
    return val if val in ("disk", "postgres") else DEFAULT_BACKEND


def is_postgres() -> bool:
    return vault_backend() == "postgres"


def dev_tenant_id() -> str:
    """The implicit tenant for local dev / CLI calls.

    Required when ``DISEASE360_VAULT_BACKEND=postgres`` and there's no JWT in
    flight (phase 4 work). Raises if unset to surface misconfiguration
    early instead of silently inserting under a NULL tenant.
    """
    val = config_get("DISEASE360_DEV_TENANT_ID", "")
    if not val:
        raise RuntimeError(
            "DISEASE360_DEV_TENANT_ID is unset; set it to Bruno's auth.users.id "
            "or pass tenant_id explicitly through the request."
        )
    return val


# --- Pool ------------------------------------------------------------------

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    """Lazily create and return the asyncpg pool."""
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        dsn = config_get("DISEASE360_SUPABASE_DB_URL", "")
        if not dsn:
            raise RuntimeError(
                "DISEASE360_SUPABASE_DB_URL is unset; cannot reach Postgres. "
                "Either flip DISEASE360_VAULT_BACKEND=disk or set the DSN."
            )
        # Pool size kept small: the memory service is one process and
        # most requests are short-lived. Bump if we add long transactions.
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=8,
            command_timeout=15.0,
            statement_cache_size=0,  # PgBouncer transaction mode forbids prepared
        )
    return _pool


async def close_pool() -> None:
    """Close the pool — call on app shutdown to flush connections cleanly."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the pool. Use as ``async with acquire() as c``."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection wrapped in a transaction."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


def env_snapshot() -> dict[str, Any]:
    """Diagnostic dump of the relevant env, with secrets redacted."""
    return {
        "DISEASE360_VAULT_BACKEND": vault_backend(),
        "DISEASE360_SUPABASE_DB_URL_set": bool(os.environ.get("DISEASE360_SUPABASE_DB_URL")),
        "DISEASE360_SUPABASE_SERVICE_ROLE_KEY_set": bool(
            os.environ.get("DISEASE360_SUPABASE_SERVICE_ROLE_KEY")
        ),
        "DISEASE360_DEV_TENANT_ID_set": bool(os.environ.get("DISEASE360_DEV_TENANT_ID")),
    }
