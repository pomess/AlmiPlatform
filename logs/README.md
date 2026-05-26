# Logs

This directory holds runtime logs. None of them are committed.

- `audit.jsonl` — every tool call, every approval decision, with rationale.
- `errors.log` — exceptions with stack traces.
- `latency.jsonl` — per-turn timing for tuning.

All log writes go through the harness's logging service so we can swap to a real log backend later (Loki, etc.) without touching call sites.
