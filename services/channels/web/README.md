# Web channel

**Greenfield Vite + React 19 + TypeScript app** at [`apps/web/`](../../../apps/web/). No code reused from the KG project.

## Pages

- `/`            — Chat (SSE streaming, brain switcher)
- `/approvals`   — Pending tool calls; approve/deny; webcam toggle for slim 👍/👎 gesture port
- `/brain/:id`   — Read-only vault browser (index, hot, page tree, graph view)
- `/settings`    — Active brain, model override, gesture settings (fps/conf/cooldown — localStorage)

## Stack

- Vite + React 19 + TypeScript
- Tailwind CSS (fresh config)
- TanStack Router
- TanStack Query for API state
- `eventsource-parser` for SSE
- MediaPipe Hands `gesture_recognizer.task` loaded from CDN (`/approvals` only)

## API targets

- Harness REST: `localhost:8002` (`/chat` SSE, `/approvals*`)
- Memory: `localhost:8001` (`/brains`, `/brain/{id}/*`)

## Gesture port (Phase 1, slim)

- Mounted only on `/approvals` when webcam toggle is on.
- 320×240, 3 fps, 0.65 confidence, 3-frame confirm, 2000 ms cooldown.
- Mappings: 👍 → approve top pending; 👎 → deny top pending. All other 5 gestures Phase 4.

Status: **scaffolded — implement in Phase 1**.
