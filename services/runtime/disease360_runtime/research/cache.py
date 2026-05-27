"""Per-run in-memory cache for search results and fetched content.

Keyed on (stage, query_hash). Prevents duplicate network calls when multiple
subagents ask similar questions within the same research run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def _hash_key(stage: str, query: str) -> str:
    raw = f"{stage}::{query.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RunCache:
    """Simple per-run cache backed by a dict. Threadsafe not required — async single-threaded."""

    _store: dict[str, Any] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, stage: str, query: str) -> Any | None:
        key = _hash_key(stage, query)
        val = self._store.get(key)
        if val is not None:
            self.hits += 1
        else:
            self.misses += 1
        return val

    def put(self, stage: str, query: str, value: Any) -> None:
        key = _hash_key(stage, query)
        self._store[key] = value

    def has(self, stage: str, query: str) -> bool:
        return _hash_key(stage, query) in self._store

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    @property
    def size(self) -> int:
        return len(self._store)
