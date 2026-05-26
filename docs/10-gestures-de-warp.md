# How de-warp does gestures (and how JARVIS will)

> Source: `c:/Users/Bruno/Desktop/dewarp/de-warp/webapp/frontend/src` — files [useGestureRecognition.ts](../../dewarp/de-warp/webapp/frontend/src/hooks/useGestureRecognition.ts), [useGestureConfig.ts](../../dewarp/de-warp/webapp/frontend/src/hooks/useGestureConfig.ts), [GestureCamera.tsx](../../dewarp/de-warp/webapp/frontend/src/components/GestureCamera.tsx), [GestureSettingsPanel.tsx](../../dewarp/de-warp/webapp/frontend/src/components/GestureSettingsPanel.tsx).
>
> Per locked decisions (see [09-locked-decisions.md](09-locked-decisions.md)): rebuild this clean for JARVIS, but **same architecture, same UX**.

---

## What de-warp does (in one paragraph)

A small webcam picture-in-picture in the corner of the page. MediaPipe's hand-gesture recognizer runs in the **browser** (WASM, GPU-delegated when possible). Each detected gesture is mapped — by the user, persisted in localStorage — to a **named action** in the host app (start recording, capture snapshot, etc.). A tiny gear opens a dropdown panel where the user re-assigns gestures to actions on the fly.

It's all client-side. The backend never sees a video frame.

---

## Stack

| Layer | What | Notes |
|---|---|---|
| Model | `gesture_recognizer.task` from Google's `mediapipe-models` CDN | Pre-trained, 7 gestures + None |
| Runtime | `@mediapipe/tasks-vision` (npm) | WASM bundle from jsdelivr CDN, GPU delegate with CPU fallback |
| Camera | `navigator.mediaDevices.getUserMedia` 320×240 @ user-facing | Tiny stream → cheap inference |
| UI | React hook + PiP video + canvas overlay drawing landmarks | Draws hand skeleton in real time |
| Config | `useGestureConfig` + `localStorage` (`vagent_gesture_config`) | Per-user mapping persists |

## The 7 gestures

Built into the MediaPipe model — JARVIS can't add new ones without training a new model.

| Gesture | Display |
|---|---|
| `Thumb_Up` | 👍 Thumb Up |
| `Thumb_Down` | 👎 Thumb Down |
| `Open_Palm` | 🖐 Open Palm |
| `Closed_Fist` | ✊ Closed Fist |
| `Pointing_Up` | ☝️ Pointing Up |
| `Victory` | ✌️ Victory |
| `ILoveYou` | 🤟 I Love You |

## Detection pipeline

```
camera @ 320×240
    │
    ▼
MediaPipe GestureRecognizer.recognizeForVideo()  (≈3 fps target)
    │
    ▼
Top-1 gesture + confidence score
    │
    ▼
Filter: confidence ≥ 0.65
    │
    ▼
Debounce: same gesture must repeat for N consecutive frames
    │   (de-warp: confirmFrames=3 inside GestureCamera, 5 default)
    ▼
Cooldown: 2000 ms per-gesture (a fired gesture can't fire again for 2s)
    │
    ▼
Emit GestureEvent { gesture, confidence, timestamp }
    │
    ▼
Host app maps gesture → action via user config
```

The whole loop runs on a `setTimeout` chain (not `requestAnimationFrame`) so the FPS target is honored even when the tab is busy.

## Action set in de-warp

These are domain-specific to a voice/recording app — JARVIS will define its own:

```
start_recording   ⏺   begin audio recording
stop_recording    💾   stop and save
cancel_recording  ✕    discard
toggle_mic        🎙   mute / unmute
ai_snapshot       📷   capture a frame, send to LLM, ask "what do you see?"
speak_ai_news     📰   prompt: "read me today's AI news"
clear_flashcards  🧹   clear UI cards
none              —    do nothing
```

The default mapping (de-warp):

