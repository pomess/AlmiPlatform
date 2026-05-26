"""Knowledge atlas: a cheap, file-derived summary of every brain's contents.

The atlas is a compact JSON view of every brain's wiki: its purpose, top
entities, and top concepts. It is computed by walking the vault on disk
(no LLM, no FTS) and is cached per-brain keyed on the most recent mtime
under that brain's folder.

The harness injects the atlas into the system prompt so the agent knows,
*before* calling any memory tool, which brain holds which topic. With
that context the agent can:

1. Skip the slow cross-brain `search_wiki` and call `get_page` directly
   when the topic is already named in the atlas.
2. Verbalize a contextual filler ("Let me check your Deloitte notes.")
   while the page read is in flight, so the user is never sitting in
   silence wondering whether the assistant heard them.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from .registry import DEFAULT_TENANT_ID, Brain, list_brains
from .vault import title_from_body

# Caps: keep the rendered atlas around ~500 tokens total even with many brains.
MAX_ENTITIES_PER_BRAIN = 12
MAX_CONCEPTS_PER_BRAIN = 8
BLURB_CHAR_LIMIT = 140


@dataclass
class _CacheEntry:
    mtime: float
    payload: dict


_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(tenant_id: str, brain_id: str) -> str:
    return f"{tenant_id}/{brain_id}"


def invalidate(brain_id: str | None = None, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    """Drop the cached atlas. Pass `brain_id=None` to clear everything."""
    with _CACHE_LOCK:
        if brain_id is None:
            _CACHE.clear()
        else:
            _CACHE.pop(_cache_key(tenant_id, brain_id), None)


def build_atlas(tenant_id: str = DEFAULT_TENANT_ID) -> dict:
    """Compute (or fetch from cache) the atlas for every known brain in a tenant."""
    out: list[dict] = []
    for brain in list_brains(tenant_id):
        out.append(_brain_atlas(brain))
    return {"brains": out}


def _brain_atlas(brain: Brain) -> dict:
    latest = _max_mtime(brain.root)
    key = _cache_key(brain.tenant_id, brain.id)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached.mtime >= latest:
            return cached.payload

    payload = _compute_brain_atlas(brain, latest)

    with _CACHE_LOCK:
        _CACHE[key] = _CacheEntry(mtime=latest, payload=payload)
    return payload


def _compute_brain_atlas(brain: Brain, latest_mtime: float) -> dict:
    purpose = _read_purpose(brain)
    entities = _collect_pages(brain.wiki_dir / "entities", MAX_ENTITIES_PER_BRAIN)
    concepts = _collect_pages(brain.wiki_dir / "concepts", MAX_CONCEPTS_PER_BRAIN)
    page_count = sum(1 for _ in brain.wiki_dir.rglob("*.md")) if brain.wiki_dir.is_dir() else 0
    return {
        "id": brain.id,
        "purpose": purpose,
        "page_count": page_count,
        "key_entities": entities,
        "key_concepts": concepts,
        "updated_at": datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
        if latest_mtime
        else None,
    }


def _max_mtime(root: Path) -> float:
    if not root.is_dir():
        return 0.0
    latest = 0.0
    for p in root.rglob("*.md"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > latest:
            latest = m
    return latest


def _read_purpose(brain: Brain) -> str:
    """Pull the brain's one-line purpose from `wiki/overview.md`.

    Preference order:
      1. `purpose:` YAML frontmatter on overview.md (hand-authored, tightest).
      2. First non-heading paragraph of overview.md (auto-fallback).
      3. Brain id (last-resort fallback).
    """
    overview = brain.wiki_dir / "overview.md"
    if not overview.is_file():
        return brain.id
    try:
        post = frontmatter.loads(overview.read_text(encoding="utf-8"))
    except Exception:
        return brain.id
    fm_purpose = post.metadata.get("purpose") if post.metadata else None
    if isinstance(fm_purpose, str) and fm_purpose.strip():
        return fm_purpose.strip()
    # Fallback: first non-empty, non-heading paragraph.
    for raw_para in post.content.split("\n\n"):
        para = raw_para.strip()
        if not para or para.startswith("#"):
            continue
        return _truncate(_strip_wikilinks(para), 200)
    return brain.id


def _collect_pages(folder: Path, cap: int) -> list[dict]:
    """Return up to `cap` `{title, blurb, path}` records from a wiki subfolder.

    Sorted by mtime descending so recently-touched pages surface first.
    """
    if not folder.is_dir():
        return []
    files = [p for p in folder.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict] = []
    for path in files[:cap]:
        title, blurb = _page_title_and_blurb(path)
        out.append(
            {
                "title": title,
                "blurb": blurb,
                "path": _rel_path(path, folder),
            }
        )
    return out


def _page_title_and_blurb(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem.replace("-", " ").title(), ""
    try:
        post = frontmatter.loads(raw)
        body = post.content
        fm_title = post.metadata.get("title") if post.metadata else None
    except Exception:
        body = raw
        fm_title = None
    title = (
        fm_title.strip() if isinstance(fm_title, str) and fm_title.strip()
        else title_from_body(path, body)
    )
    blurb = ""
    for raw_para in body.split("\n\n"):
        para = raw_para.strip()
        if not para or para.startswith("#") or para.startswith("---"):
            continue
        blurb = _truncate(_strip_wikilinks(para), BLURB_CHAR_LIMIT)
        break
    return title, blurb


def _rel_path(path: Path, folder: Path) -> str:
    """Return the path relative to the brain root (e.g. 'wiki/entities/foo.md')."""
    try:
        # folder is .../wiki/entities; brain root is folder.parent.parent
        brain_root = folder.parent.parent
        return path.resolve().relative_to(brain_root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


_WIKILINK_INLINE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")


def _strip_wikilinks(text: str) -> str:
    """Replace `[[target|alias]]` with `alias` (or `target`) so blurbs read cleanly."""
    def _sub(m):
        return (m.group(2) or m.group(1)).strip()
    return _WIKILINK_INLINE.sub(_sub, text).replace("\n", " ").strip()


def _truncate(s: str, limit: int) -> str:
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    cut = s[: limit - 1].rsplit(" ", 1)[0]
    return cut + "\u2026"
