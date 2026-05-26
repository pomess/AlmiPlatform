/**
 * MediaPipe Hands gesture port — slim version.
 * Loads the gesture_recognizer.task from Google's CDN and runs it on a webcam stream
 * at low fps. Emits 👍 / 👎 callbacks after `confirmFrames` of agreement and a
 * `cooldownMs` debounce. Phase 1 only handles approve/deny; full set is Phase 4.
 *
 * Settings come from localStorage `kairos.gestureSettings`; defaults match the
 * de-warp defaults: 320×240, 3 fps, 0.65 confidence, 3-frame confirm, 2 s cooldown.
 */

import { useEffect, useRef } from "react";

const LS_GESTURE = "kairos.gestureSettings";

type Settings = {
  fps: number;
  confidence: number;
  confirmFrames: number;
  cooldownMs: number;
};

const DEFAULTS: Settings = { fps: 3, confidence: 0.65, confirmFrames: 3, cooldownMs: 2000 };

function loadSettings(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(LS_GESTURE) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

type Opts = {
  enabled: boolean;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onApprove: () => void;
  onDeny: () => void;
};

export function useGestureApprovals({ enabled, videoRef, onApprove, onDeny }: Opts) {
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!enabled) {
      stopRef.current?.();
      stopRef.current = null;
      return;
    }
    let cancelled = false;
    let recognizer: { recognizeForVideo: (v: HTMLVideoElement, ts: number) => unknown; close?: () => void } | null = null;
    let stream: MediaStream | null = null;
    let timer: number | null = null;

    const settings = loadSettings();
    const intervalMs = Math.max(50, Math.floor(1000 / settings.fps));

    let lastFireAt = 0;
    let streak: { name: string; count: number } = { name: "", count: 0 };

    (async () => {
      try {
        const tasks: any = await import(
          /* @vite-ignore */ "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs"
        );
        const filesetResolver = await tasks.FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm",
        );
        recognizer = await tasks.GestureRecognizer.createFromOptions(filesetResolver, {
          baseOptions: {
            modelAssetPath:
              "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
            delegate: "GPU",
          },
          numHands: 1,
          runningMode: "VIDEO",
        });

        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: 320, height: 240 },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        await video.play();

        timer = window.setInterval(() => {
          if (!recognizer || !video || video.readyState < 2) return;
          const ts = performance.now();
          const result = recognizer.recognizeForVideo(video, ts) as {
            gestures?: Array<Array<{ categoryName: string; score: number }>>;
          };
          const top = result?.gestures?.[0]?.[0];
          if (!top || top.score < settings.confidence) {
            streak = { name: "", count: 0 };
            return;
          }
          const name = top.categoryName;
          if (name !== "Thumb_Up" && name !== "Thumb_Down") {
            streak = { name: "", count: 0 };
            return;
          }
          if (streak.name === name) streak.count += 1;
          else streak = { name, count: 1 };

          if (streak.count >= settings.confirmFrames) {
            const now = performance.now();
            if (now - lastFireAt >= settings.cooldownMs) {
              lastFireAt = now;
              streak = { name: "", count: 0 };
              if (name === "Thumb_Up") onApprove();
              else onDeny();
            }
          }
        }, intervalMs);
      } catch (e) {
        console.warn("[gestures] failed to start", e);
      }
    })();

    stopRef.current = () => {
      cancelled = true;
      if (timer !== null) clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
      try {
        recognizer?.close?.();
      } catch {
        // ignore
      }
    };

    return () => {
      stopRef.current?.();
      stopRef.current = null;
    };
  }, [enabled, videoRef, onApprove, onDeny]);
}
