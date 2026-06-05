"""Unity Catalog connection client for Disease360 Atlas.

Provides connection pooling to the Databricks SQL Warehouse
for reading from Platinum tables.
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

_CATALOG = None
_SCHEMA = "genai_mcm_d360"


def catalog() -> str:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = os.environ.get("ATLAS_CATALOG", "dev_gold_commercial")
    return _CATALOG


def schema() -> str:
    return _SCHEMA


def full_table(name: str) -> str:
    return f"{catalog()}.{schema()}.{name}"


def get_connection():
    """Create a Databricks SQL connection.

    In Databricks Apps: uses auto-injected service principal credentials.
    In local dev: uses DATABRICKS_TOKEN personal access token.
    Returns None if credentials are not configured (local dev without Databricks).
    """
    from databricks import sql as databricks_sql

    server = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", "")
    token = os.environ.get("DATABRICKS_TOKEN")

    if not server or not http_path:
        return None

    return databricks_sql.connect(
        server_hostname=server,
        http_path=http_path,
        access_token=token,
    )


@contextmanager
def cursor():
    """Context manager that yields a cursor and handles connection lifecycle."""
    conn = get_connection()
    if conn is None:
        raise ConnectionError("Databricks not configured")
    try:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
    finally:
        conn.close()


def is_configured() -> bool:
    """Return True if Databricks credentials are available."""
    server = os.environ.get("DATABRICKS_SERVER_HOSTNAME", "")
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", "")
    return bool(server and http_path)


def query(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute a SQL query and return results as a list of dicts."""
    with cursor() as cur:
        cur.execute(sql, parameters=params)
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def query_one(sql: str, params: dict[str, Any] | None = None) -> dict | None:
    """Execute a SQL query and return a single result or None."""
    results = query(sql, params)
    return results[0] if results else None
