"""Seed an on-disk vault into the Postgres-canonical vault (ADR 0001 phase 5).

Walks `vault/<brain>/` (or, if the legacy `vault/local/<brain>/` shape from
commit cf0da22 is in play, that path) and inserts rows into:
  - public.brains       (one row per brain, agents_md + index_md filled in)
  - public.pages        (one row per markdown file under wiki/ and raw/)
  - public.hot_cache    (one row per brain, body = hot.md content)
  - public.raw_captures (one row per file under raw/)
  - public.wikilinks    (refreshed by vault_pg.write_page)

Idempotent: uses INSERT ... ON CONFLICT, so re-runs update existing rows
instead of duplicating. Drops old wikilinks for each rewritten page.

Targets the tenant in `KAIROS_DEV_TENANT_ID`. Run once per environment.

Usage:
    uv run python scripts/migrate_vault_to_postgres.py
    uv run python scripts/migrate_vault_to_postgres.py --dry-run
    uv run python scripts/migrate_vault_to_postgres.py --brain "Bruno's Brain"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import frontmatter

# Make the in-repo packages importable when running as a bare script.
ROOT = Path(__file__).resolve().parent.parent
for sub in ("services/runtime", "services/memory"):
    sys.path.insert(0, str(ROOT / sub))

from kairos_memory import db, registry_pg, vault_pg  # noqa: E402
from kairos_memory.db import acquire  # noqa: E402


def _vault_root() -> Path:
    """Find the disk vault root.

    Phase 1 layout: `<repo>/vault/<brain>/`.
    cf0da22 layout: `<repo>/vault/local/<brain>/`.

    We pick the layout that actually has brains in it. If both exist
    (mid-migration), prefer the legacy top-level since it matches the
    pre-cf0da22 shape Bruno was running.
    """
    legacy = ROOT / "vault"
    nested = legacy / "local"
    if any(_looks_like_brain(p) for p in legacy.iterdir() if p.is_dir()):
        return legacy
    if nested.is_dir() and any(_looks_like_brain(p) for p in nested.iterdir() if p.is_dir()):
        return nested
    return legacy


def _looks_like_brain(p: Path) -> bool:
    return p.is_dir() and ((p / "wiki").is_dir() or (p / "hot.md").is_file())


def _read_or_empty(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _split_frontmatter(text: str) -> tuple[str, dict]:
    try:
        post = frontmatter.loads(text)
        return post.content, dict(post.metadata) if post.metadata else {}
    except Exception:
        return text, {}


async def _ensure_brain(tenant_id: str, brain_dir: Path, *, dry_run: bool) -> str | None:
    """Upsert the brain row. Returns the brain UUID, or None when dry-run."""
    name = brain_dir.name
    agents_md = _read_or_empty(brain_dir / "AGENTS.md")
    index_md = _read_or_empty(brain_dir / "index.md")

    if dry_run:
        print(f"[dry-run] brain: {name} (agents_md={len(agents_md)}B, index_md={len(index_md)}B)")
        return None

    async with acquire() as c:
        row = await c.fetchrow(
            """
            insert into public.brains (tenant_id, name, agents_md, index_md)
            values ($1, $2, $3, $4)
            on conflict (tenant_id, name) do update
                set agents_md = excluded.agents_md,
                    index_md = excluded.index_md,
                    updated_at = now()
            returning id::text as id
            """,
            tenant_id,
            name,
            agents_md or None,
            index_md or None,
        )
    print(f"  brain row: {name} -> {row['id']}")
    return row["id"]


async def _seed_hot(tenant_id: str, brain_id: str, brain_dir: Path, *, dry_run: bool) -> None:
    hot = _read_or_empty(brain_dir / "hot.md")
    if not hot:
        return
    if dry_run:
        print(f"  [dry-run] hot.md ({len(hot)}B)")
        return
    await vault_pg.write_hot(tenant_id, brain_id, hot)
    print(f"  hot.md ({len(hot)}B)")


async def _seed_pages(
    tenant_id: str, brain_id: str, brain_dir: Path, *, dry_run: bool
) -> int:
    """Walk wiki/ and write each markdown file as a page row."""
    wiki_dir = brain_dir / "wiki"
    if not wiki_dir.is_dir():
        return 0
    n = 0
    for md in sorted(wiki_dir.rglob("*.md")):
        if not md.is_file():
            continue
        rel = md.relative_to(brain_dir).as_posix()  # e.g. wiki/concepts/foo.md
        raw = md.read_text(encoding="utf-8")
        body, fm = _split_frontmatter(raw)
        if dry_run:
            print(f"    [dry-run] page: {rel} ({len(body)}B, fm-keys={list(fm)[:5]})")
        else:
            await vault_pg.write_page(tenant_id, brain_id, rel, body, fm)
            print(f"    page: {rel}")
        n += 1
    return n


async def _seed_raw(
    tenant_id: str, brain_id: str, brain_dir: Path, *, dry_run: bool
) -> int:
    raw_dir = brain_dir / "raw"
    if not raw_dir.is_dir():
        return 0
    n = 0
    for f in sorted(raw_dir.rglob("*")):
        if not f.is_file():
            continue
        # Skip binary files — raw_captures.body is text. ADR 0001 punts
        # binary blobs to Supabase Storage with a storage_path column
        # ("Open questions" in the ADR), so for now we just log and skip.
        if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4", ".zip"):
            print(f"    raw: {f.relative_to(raw_dir).as_posix()} (skipped — binary, defer to phase 6+)")
            continue
        if f.stat().st_size == 0:
            # .gitkeep and friends — no value in seeding empty rows.
            continue
        body = f.read_text(encoding="utf-8", errors="replace")
        # filename includes any subpath under raw/ so collisions across
        # subfolders don't merge.
        filename = f.relative_to(raw_dir).as_posix()
        if dry_run:
            print(f"    [dry-run] raw: {filename} ({len(body)}B)")
        else:
            # Skip if a row with the same filename already exists for
            # this brain — raw_captures has no unique constraint, so we
            # check explicitly to keep re-runs idempotent.
            async with acquire() as c:
                existing = await c.fetchval(
                    """
                    select 1 from public.raw_captures
                     where tenant_id = $1 and brain_id = $2 and filename = $3
                     limit 1
                    """,
                    tenant_id,
                    brain_id,
                    filename,
                )
            if existing:
                print(f"    raw: {filename} (skipped — already present)")
            else:
                await vault_pg.ingest_raw(tenant_id, brain_id, filename, body)
                print(f"    raw: {filename}")
        n += 1
    return n


async def migrate_brain(
    tenant_id: str, brain_dir: Path, *, dry_run: bool
) -> dict[str, int]:
    print(f"\n--- {brain_dir.name} ---")
    brain_id = await _ensure_brain(tenant_id, brain_dir, dry_run=dry_run)
    # Dry-run gets a placeholder brain_id so the page/raw walks can still
    # report what they'd write. Real writes are gated below by `dry_run`.
    effective_brain_id = brain_id or "00000000-0000-0000-0000-000000000000"
    await _seed_hot(tenant_id, effective_brain_id, brain_dir, dry_run=dry_run)
    pages = await _seed_pages(tenant_id, effective_brain_id, brain_dir, dry_run=dry_run)
    raw = await _seed_raw(tenant_id, effective_brain_id, brain_dir, dry_run=dry_run)
    return {"pages": pages, "raw": raw}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk the vault and print what would change, without writing.",
    )
    parser.add_argument(
        "--brain",
        action="append",
        default=None,
        help="Migrate only the named brain(s). Repeatable. Default: all brains.",
    )
    args = parser.parse_args()

    if not db.is_postgres():
        print(
            "KAIROS_VAULT_BACKEND must be 'postgres' to run this migration. "
            "Set it in policies/secrets.env first.",
            file=sys.stderr,
        )
        return 2

    try:
        tenant_id = db.dev_tenant_id()
    except RuntimeError as e:
        print(f"Cannot resolve tenant: {e}", file=sys.stderr)
        return 2

    root = _vault_root()
    print(f"Vault root: {root}")
    print(f"Tenant: {tenant_id}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")

    brains = [
        p for p in sorted(root.iterdir())
        if _looks_like_brain(p)
        and not p.name.startswith(".")
        and p.name != "local"  # skip the cf0da22 nested layer if both exist
    ]
    if args.brain:
        wanted = set(args.brain)
        brains = [b for b in brains if b.name in wanted]
        if not brains:
            print(f"No matching brains for: {wanted}", file=sys.stderr)
            return 1

    print(f"Brains to migrate: {[b.name for b in brains]}")

    totals = {"pages": 0, "raw": 0}
    for brain_dir in brains:
        result = await migrate_brain(tenant_id, brain_dir, dry_run=args.dry_run)
        totals["pages"] += result["pages"]
        totals["raw"] += result["raw"]

    print(
        f"\nDone. Brains: {len(brains)}, "
        f"pages: {totals['pages']}, raw captures: {totals['raw']}"
    )

    if not args.dry_run:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
