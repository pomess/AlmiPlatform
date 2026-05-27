"""Env loader. Reads `policies/secrets.env` then the process environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    """Resolve the repo root.

    Honors ``DISEASE360_HOME`` if set, otherwise walks up from this file
    until it finds the ``policies/`` directory.
    """
    home = os.environ.get("DISEASE360_HOME")
    if home:
        return Path(home).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "policies").is_dir() and (parent / "identity").is_dir():
            return parent
    raise RuntimeError("Could not locate Disease360 repo root; set DISEASE360_HOME.")


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load `policies/secrets.env` into os.environ (idempotent, cached)."""
    secrets = repo_root() / "policies" / "secrets.env"
    if secrets.is_file():
        load_dotenv(secrets, override=False)


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
