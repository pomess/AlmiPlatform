# CLI channel

Thin Python CLI built with `typer`. **Spawn-and-exit** per command (Phase 1; daemon mode Phase 4).

## Commands (Phase 1)

```
disease360 ask "<question>"             # one-shot; runs the Deep Agent in-process
disease360 status                       # harness reachable? memory reachable? counts of pending approvals
disease360 approvals list               # reads SQLite directly (services/harness/data/approvals.db)
disease360 approvals approve <id>       # POST harness REST so the paused agent resumes
disease360 approvals deny <id>          # POST harness REST
disease360 brains                       # GET memory /brains
disease360 switch <brain>               # write to ~/.disease360/state.json (active brain for the next ask)
```

## Phase 2+

```
disease360 digest                       # run morning digest now
disease360 ingest <file>                # ingest into active brain (require_approval)
disease360 daemon                       # long-running mode (Phase 4)
```

Status: **scaffolded — implement in Phase 1**.
