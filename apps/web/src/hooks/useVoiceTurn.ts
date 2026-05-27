import { useCallback, useEffect, useRef, useState } from "react";
import {
  openStreamingStt,
  postVoiceToolResult,
  voiceTurn,
  type StreamingSttSession,
  type VoiceTurnEvent,
  type VoiceTurnHandle,
} from "../lib/api";
import type { ToolActivity } from "./useStreamChat";

export type VoiceTurnStatus =
  | "idle"
  | "capturing"
  | "thinking"
  | "speaking"
  | "error";

type ToolResult = Record<string, unknown>;

export interface UseVoiceTurnOptions {
  /** Page surface, drives which page-scoped tools the agent has. */
  page?: string;
  /** Brain to scope the agent to (default = whatever the server picks). */
  brain?: string | null;
  /** Profile passed to the agent (default "chat"). */
  profile?: string;
  /** True while the user holds the PTT key. */
  pttActive: boolean;
  /** Optional thread_id; if omitted, persisted under `disease360.thread`. */
  threadId?: string | null;
  /**
   * Returns the user's current GPS fix at submit time, or null if no fix
   * is available. The hook reads this fresh on every turn, so the parent
   * can keep the value in a ref without causing the hook to re-bind.
   */
  getUserLocation?: () => { lat: number; lon: number } | null;
  /** Called for client-executed tool calls (e.g. `fly_to_location`). */
  onToolCall?: (
    name: string,
    args: Record<string, unknown>,
    id: string,
  ) => ToolResult | Promise<ToolResult>;
}

export interface UseVoiceTurnReturn {
  status: VoiceTurnStatus;
  error: string | null;
  micReady: boolean;
  capturing: boolean;
  threadId: string | null;
  /** Last user transcript returned by the server (for UI). */
  transcript: string | null;
  /** Streaming reply text accumulated in the current turn. */
  reply: string;
  /** Tool calls the agent made during the current turn. */
  toolActivity: ToolActivity[];
  /** Stop any in-flight playback / request. */
  cancel: () => void;
  /**
   * Submit a typed prompt through the same SSE pipeline as a voice turn
   * (no mic capture, no streaming-STT WebSocket -- just the server's
   * `transcript`-only path). When `silent` is true the agent's TTS audio
   * frames are dropped client-side; tokens / tool calls / replies still
   * flow normally.
   */
  submitText: (text: string, opts?: { silent?: boolean }) => Promise<void>;
}

const PLAYBACK_RATE = 24_000;
const CAPTURE_RATE = 16_000;
const WORKLET_URL = "/worklets/pcm-downsampler.js";
const THREAD_KEY = "disease360.thread";
// Mechanical playback speedup. We do this in the client (instead of
// asking Gemini for `[fast]` prosody) because the audio-tag approach
// makes the model act faster -- it raises pitch and adds urgency, which
// kills the smooth-baritone JARVIS feel. A flat playbackRate preserves
// vocal character and only nudges pitch up by ~1.3 semitones at 1.08,
// which is essentially imperceptible.
const PLAYBACK_SPEED = 1.08;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readSharedThreadId(): string | null {
  try {
    return (
      window.localStorage.getItem(THREAD_KEY) ||
      window.sessionStorage.getItem(THREAD_KEY)
    );
  } catch {
    return null;
  }
}

function writeSharedThreadId(id: string): void {
  try {
    window.localStorage.setItem(THREAD_KEY, id);
  } catch {
    /* ignore quota / privacy errors */
  }
}

function base64ToInt16(b64: string): Int16Array {
  const bin = atob(b64);
  const buf = new ArrayBuffer(bin.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i += 1) view[i] = bin.charCodeAt(i);
  return new Int16Array(buf);
}

