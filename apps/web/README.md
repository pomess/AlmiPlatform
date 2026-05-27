# Disease360 web app

Greenfield Vite + React 19 + TypeScript. No code reused from any other project.

## Dev

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies:
- `/api/harness/*` → `http://127.0.0.1:8002` (run with `python -m disease360_harness.api`)
- `/api/memory/*`  → `http://127.0.0.1:8001` (run with `python -m disease360_memory.main`)

## Pages

- `/app/chat`       Streaming chat (brain switcher, deep research)
- `/app/dashboard`  3D globe + competitive-intel news
- `/app/bullseye`   Pharma pipeline radar
- `/app/graph`      Brain graph visualisation
- `/app/brains`     Read-only browsing of brain pages (`hot.md`, `index.md`, wiki)
