"""BrainRegistry — discovers brains under <repo>/vault/<tenant_id>/."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from disease360_runtime.config import repo_root

from .schemas import BrainSummary
from .vault import list_markdown

DEFAULT_TENANT_ID = "local"


@dataclass
class Brain:
    id: str
    root: Path  # vault/<tenant_id>/<id>/
    tenant_id: str = DEFAULT_TENANT_ID

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def hot_path(self) -> Path:
        return self.root / "hot.md"

    @property
    def index_path(self) -> Path:
        return self.root / "index.md"

    @property
    def log_path(self) -> Path:
        return self.root / "log.md"

    @property
    def agents_path(self) -> Path:
        return self.root / "AGENTS.md"

    def ensure_layout(self) -> None:
        for d in (self.wiki_dir, self.raw_dir):
            d.mkdir(parents=True, exist_ok=True)
        for f, default in [
            (self.hot_path, "# Hot cache\n\n_Empty._\n"),
            (self.index_path, f"# {self.id} — Index\n\n_(empty)_\n"),
            (self.log_path, "# Log\n\n"),
            (
                self.agents_path,
                "# AGENTS\n\n_Schema for ingest. See docs/04-karpathy-llm-wiki.md._\n",
            ),
        ]:
            if not f.exists():
                f.write_text(default, encoding="utf-8")

    def summary(self) -> BrainSummary:
        page_count = len(list_markdown(self.wiki_dir))
        return BrainSummary(
            id=self.id,
            title=self.id,
            page_count=page_count,
            has_hot=self.hot_path.exists() and self.hot_path.stat().st_size > 0,
        )


def vault_root() -> Path:
    """Top-level vault directory. Houses one subdir per tenant."""
    return repo_root() / "vault"


def tenant_root(tenant_id: str) -> Path:
    """Per-tenant vault directory. Houses one subdir per brain."""
    return vault_root() / tenant_id


def list_tenants() -> list[str]:
    root = vault_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def list_brains(tenant_id: str = DEFAULT_TENANT_ID) -> list[Brain]:
    root = tenant_root(tenant_id)
    if not root.is_dir():
        return []
    out: list[Brain] = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            out.append(Brain(id=p.name, root=p, tenant_id=tenant_id))
    return out


def get_brain(tenant_id: str, brain_id: str) -> Brain:
    for b in list_brains(tenant_id):
        if b.id == brain_id:
            return b
    raise KeyError(f"No such brain in tenant {tenant_id!r}: {brain_id!r}")


def _looks_like_brain_dir(p: Path) -> bool:
    """A brain directory has a wiki/ subdir or a hot.md file at its root."""
    return p.is_dir() and ((p / "wiki").is_dir() or (p / "hot.md").is_file())


def migrate_legacy_vault(target_tenant: str = DEFAULT_TENANT_ID) -> list[str]:
    """Move legacy `vault/<brain>/` directories under `vault/<target_tenant>/`.

    A pre-multitenant vault places brains directly under `vault/`. The new
    layout nests them under a tenant id. This helper detects brain-shaped
    directories at the old location and relocates them in place.

    Returns the list of brain ids that were migrated. Idempotent: a vault
    already in the new layout produces an empty list.
    """
    root = vault_root()
    if not root.is_dir():
        return []
    legacy = [p for p in root.iterdir() if _looks_like_brain_dir(p)]
    if not legacy:
        return []
    target = tenant_root(target_tenant)
    target.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for src in legacy:
        dst = target / src.name
        if dst.exists():
            # Tenant already has a brain by this name — leave the legacy dir alone.
            continue
        shutil.move(str(src), str(dst))
        moved.append(src.name)
    return moved


def bootstrap_default_brains(tenant_id: str = DEFAULT_TENANT_ID) -> None:
    """Create the two default brains on first run if the tenant's vault is empty.

    Also migrates any legacy top-level brain directories into the default
    tenant. Idempotent.
    """
    vault_root().mkdir(parents=True, exist_ok=True)
    migrate_legacy_vault(tenant_id)

    root = tenant_root(tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    if any(p.is_dir() for p in root.iterdir()):
        return
    for name in ("Bruno's Brain", "Deloitte's Brain"):
        Brain(id=name, root=root / name, tenant_id=tenant_id).ensure_layout()
