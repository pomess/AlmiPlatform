"""Shared pytest fixtures.

Tests run against a tmp_path-scoped fake "Disease360 home" so they never touch the
real `vault/`, `services/harness/data/`, or the project's `policies/secrets.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from atlas_runtime import config as runtime_config


@pytest.fixture
def disease360_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point repo_root() at a tmp directory laid out like the real repo.

    Creates the `policies/` and `identity/` markers that `repo_root()` walks
    for, plus an empty `vault/`. Clears the cached env loader and module-level
    DB path caches so each test gets a clean slate.
    """
    (tmp_path / "policies").mkdir()
    (tmp_path / "identity").mkdir()
    (tmp_path / "vault").mkdir()
    (tmp_path / "services" / "harness" / "data").mkdir(parents=True)
    (tmp_path / "services" / "memory" / "data").mkdir(parents=True)

    monkeypatch.setenv("DISEASE360_HOME", str(tmp_path))

    # Reset caches that pin paths from a previous repo_root().
    runtime_config.load_env.cache_clear()
    from atlas_runtime.research import store as research_store

    research_store._DB_PATH = None
    research_store._ACTIVE_TASKS.clear()

    # Reset atlas cache, which is keyed by brain id and outlives test runs.
    from atlas_memory import atlas as atlas_mod

    atlas_mod.invalidate(None)

    # Reset audit module's cached path so it re-resolves under the new
    # DISEASE360_HOME instead of writing to a previous test's tmp dir.
    from atlas_harness import audit as audit_mod

    audit_mod._PATH = None

    return tmp_path


@pytest.fixture
def vault_root(disease360_home: Path) -> Path:
    """Top-level vault directory (parent of per-tenant subdirs)."""
    return disease360_home / "vault"


@pytest.fixture
def tenant_root(vault_root: Path) -> Path:
    """Default-tenant directory under the test vault."""
    from atlas_memory.registry import DEFAULT_TENANT_ID

    p = vault_root / DEFAULT_TENANT_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def make_brain(tenant_root: Path):
    """Factory that builds a brain folder with the standard layout under the default tenant."""
    from atlas_memory.registry import DEFAULT_TENANT_ID, Brain

    def _make(brain_id: str = "Test Brain") -> Brain:
        b = Brain(id=brain_id, root=tenant_root / brain_id, tenant_id=DEFAULT_TENANT_ID)
        b.ensure_layout()
        return b

    return _make
