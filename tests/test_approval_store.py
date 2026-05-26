"""Approval queue — create, resolve, expire, DND, persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from kairos_harness import approval_store


def test_create_pending_outside_dnd(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "01:00")
    monkeypatch.setenv("KAIROS_DND_END", "07:00")
    fake_now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    with patch.object(approval_store, "_now_utc", return_value=fake_now):
        a = approval_store.create(
            thread_id="t1", tool="write_note", args={"x": 1}, rationale="why"
        )
    assert a.status == approval_store.PENDING
    assert a.thread_id == "t1"
    assert a.args == {"x": 1}
    assert a.rationale == "why"
    fetched = approval_store.get_by_id(a.id)
    assert fetched is not None and fetched.id == a.id


def test_create_uses_dnd_held_inside_window(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_TIMEZONE", "UTC")
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "23:59")
    a = approval_store.create(thread_id="t", tool="x", args={})
    assert a.status == approval_store.DND_HELD


def test_drain_dnd_promotes_to_pending(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_TIMEZONE", "UTC")
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "23:59")
    approval_store.create(thread_id="t", tool="x", args={})
    approval_store.create(thread_id="t", tool="y", args={})
    n = approval_store.drain_dnd()
    assert n == 2
    statuses = {a.status for a in approval_store.list_(approval_store.PENDING)}
    assert statuses == {approval_store.PENDING}


def test_resolve_approve(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={})
    updated = approval_store.resolve(a.id, decision=approval_store.APPROVED, by="cli")
    assert updated is not None
    assert updated.status == approval_store.APPROVED
    assert updated.resolved_by == "cli"
    assert updated.resolved_at is not None


def test_resolve_deny(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={})
    updated = approval_store.resolve(a.id, decision=approval_store.DENIED, by="web")
    assert updated is not None
    assert updated.status == approval_store.DENIED


def test_resolve_rejects_invalid_decision(kairos_home: Path):
    with pytest.raises(ValueError):
        approval_store.resolve("nonexistent", decision="maybe", by="cli")


def test_resolve_no_op_for_already_resolved(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={})
    approval_store.resolve(a.id, decision=approval_store.APPROVED, by="cli")
    # Second resolve attempt to deny should not change the row.
    updated = approval_store.resolve(a.id, decision=approval_store.DENIED, by="cli")
    assert updated is not None
    assert updated.status == approval_store.APPROVED


def test_dnd_held_can_still_be_resolved(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_TIMEZONE", "UTC")
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "23:59")
    a = approval_store.create(thread_id="t", tool="x", args={})
    assert a.status == approval_store.DND_HELD
    updated = approval_store.resolve(a.id, decision=approval_store.APPROVED, by="cli")
    assert updated is not None
    assert updated.status == approval_store.APPROVED


def test_expire_overdue(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_APPROVAL_TIMEOUT_SECONDS", "1")
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with (
        patch.object(approval_store, "_now_utc", return_value=past),
        patch.object(approval_store, "_is_in_dnd", return_value=False),
    ):
        a = approval_store.create(thread_id="t", tool="x", args={})
    # list_() runs _expire_overdue() under the hood.
    items = approval_store.list_()
    expired = [i for i in items if i.id == a.id][0]
    assert expired.status == approval_store.EXPIRED
    assert expired.resolved_by == "timeout"


def test_persistence_across_module_calls(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={"k": "v"})
    # Simulate a fresh process by re-fetching — the SQLite row should survive.
    fetched = approval_store.get_by_id(a.id)
    assert fetched is not None
    assert fetched.args == {"k": "v"}


def test_list_filters_by_status(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={})
    b = approval_store.create(thread_id="t", tool="y", args={})
    approval_store.resolve(a.id, decision=approval_store.APPROVED, by="cli")
    pending = approval_store.list_(approval_store.PENDING)
    approved = approval_store.list_(approval_store.APPROVED)
    assert {p.id for p in pending} == {b.id}
    assert {p.id for p in approved} == {a.id}


def test_dnd_window_crossing_midnight(kairos_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KAIROS_TIMEZONE", "UTC")
    monkeypatch.setenv("KAIROS_DND_START", "23:00")
    monkeypatch.setenv("KAIROS_DND_END", "07:00")
    inside = datetime(2026, 5, 14, 23, 30, tzinfo=timezone.utc)
    outside = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    assert approval_store._is_in_dnd(inside) is True
    assert approval_store._is_in_dnd(outside) is False


def test_malformed_dnd_config_falls_back_outside_window(
    kairos_home: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("KAIROS_DND_START", "not-a-time")
    monkeypatch.setenv("KAIROS_DND_END", "07:00")
    assert approval_store._is_in_dnd() is False
