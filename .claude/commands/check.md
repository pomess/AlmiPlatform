---
description: Run the full Disease360 check loop — ruff, mypy, pytest, frontend tsc
---

Run these in parallel where possible and report a punch list of failures.

1. `ruff check .` from the repo root.
2. `mypy services` from the repo root.
3. `pytest` from the repo root.
4. `npx tsc --noEmit` from `apps/web/`.

For each step, report pass/fail and a one-line summary. If any fail, surface the first 3 errors verbatim with file:line references. Don't fix anything — this is read-only validation.
