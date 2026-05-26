"""Audit-log writer + redactor + approval-store hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from kairos_harness import approval_store, audit


def _read_audit(home: Path) -> list[dict]:
    p = home / "logs" / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def _reset_audit_path() -> None:
    """Force the audit module to re-resolve the path under the new KAIROS_HOME."""
    audit._PATH = None


def test_redact_args_handles_secret_keys():
    out = audit.redact_args(
        {
            "to": "alice@example.com",
            "api_key": "sk-12345",
            "nested": {"AuthToken": "x", "ok": True},
            "list": [{"password": "y"}, "harmless"],
        }
    )
    assert out["to"] == "alice@example.com"
    assert out["api_key"] == "[REDACTED]"
    assert out["nested"]["AuthToken"] == "[REDACTED]"
    assert out["nested"]["ok"] is True
    assert out["list"][0]["password"] == "[REDACTED]"
    assert out["list"][1] == "harmless"


def test_summarize_result_truncates_long_strings():
    long = "x" * 1000
    s = audit.summarize_result(long)
    assert s.endswith("…")
    assert len(s) <= audit._RESULT_SUMMARY_MAX + 1


def test_summarize_result_handles_dicts():
    s = audit.summarize_result({"k": "v"})
    assert '"k"' in s and '"v"' in s


def test_log_event_writes_jsonl(kairos_home: Path):
    _reset_audit_path()
    audit.log_event("smoke", who="kairos", n=1)
    rows = _read_audit(kairos_home)
    assert len(rows) == 1
    assert rows[0]["kind"] == "smoke"
    assert rows[0]["who"] == "kairos"
    assert rows[0]["n"] == 1
    assert "ts" in rows[0]


def test_log_event_appends(kairos_home: Path):
    _reset_audit_path()
    audit.log_event("a", i=1)
    audit.log_event("b", i=2)
    rows = _read_audit(kairos_home)
    assert [r["kind"] for r in rows] == ["a", "b"]


def test_audit_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """KAIROS_AUDIT_PATH bypasses repo_root()."""
    target = tmp_path / "custom" / "audit.jsonl"
    monkeypatch.setenv("KAIROS_HOME", str(tmp_path))
    monkeypatch.setenv("KAIROS_AUDIT_PATH", str(target))
    from kairos_runtime import config as runtime_config

    runtime_config.load_env.cache_clear()
    _reset_audit_path()
    audit.log_event("x", v=1)
    assert target.exists()
    rows = [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert rows[0]["kind"] == "x"


def test_approval_create_emits_audit_event(
    kairos_home: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_audit_path()
    monkeypatch.setenv("KAIROS_DND_START", "01:00")
    monkeypatch.setenv("KAIROS_DND_END", "07:00")
    a = approval_store.create(
        thread_id="t1",
        tool="send_email",
        args={"to": "x@y.com", "api_key": "secret"},
        rationale="test",
    )
    rows = _read_audit(kairos_home)
    created = [r for r in rows if r["kind"] == "approval_created"]
    assert len(created) == 1
    r = created[0]
    assert r["approval_id"] == a.id
    assert r["tool"] == "send_email"
    assert r["args_redacted"]["to"] == "x@y.com"
    assert r["args_redacted"]["api_key"] == "[REDACTED]"


def test_approval_resolve_emits_audit_event(
    kairos_home: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_audit_path()
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "00:01")
    a = approval_store.create(thread_id="t", tool="x", args={})
    approval_store.resolve(a.id, decision=approval_store.APPROVED, by="cli")
    rows = _read_audit(kairos_home)
    resolved = [r for r in rows if r["kind"] == "approval_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["decision"] == approval_store.APPROVED
    assert resolved[0]["resolved_by"] == "cli"


def test_drain_dnd_emits_audit_event(
    kairos_home: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_audit_path()
    monkeypatch.setenv("KAIROS_TIMEZONE", "UTC")
    monkeypatch.setenv("KAIROS_DND_START", "00:00")
    monkeypatch.setenv("KAIROS_DND_END", "23:59")
    approval_store.create(thread_id="t", tool="x", args={})
    approval_store.create(thread_id="t", tool="y", args={})
    approval_store.drain_dnd()
    rows = _read_audit(kairos_home)
    drained = [r for r in rows if r["kind"] == "approval_drained"]
    assert len(drained) == 1
    assert drained[0]["count"] == 2
    assert len(drained[0]["ids"]) == 2


def test_expire_emits_audit_event(
    kairos_home: Path, monkeypatch: pytest.MonkeyPatch
):
    _reset_audit_path()
    from datetime import UTC, datetime, timedelta
    from unittest.mock import patch

    monkeypatch.setenv("KAIROS_APPROVAL_TIMEOUT_SECONDS", "1")
    past = datetime.now(UTC) - timedelta(hours=1)
    with (
        patch.object(approval_store, "_now_utc", return_value=past),
        patch.object(approval_store, "_is_in_dnd", return_value=False),
    ):
        approval_store.create(thread_id="t", tool="x", args={})
    approval_store.list_()  # triggers _expire_overdue
    rows = _read_audit(kairos_home)
    expired = [
        r
        for r in rows
        if r["kind"] == "approval_resolved" and r["decision"] == approval_store.EXPIRED
    ]
    assert len(expired) == 1
    assert expired[0]["resolved_by"] == "timeout"
