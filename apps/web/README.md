# Kairos web app

Greenfield Vite + React 19 + TypeScript + Tailwind. No code reused from any other project.

## Dev

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies:
- `/api/harness/*` → `http://127.0.0.1:8002` (run with `python -m kairos_harness.api`)
- `/api/memory/*`  → `http://127.0.0.1:8001` (run with `python -m kairos_memory.main`)

## Pages

- `/`            Chat (brain switcher, streaming-ready)
- `/approvals`   Pending tool calls; webcam toggle for 👍/👎 gesture port
- `/brains`      List of brains (memory service)
- `/brain/:id`   Read-only view of one brain's `hot.md` + `index.md`
- `/settings`    Gesture settings (localStorage)
