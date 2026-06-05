"""Env loader. Reads `.env` then the process environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    """Resolve the repo root.

    Honors ``DISEASE360_HOME`` if set, otherwise walks up from this file
    until it finds ``pyproject.toml``.
    """
    home = os.environ.get("DISEASE360_HOME")
    if home:
        return Path(home).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repo root; set DISEASE360_HOME.")


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load `.env` into os.environ (idempotent, cached)."""
    env_file = repo_root() / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def get(name: str, default: str | None = None) -> str | None:
    load_env()
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


def require(name: str) -> str:
    val = get(name)
    if not val:
        raise RuntimeError(f"Required env var {name} is not set.")
    return val
