# CLI channel

Thin Python CLI built with `typer`. **Spawn-and-exit** per command (Phase 1; daemon mode Phase 4).

## Commands (Phase 1)

```
kairos ask "<question>"             # one-shot; runs the Deep Agent in-process
kairos status                       # harness reachable? memory reachable? counts of pending approvals
kairos approvals list               # reads SQLite directly (services/harness/data/approvals.db)
kairos approvals approve <id>       # POST harness REST so the paused agent resumes
kairos approvals deny <id>          # POST harness REST
kairos brains                       # GET memory /brains
kairos switch <brain>               # write to ~/.kairos/state.json (active brain for the next ask)
```

## Phase 2+

```
kairos digest                       # run morning digest now
kairos ingest <file>                # ingest into active brain (require_approval)
kairos daemon                       # long-running mode (Phase 4)
```

Status: **scaffolded — implement in Phase 1**.