function wavFromInt16Mono(samples: Int16Array, sampleRate: number): Blob {
  const dataSize = samples.byteLength;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) view.setUint8(offset + i, s.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataSize, true);
  new Int16Array(buffer, 44).set(samples);

  return new Blob([buffer], { type: "audio/wav" });
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useVoiceTurn(opts: UseVoiceTurnOptions): UseVoiceTurnReturn {
  const {
    page = "dashboard",
    brain,
    profile = "chat",
    pttActive,
    threadId: threadIdProp,
    onToolCall,
    getUserLocation,
  } = opts;

  const [status, setStatus] = useState<VoiceTurnStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [micReady, setMicReady] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([]);
  const [threadId, setThreadId] = useState<string | null>(
    threadIdProp ?? readSharedThreadId(),
  );

  // Capture pipeline (lives across turns).
  const streamRef = useRef<MediaStream | null>(null);
  const micCtxRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);

  // Per-turn state.
  const recordingRef = useRef<Int16Array[]>([]);
  const recordingBytesRef = useRef(0);
  const pttRef = useRef(pttActive);
  const turnIdRef = useRef<string | null>(null);
  const handleRef = useRef<VoiceTurnHandle | null>(null);

  // Streaming-STT session: opened at PTT-down, frames are forwarded to
  // it as the worklet produces them, transcript is awaited at PTT-up.
  // Remains null when the WebSocket failed to open or the server
  // disabled the path -- the legacy WAV-upload fallback then runs.
  const sttSessionRef = useRef<StreamingSttSession | null>(null);
  const sttFailedRef = useRef(false);

  // Playback pipeline (24 kHz PCM scheduled back-to-back).
  const playCtxRef = useRef<AudioContext | null>(null);
  const playEndRef = useRef(0);
  const playSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());

  // Latest callbacks/refs for handlers that should not re-bind every render.
  const onToolCallRef = useRef(onToolCall);
  onToolCallRef.current = onToolCall;
  const brainRef = useRef(brain);
  brainRef.current = brain;
  const pageRef = useRef(page);
  pageRef.current = page;
  const profileRef = useRef(profile);
  profileRef.current = profile;
  const threadIdRef = useRef(threadId);
  threadIdRef.current = threadId;
  const getUserLocationRef = useRef(getUserLocation);
  getUserLocationRef.current = getUserLocation;

  // Keep external thread-id prop in sync if the parent provides one.
  useEffect(() => {
    if (threadIdProp && threadIdProp !== threadIdRef.current) {
      threadIdRef.current = threadIdProp;
      setThreadId(threadIdProp);
    }
  }, [threadIdProp]);

  // -------------------------------------------------------------------------
  // Capture: initialize once, kept alive across turns.
  // -------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            channelCount: 1,
          },
          video: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;

        const ctx = new AudioContext();
        micCtxRef.current = ctx;
        await ctx.audioWorklet.addModule(WORKLET_URL);
        if (cancelled) return;

        const source = ctx.createMediaStreamSource(stream);
        sourceNodeRef.current = source;
        const node = new AudioWorkletNode(ctx, "pcm-downsampler");
        workletNodeRef.current = node;

        node.port.onmessage = (ev) => {
          const buf = ev.data as ArrayBuffer;
          if (!buf || !pttRef.current) return;
          const frame = new Int16Array(buf);
          recordingRef.current.push(frame);
          recordingBytesRef.current += frame.byteLength;
          // Mirror the same frame to the streaming STT session so most
          // of the audio is in Gemini Live by the time PTT releases.
          // Failures here are benign -- `submitTurn` will fall back to
          // the legacy multipart WAV path automatically.
          const session = sttSessionRef.current;
          if (session) {
            try {
              session.send(frame);
            } catch {
              sttFailedRef.current = true;
            }
          }
        };

        source.connect(node);
        if (cancelled) return;
        setMicReady(true);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      cancelled = true;
      try {
        workletNodeRef.current?.disconnect();
        sourceNodeRef.current?.disconnect();
      } catch {
        /* ignore */
      }
      workletNodeRef.current = null;
      sourceNodeRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      micCtxRef.current?.close().catch(() => {});
      micCtxRef.current = null;
      setMicReady(false);
    };
  }, []);

  // -------------------------------------------------------------------------
  // Playback helpers.
  // -------------------------------------------------------------------------

  const playPcm = useCallback((int16: Int16Array) => {
    if (int16.length === 0) return;
    let ctx = playCtxRef.current;
    if (!ctx) {
      ctx = new AudioContext({ sampleRate: PLAYBACK_RATE });
      playCtxRef.current = ctx;
      playEndRef.current = ctx.currentTime;
    }
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i += 1) {
      float32[i] = int16[i] < 0 ? int16[i] / 0x8000 : int16[i] / 0x7fff;
    }
    const audioBuffer = ctx.createBuffer(1, float32.length, PLAYBACK_RATE);
    audioBuffer.copyToChannel(float32, 0);
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.playbackRate.value = PLAYBACK_SPEED;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, playEndRef.current);
    source.start(startAt);
    // Wall-clock duration shrinks by PLAYBACK_SPEED, so the next chunk
    // must be scheduled where this one *actually* finishes.
    playEndRef.current = startAt + audioBuffer.duration / PLAYBACK_SPEED;
    playSourcesRef.current.add(source);
    setStatus("speaking");

    source.onended = () => {
      playSourcesRef.current.delete(source);
      const c = playCtxRef.current;
      if (!c) return;
      if (playEndRef.current - c.currentTime <= 0.02) {
        setStatus((prev) => (prev === "speaking" ? "idle" : prev));
      }
    };
  }, []);

  const stopPlayback = useCallback(() => {
    playSourcesRef.current.forEach((src) => {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
      src.disconnect();
    });
    playSourcesRef.current.clear();
    const ctx = playCtxRef.current;
    if (ctx) playEndRef.current = ctx.currentTime;
  }, []);

  // -------------------------------------------------------------------------
  // Submit a captured turn.
  // -------------------------------------------------------------------------

  const submitTurn = useCallback(async () => {
    const frames = recordingRef.current;
    recordingRef.current = [];
    recordingBytesRef.current = 0;
    const session = sttSessionRef.current;
    sttSessionRef.current = null;
    const sttFailed = sttFailedRef.current;
    sttFailedRef.current = false;

    if (frames.length === 0) {
      setStatus("idle");
      session?.cancel();
      return;
    }

    // Concat all Int16 frames into one.
    const totalSamples = frames.reduce((n, f) => n + f.length, 0);
    if (totalSamples < CAPTURE_RATE / 4) {
      // < 250 ms of audio -- almost certainly an accidental tap.
      setStatus("idle");
      session?.cancel();
      return;
    }
    const merged = new Int16Array(totalSamples);
    let off = 0;
    for (const f of frames) {
      merged.set(f, off);
      off += f.length;
    }

    setStatus("thinking");
    setReply("");
    setError(null);
    setTranscript(null);
    setToolActivity([]);
    stopPlayback();

    // If the streaming STT session is alive, finalise it and use the
    // returned transcript -- this skips the server-side `_stt_sync`
    // round-trip entirely. We distinguish three outcomes:
    //   - succeeded with text  -> send transcript only (no WAV upload)
    //   - succeeded with empty -> still skip server STT (audio was silence)
    //   - threw / WS dropped   -> fall back to legacy WAV-upload path
    let prefetchedTranscript: string | null = null;
    let sttOk = false;
    if (session && !sttFailed) {
      try {
        const raw = await session.end();
        prefetchedTranscript = raw.trim();
        sttOk = true;
      } catch (e) {
        console.warn("[voice] streaming STT failed, falling back", e);
      }
    } else {
      session?.cancel();
    }

    // When streaming STT succeeded we always send the transcript and
    // skip the WAV (server treats `transcript=""` as a confident empty
    // turn). Only fall back to the WAV-upload path on actual STT
    // failure.
    const wav = sttOk ? null : wavFromInt16Mono(merged, CAPTURE_RATE);
    if (sttOk && prefetchedTranscript) {
      // Surface the user's words in the UI as soon as we have them,
      // even before the agent's first token arrives.
      setTranscript(prefetchedTranscript);
    }

    const fix = getUserLocationRef.current?.() ?? null;
    const handle = voiceTurn(
      {
        audio: wav,
        // Pass the prefetched transcript only when streaming STT actually
        // succeeded -- including the empty-string case, which the server
        // recognises as "STT succeeded, heard nothing" and treats as an
        // empty turn (no agent invocation, instant `done`). When STT
        // failed we send `null` so the server falls back to its own STT
        // on the WAV blob.
        transcript: sttOk ? (prefetchedTranscript ?? "") : null,
        thread_id: threadIdRef.current,
        brain: brainRef.current ?? null,
        page: pageRef.current ?? "dashboard",
        profile: profileRef.current,
        user_lat: fix ? fix.lat : null,
        user_lng: fix ? fix.lon : null,
      },
      makeTurnEventHandler({ silent: false }),
    );
    handleRef.current = handle;
    try {
      await handle.done;
    } finally {
      if (handleRef.current === handle) handleRef.current = null;
    }
  }, [playPcm, stopPlayback]);

  // -------------------------------------------------------------------------
  // Shared SSE event handler used by both submitTurn (voice path) and
  // submitText (typed-prompt path). Closes over the hook's setState
  // helpers + refs; the only per-turn variable is `silent`, which gates
  // whether agent TTS audio frames are forwarded to the playback queue.
  // -------------------------------------------------------------------------

  function makeTurnEventHandler({
    silent,
  }: {
    silent: boolean;
  }): (evt: VoiceTurnEvent) => void {
    return (evt) => {
      switch (evt.type) {
        case "meta": {
          turnIdRef.current = evt.turn_id;
          if (evt.thread_id && evt.thread_id !== threadIdRef.current) {
            threadIdRef.current = evt.thread_id;
            setThreadId(evt.thread_id);
            writeSharedThreadId(evt.thread_id);
          }
          break;
        }
        case "transcript":
          setTranscript(evt.text);
          break;
        case "tool":
          setToolActivity((prev) => [
            ...prev,
            {
              name: evt.name,
              args: evt.args,
              startedAt: Date.now(),
              toolCallId: evt.tool_call_id,
            },
          ]);
          break;
        case "tool_done":
          setToolActivity((prev) =>
            prev.map((t) =>
              t.toolCallId === evt.tool_call_id && t.finishedAt == null
                ? { ...t, finishedAt: Date.now() }
                : t,
            ),
          );
          break;
        case "token":
          setReply((r) => r + evt.text);
          break;
        case "audio":
          // Server always emits TTS frames; the typed-prompt path opts
          // out of playback by passing silent=true so we just drop the
          // base64 PCM here.
          if (!silent) playPcm(base64ToInt16(evt.b64));
          break;
        case "tool_call": {
          const turnId = turnIdRef.current;
          if (!turnId) break;
          const handler = onToolCallRef.current;
          (async () => {
            let result: ToolResult = { ok: false, error: "no handler" };
            if (handler) {
              try {
                const maybe = await handler(evt.name, evt.args, evt.id);
                result = maybe ?? { ok: true };
              } catch (e) {
                result = { ok: false, error: String(e) };
              }
            }
            try {
              await postVoiceToolResult(turnId, evt.id, result);
            } catch (e) {
              console.warn("[voice] tool_result POST failed", e);
            }
          })();
          break;
        }
        case "done":
          if (evt.thread_id && evt.thread_id !== threadIdRef.current) {
            threadIdRef.current = evt.thread_id;
            setThreadId(evt.thread_id);
            writeSharedThreadId(evt.thread_id);
          }
          // If nothing is currently being spoken, transition back to idle.
          setStatus((prev) => (prev === "speaking" ? prev : "idle"));
          break;
        case "error":
          setError(evt.message);
          setStatus("error");
          break;
        default:
          break;
      }
    };
  }

  // -------------------------------------------------------------------------
  // Submit a typed prompt. Same SSE pipeline as voice -- skips mic capture
  // and streaming STT entirely; the server treats `transcript=...` with no
  // audio blob as a confident text-only turn. `silent: true` mutes TTS
  // playback client-side so dev iteration in the dashboard composer
  // doesn't have to listen to the agent talk.
  // -------------------------------------------------------------------------

  const submitText = useCallback(
    async (text: string, opts?: { silent?: boolean }) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      // Don't fire on top of an in-flight turn; the caller's UI should
      // be disabling the submit affordance while `status` is non-idle,
      // but be defensive.
      if (handleRef.current) return;

      setStatus("thinking");
      setReply("");
      setError(null);
      setTranscript(trimmed);
      setToolActivity([]);
      stopPlayback();

      const fix = getUserLocationRef.current?.() ?? null;
      const silent = opts?.silent === true;
      const handle = voiceTurn(
        {
          audio: null,
          transcript: trimmed,
          thread_id: threadIdRef.current,
          brain: brainRef.current ?? null,
          page: pageRef.current ?? "dashboard",
          profile: profileRef.current,
          user_lat: fix ? fix.lat : null,
          user_lng: fix ? fix.lon : null,
        },
        makeTurnEventHandler({ silent }),
      );
      handleRef.current = handle;
      try {
        await handle.done;
      } finally {
        if (handleRef.current === handle) handleRef.current = null;
      }
    },
    // makeTurnEventHandler is a closure over stable refs + setStates, so
    // we depend only on the playback helpers it uses.
    [playPcm, stopPlayback],
  );

  // -------------------------------------------------------------------------
  // PTT edge: false -> true means start capturing; true -> false means
  // submit the captured audio.
  // -------------------------------------------------------------------------

  useEffect(() => {
    const wasActive = pttRef.current;
    pttRef.current = pttActive;

    if (!micReady) {
      // The user pressed Space before the mic was ready; ignore. They
      // need to release and try again. We don't try to backfill — the
      // worklet's port.onmessage gates on pttRef which is now true, so
      // any future frames _will_ be captured.
      return;
    }

    if (pttActive && !wasActive) {
      // Start of a press: clear any leftover frames + stop ongoing audio.
      recordingRef.current = [];
      recordingBytesRef.current = 0;
      stopPlayback();
      handleRef.current?.cancel();
      setStatus("capturing");
      setReply("");
      setError(null);
      setTranscript(null);
      setToolActivity([]);
      // Kick off the streaming-STT WebSocket the instant PTT engages so
      // the audio frames the worklet emits over the next few hundred ms
      // start uploading immediately. If the socket fails to open we
      // mark the session as failed and `submitTurn` will silently fall
      // back to the multipart WAV path.
      sttFailedRef.current = false;
      try {
        const session = openStreamingStt();
        sttSessionRef.current = session;
        session.ready.catch(() => {
          sttFailedRef.current = true;
        });
      } catch (e) {
        console.warn("[voice] could not open streaming-STT session", e);
        sttSessionRef.current = null;
        sttFailedRef.current = true;
      }
    } else if (!pttActive && wasActive) {
      void submitTurn();
    }
  }, [pttActive, micReady, stopPlayback, submitTurn]);

  // Cleanup on unmount: cancel any running turn + stop playback.
  useEffect(() => {
    return () => {
      handleRef.current?.cancel();
      sttSessionRef.current?.cancel();
      sttSessionRef.current = null;
      stopPlayback();
      playCtxRef.current?.close().catch(() => {});
      playCtxRef.current = null;
    };
  }, [stopPlayback]);

  const cancel = useCallback(() => {
    handleRef.current?.cancel();
    handleRef.current = null;
    recordingRef.current = [];
    recordingBytesRef.current = 0;
    sttSessionRef.current?.cancel();
    sttSessionRef.current = null;
    sttFailedRef.current = false;
    stopPlayback();
    setStatus("idle");
  }, [stopPlayback]);

  return {
    status,
    error,
    micReady,
    capturing: status === "capturing",
    threadId,
    transcript,
    reply,
    toolActivity,
    cancel,
    submitText,
  };
}
