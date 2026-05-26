# Perception service

Voice + camera (gesture) input → events into the harness.

Inspired by `de-warp` and, for **gestures specifically, a clean rebuild of the same architecture** with JARVIS-specific actions. See [docs/10-gestures-de-warp.md](../../docs/10-gestures-de-warp.md) for the full breakdown.

## Voice (clean from scratch)

- **Wake word** — `openWakeWord` or a small custom-trained one.
- **STT** — `faster-whisper` local; cloud fallback (Deepgram) optional.
- **TTS** — `Piper` local; cloud fallback optional.
- **Barge-in** — VAD-based interruption of the LLM stream.

## Gestures (port the de-warp pipeline, retarget actions)

Stack:
- `@mediapipe/tasks-vision` in the **browser** (WASM, GPU→CPU fallback).
- `gesture_recognizer.task` model from Google's CDN.
- 320×240 webcam capture, 3 fps, 0.65 confidence, 3-frame debounce, 2000 ms cooldown — all kept verbatim from de-warp.
- localStorage-backed user mapping (`jarvis_gesture_config`).

Action set (initial, user-remappable):

| Gesture | JARVIS action |
|---|---|
| 👍 Thumb_Up | `approve_pending` |
| 👎 Thumb_Down | `deny_pending` |
| ✊ Closed_Fist | `stop_speaking` |
| 🖐 Open_Palm | `push_to_talk_toggle` |
| ✌️ Victory | `snapshot_to_brain` |
| ☝️ Pointing_Up | `read_morning_digest` |
| 🤟 ILoveYou | `none` |

The recognition lives entirely in the **web channel** ([../channels/web/](../channels/web/README.md)). This service holds the **voice** pipeline plus shared types and event contracts; gesture frames never leave the browser.

## Non-goals (Phase 3)

- Custom-trained gesture models, two-handed gestures, full body pose, server-side recognition. All deferred.
- Face recognition, emotion analysis, scene understanding.

## Status

**Not yet scaffolded.** Voice is Phase 3; gesture porting can land earlier in Phase 1 alongside the Approvals panel — see [docs/07-roadmap.md](../../docs/07-roadmap.md).