| Gesture | Action |
|---|---|
| 👍 Thumb_Up | start_recording |
| ✊ Closed_Fist | stop_recording |
| 👎 Thumb_Down | cancel_recording |
| 🖐 Open_Palm | clear_flashcards |
| ☝️ Pointing_Up | none |
| ✌️ Victory | speak_ai_news |
| 🤟 ILoveYou | ai_snapshot |

## Snapshot pattern (worth copying as-is)

`captureSnapshot()` in `GestureCamera.tsx` does:

1. Read current `<video>` element.
2. Draw to a hidden canvas at the video's native size.
3. `canvas.toBlob` → `FileReader` → base64.
4. Send the base64 to the LLM channel.
5. **120 ms later**, send a follow-up text "I just shared my camera with you. What do you see?" so the multimodal model knows it's expected to respond.

This is the *gesture → vision LLM* bridge. Reusable verbatim.

## UX details that matter

- **PiP layout**: small video, overlay canvas drawing hand skeleton in lavender, label strip showing the action that *would* fire if the current gesture confirms.
- **Legend strip**: under the video, a row of emoji for the configured gestures. Hidden if the user mapped one to `none`.
- **Settings gear**: opens a dropdown panel (rendered via `createPortal` to `document.body`) listing each configurable gesture with an action dropdown. Saves to localStorage on every change. "Reset to defaults" button.
- **Snapshot flash**: 400 ms white flash overlay on the video when `ai_snapshot` fires (cheap dopamine hit so the user knows it worked).
- **Errors**: camera permission denied → friendly message in the PiP. WebGL/WASM init failures → swallowed, falls back from GPU to CPU automatically.

---

## What changes for JARVIS

**Same architecture.** Different action set. Different host app integration.

### JARVIS action set (proposed)

| Gesture | JARVIS action | Notes |
|---|---|---|
| 👍 Thumb_Up | `approve_pending` | Approve the topmost pending tool-call request |
| 👎 Thumb_Down | `deny_pending` | Deny it |
| ✊ Closed_Fist | `stop_speaking` | Interrupt JARVIS mid-TTS |
| 🖐 Open_Palm | `push_to_talk_toggle` | Hold-open mic alternative for PTT users |
| ✌️ Victory | `snapshot_to_brain` | Take camera frame, ingest as a wiki page in active brain |
| ☝️ Pointing_Up | `read_morning_digest` | Or any "favorite" command |
| 🤟 ILoveYou | `none` | User-configurable like all the others |

All of these stay user-remappable via the same settings panel pattern.

### Host integration changes

- The PiP lives inside the JARVIS web channel ([services/channels/web/](../services/channels/web/README.md)).
- `onSendWsText` / `onSendImage` get replaced by the JARVIS chat API (FastAPI `/api/chat` SSE endpoint, already in the existing project).
- Approval gestures (`approve_pending` / `deny_pending`) talk to the harness's approval queue, not the chat API.
- localStorage key renamed: `vagent_gesture_config` → `jarvis_gesture_config`.

### What we deliberately keep identical

- 320×240 capture, 3 fps target, 0.65 confidence floor, 3-frame confirm, 2000 ms cooldown.
- WASM CDN + model URL.
- GPU-then-CPU delegate fallback.
- localStorage persistence.
- Settings gear + portal-rendered dropdown.
- Snapshot flash + 120 ms follow-up text.

These are all numbers that have been tuned by use. Don't relitigate them in v0.

### Build order

1. Phase 1 (early): port the recognition hook and PiP component into the web channel; map only `approve_pending` / `deny_pending` initially. That alone makes the Approvals panel feel magic.
2. Phase 2: wire `read_morning_digest` and `snapshot_to_brain`.
3. Phase 3: full action set + voice integration so `stop_speaking` and `push_to_talk_toggle` matter.

---

## Out of scope (for now)

- Custom-trained model (would let us add new gestures like a "scroll" sweep). Real, but a research project on its own.
- Two-handed gestures. MediaPipe supports `numHands: 2`; de-warp uses 1, JARVIS will start with 1.
- Pose / body gestures. Different model (`pose_landmarker.task`), different cost. Not needed.
- Server-side recognition. Would let phones with no client do it, but burns bandwidth and adds latency. Skip.
