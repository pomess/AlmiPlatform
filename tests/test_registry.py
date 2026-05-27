"""Brain registry — discovery, layout bootstrap, summary, tenant scoping."""

from __future__ import annotations

from pathlib import Path

import pytest

from disease360_memory.registry import (
    DEFAULT_TENANT_ID,
    Brain,
    bootstrap_default_brains,
    get_brain,
    list_brains,
    list_tenants,
    migrate_legacy_vault,
    tenant_root,
    vault_root,
)


def test_vault_root_resolves_under_disease360_home(disease360_home: Path):
    assert vault_root() == disease360_home / "vault"


def test_tenant_root_nests_under_vault(disease360_home: Path):
    assert tenant_root("acme") == disease360_home / "vault" / "acme"


def test_ensure_layout_creates_skeleton(tenant_root: Path):
    b = Brain(id="A", root=tenant_root / "A")
    b.ensure_layout()
    assert b.wiki_dir.is_dir()
    assert b.raw_dir.is_dir()
    for p in (b.hot_path, b.index_path, b.log_path, b.agents_path):
        assert p.is_file(), f"missing {p}"


def test_ensure_layout_is_idempotent(tenant_root: Path):
    b = Brain(id="B", root=tenant_root / "B")
    b.ensure_layout()
    b.hot_path.write_text("custom hot\n", encoding="utf-8")
    b.ensure_layout()
    assert b.hot_path.read_text(encoding="utf-8") == "custom hot\n"


def test_summary_counts_only_wiki_pages(tenant_root: Path):
    b = Brain(id="C", root=tenant_root / "C")
    b.ensure_layout()
    (b.wiki_dir / "one.md").write_text("# one", encoding="utf-8")
    (b.wiki_dir / "two.md").write_text("# two", encoding="utf-8")
    (b.raw_dir / "ignored.md").write_text("# ignored", encoding="utf-8")
    s = b.summary()
    assert s.id == "C"
    assert s.page_count == 2
    assert s.has_hot is True


def test_list_brains_skips_dotdirs_and_files(tenant_root: Path):
    (tenant_root / "Real").mkdir()
    (tenant_root / ".hidden").mkdir()
    (tenant_root / "stray.txt").write_text("nope")
    ids = [b.id for b in list_brains()]
    assert ids == ["Real"]


def test_list_brains_empty(tenant_root: Path):
    assert list_brains() == []


def test_get_brain_raises_for_unknown(tenant_root: Path):
    (tenant_root / "X").mkdir()
    with pytest.raises(KeyError):
        get_brain(DEFAULT_TENANT_ID, "nope")


def test_bootstrap_creates_defaults_when_empty(vault_root: Path):
    bootstrap_default_brains()
    ids = sorted(b.id for b in list_brains())
    assert ids == ["Bruno's Brain", "Deloitte's Brain"]


def test_bootstrap_is_noop_when_brains_exist(tenant_root: Path):
    (tenant_root / "Existing").mkdir()
    bootstrap_default_brains()
    ids = [b.id for b in list_brains()]
    assert ids == ["Existing"]


def test_brains_are_isolated_across_tenants(vault_root: Path):
    (vault_root / "alpha").mkdir()
    (vault_root / "alpha" / "Brain1").mkdir()
    (vault_root / "beta").mkdir()
    (vault_root / "beta" / "Brain2").mkdir()
    assert [b.id for b in list_brains("alpha")] == ["Brain1"]
    assert [b.id for b in list_brains("beta")] == ["Brain2"]
    with pytest.raises(KeyError):
        get_brain("alpha", "Brain2")


def test_list_tenants_skips_dotdirs(vault_root: Path):
    (vault_root / "alpha").mkdir()
    (vault_root / ".trash").mkdir()
    (vault_root / "beta").mkdir()
    assert list_tenants() == ["alpha", "beta"]


def test_migrate_legacy_vault_moves_top_level_brains(vault_root: Path):
    legacy = vault_root / "Bruno's Brain"
    legacy.mkdir()
    (legacy / "wiki").mkdir()
    (legacy / "hot.md").write_text("# Hot\n", encoding="utf-8")
    moved = migrate_legacy_vault(DEFAULT_TENANT_ID)
    assert moved == ["Bruno's Brain"]
    assert (vault_root / DEFAULT_TENANT_ID / "Bruno's Brain" / "hot.md").is_file()
    assert not legacy.exists()


def test_migrate_legacy_vault_is_idempotent(vault_root: Path):
    (vault_root / DEFAULT_TENANT_ID / "Brain").mkdir(parents=True)
    assert migrate_legacy_vault(DEFAULT_TENANT_ID) == []
