"""Audit-log writer + redactor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from disease360_harness import audit


def _read_audit(home: Path) -> list[dict]:
    p = home / "logs" / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]


def _reset_audit_path() -> None:
    """Force the audit module to re-resolve the path under the new DISEASE360_HOME."""
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


def test_log_event_writes_jsonl(disease360_home: Path):
    _reset_audit_path()
    audit.log_event("smoke", who="disease360", n=1)
    rows = _read_audit(disease360_home)
    assert len(rows) == 1
    assert rows[0]["kind"] == "smoke"
    assert rows[0]["who"] == "disease360"
    assert rows[0]["n"] == 1
    assert "ts" in rows[0]


def test_log_event_appends(disease360_home: Path):
    _reset_audit_path()
    audit.log_event("a", i=1)
    audit.log_event("b", i=2)
    rows = _read_audit(disease360_home)
    assert [r["kind"] for r in rows] == ["a", "b"]


def test_audit_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """DISEASE360_AUDIT_PATH bypasses repo_root()."""
    target = tmp_path / "custom" / "audit.jsonl"
    monkeypatch.setenv("DISEASE360_HOME", str(tmp_path))
    monkeypatch.setenv("DISEASE360_AUDIT_PATH", str(target))
    from disease360_runtime import config as runtime_config

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
