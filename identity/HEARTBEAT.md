# HEARTBEAT

> Cron-like proactive schedule. JARVIS reads this on boot and sets timers. Each block is a self-contained job description in plain English; the harness translates it to a tool plan at trigger time.

> All times are **Europe/Madrid**.

## Daily

### 07:00 — DND drain
Do Not Disturb window ended. Move every `dnd_held` row in the approval queue to `pending`, sorted oldest-first. Surface count to the next active channel (CLI status, web banner).

### 08:00 — Morning digest
Compose a 5-bullet briefing covering:
1. Today's calendar (next 12 hours), with conflicts flagged.
2. Inbox triage: senders that matter, threads needing reply.
3. Open todos from Bruno's Brain (the `#followup` and `#waiting` tags).
4. Anything from yesterday's `log.md` that wasn't closed.
5. Weather (Barcelona) and one "useful note" — a wiki page that's relevant to today.

Render in CLI on demand; if Bruno is at the PC, also speak it (when voice is online).

### 23:30 — Day close
- Skim today's `log.md`. Identify items that should become wiki pages.
- Propose ingestions (with approval) to the relevant brain.
- File any unfiled meeting notes.
- **Hot-cache compaction**: items older than 7 days or untouched in the last day → propose moving to wiki pages. If `hot.md` is over its token budget (1500 tokens), trigger a compaction pass and surface the diff for approval.

## Weekly

### Sunday 18:00 — Lint pass
Run the wiki linter on every brain. Surface broken wikilinks, orphan pages, conflicting facts. Render as a report in the web app.

## Watchers (continuous)

_(None yet. Phase 2 candidates: "alert if email about X", "alert if calendar event added by someone else".)_

## Rules

- DND window: **01:00–07:00 Europe/Madrid**. Proactive jobs scheduled inside this window are skipped (digest never lands at 03:00). Approval requests created during DND are tagged `dnd_held` in the SQLite queue and drained by the 07:00 job.
- Never run two jobs concurrently — queue them.
- If a job fails, retry once after 60s, then file an entry to `log.md` and stop.
