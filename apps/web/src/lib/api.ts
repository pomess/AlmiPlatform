// Tiny API clients. Vite proxy maps /api/harness -> :8002 and /api/memory -> :8001.

// Default tenant for local dev. Auth will swap this for the signed-in tenant id.
const DEFAULT_TENANT = "local";
const LS_TENANT = "kairos.activeTenant";

export function getActiveTenant(): string {
  return localStorage.getItem(LS_TENANT) || DEFAULT_TENANT;
}
export function setActiveTenant(t: string) {
  localStorage.setItem(LS_TENANT, t);
}

function memBrain(brain: string, suffix = ""): string {
  return `/api/memory/tenant/${encodeURIComponent(getActiveTenant())}/brain/${encodeURIComponent(brain)}${suffix}`;
}
function memTenant(suffix = ""): string {
  return `/api/memory/tenant/${encodeURIComponent(getActiveTenant())}${suffix}`;
}

export type ChatResponse = {
  thread_id: string;
  final_text: string;
  raw_messages: { role: string; content: string }[];
};

export type Brain = { id: string; title: string; page_count: number; has_hot: boolean };

// --- Daily news briefing --------------------------------------------------

export type NewsItem = { title: string; link: string; published: string };
export type NewsSource = { source: string; items: NewsItem[]; error?: string };
export type NewsVideo = {
  source: string;
  video_id: string;
  title: string;
  link: string;
  published: string;
  thumbnail: string;
  channel_icon?: string;
};
export type NewsBriefing = {
  fetched_at: string;
  pharma: NewsSource[];
  derm: NewsSource[];
  competitors: NewsSource[];
  video: NewsVideo | null;
};

export async function fetchDailyNews(force = false): Promise<NewsBriefing> {
  return jget<NewsBriefing>(`/api/harness/news${force ? "?force=1" : ""}`);
}

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  // harness
  chat: (req: { message: string; brain: string; thread_id?: string | null; profile?: string }) =>
    jpost<ChatResponse>("/api/harness/chat", { tenant_id: getActiveTenant(), ...req }),
  chatStream,
  // memory
  brains: () => jget<Brain[]>(memTenant("/brains")),
  index: (brain: string) =>
    jget<{ path: string; body: string }>(memBrain(brain, "/index")),
  hot: (brain: string) =>
    jget<{ path: string; body: string }>(memBrain(brain, "/hot")),
  page: (brain: string, path: string) =>
    jget<{ path: string; title: string; frontmatter: Record<string, unknown>; body: string }>(
      `${memBrain(brain, "/page")}?path=${encodeURIComponent(path)}`,
    ),
  graph: (brain: string) =>
    jget<{
      nodes: { id: string; title: string; layer: string }[];
      edges: { source: string; target: string }[];
    }>(memBrain(brain, "/graph")),
};

// --- streaming chat -------------------------------------------------------

export type ChatStreamEvent =
  | { type: "meta"; thread_id: string }
  | { type: "tool"; name: string; args: Record<string, unknown>; tool_call_id?: string }
  | { type: "tool_done"; name: string; tool_call_id: string }
  | {
      type: "tool_progress";
      name: string;
      message: string;
      stage: string;
      detail?: {
        query?: string;
        queries_run?: string[];
        urls?: string[];
        titles?: string[];
        result_count?: number;
        url?: string;
        ok?: boolean;
        bytes?: number;
        cached?: boolean;
        [k: string]: unknown;
      };
    }
  | { type: "token"; text: string }
  | { type: "done"; thread_id: string }
  | { type: "error"; message: string };

export interface ChatStreamHandle {
  cancel: () => void;
  done: Promise<void>;
}

function chatStream(
  req: { message: string; brain: string; thread_id?: string | null; profile?: string; use_research?: boolean },
  onEvent: (e: ChatStreamEvent) => void,
): ChatStreamHandle {
  const controller = new AbortController();

  const done = (async () => {
    let res: Response;
    try {
      res = await fetch("/api/harness/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: getActiveTenant(), ...req }),
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      onEvent({ type: "error", message: (err as Error).message });
      return;
    }

    if (!res.ok || !res.body) {
      onEvent({ type: "error", message: `${res.status} ${res.statusText}` });
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buf += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          // A frame can hold multiple `data:` lines — concatenate them.
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
          }
          if (dataLines.length === 0) continue;
          try {
            const evt = JSON.parse(dataLines.join("\n")) as ChatStreamEvent;
            console.debug("[chat-stream]", evt);
            onEvent(evt);
          } catch {
            // ignore malformed frame
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", message: (err as Error).message });
      }
    }
  })();

  return { cancel: () => controller.abort(), done };
}

// --- streaming voice turn -------------------------------------------------

export type VoiceTurnEvent =
  | { type: "meta"; thread_id: string; turn_id: string; brain: string; page: string | null }
  | { type: "transcript"; text: string }
  | { type: "tool"; name: string; args: Record<string, unknown>; tool_call_id?: string }
  | { type: "tool_done"; name: string; tool_call_id: string }
  | { type: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { type: "token"; text: string }
  | { type: "audio"; b64: string; seq: number; rate: number }
  | { type: "done"; thread_id: string; empty?: boolean }
  | { type: "error"; message: string };

export interface VoiceTurnHandle {
  cancel: () => void;
  done: Promise<void>;
}

export interface VoiceTurnRequest {
  /**
   * The captured WAV blob. Optional only when `transcript` is set
   * (streaming-STT path) — in that case the server skips its own STT
   * and uses the provided transcript directly, so audio isn't needed.
   */
  audio?: Blob | null;
  /**
   * Pre-computed transcript from the streaming STT WebSocket. When set,
   * the server bypasses `_stt_sync` (saving ~600-1500 ms per turn).
   */
  transcript?: string | null;
  thread_id?: string | null;
  brain?: string | null;
  page?: string | null;
  profile?: string;
  /** Browser GPS fix forwarded to the agent for implicit-origin routing. */
  user_lat?: number | null;
  user_lng?: number | null;
}

function voiceTurn(
  req: VoiceTurnRequest,
  onEvent: (e: VoiceTurnEvent) => void,
): VoiceTurnHandle {
  const controller = new AbortController();

  const fd = new FormData();
  if (req.audio) fd.append("audio", req.audio, "turn.wav");
  // Send the transcript field even when empty: an explicit empty string
  // means "streaming STT succeeded but heard nothing" and the server
  // should treat it as a finished empty turn rather than re-running STT.
  if (req.transcript != null) {
    fd.append("transcript", req.transcript);
  }
  if (req.thread_id) fd.append("thread_id", req.thread_id);
  if (req.brain) fd.append("brain", req.brain);
  fd.append("tenant_id", getActiveTenant());
  if (req.page) fd.append("page", req.page);
  if (req.profile) fd.append("profile", req.profile);
  if (req.user_lat != null && Number.isFinite(req.user_lat)) {
    fd.append("user_lat", String(req.user_lat));
  }
  if (req.user_lng != null && Number.isFinite(req.user_lng)) {
    fd.append("user_lng", String(req.user_lng));
  }

  const done = (async () => {
    let res: Response;
    try {
      res = await fetch("/api/harness/voice/turn", {
        method: "POST",
        body: fd,
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      onEvent({ type: "error", message: (err as Error).message });
      return;
    }

    if (!res.ok || !res.body) {
      onEvent({ type: "error", message: `${res.status} ${res.statusText}` });
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    try {
      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buf += decoder.decode(value, { stream: true });

        let idx: number;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const dataLines: string[] = [];
          for (const line of frame.split("\n")) {
            if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
          }
          if (dataLines.length === 0) continue;
          try {
            const evt = JSON.parse(dataLines.join("\n")) as VoiceTurnEvent;
            onEvent(evt);
          } catch {
            // ignore malformed frame
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", message: (err as Error).message });
      }
    }
  })();

  return { cancel: () => controller.abort(), done };
}

export async function postVoiceToolResult(
  turnId: string,
  callId: string,
  result: Record<string, unknown>,
): Promise<{ ok: boolean }> {
  return jpost<{ ok: boolean }>(
    `/api/harness/voice/turn/${encodeURIComponent(turnId)}/tool_result`,
    { call_id: callId, result },
  );
}

// --- streaming STT (Gemini Live, WebSocket) -------------------------------
//
// The browser opens this socket at PTT-down and forwards 16 kHz Int16
// PCM frames as the worklet emits them. On PTT-up it calls `end()` to
// flush `audio_stream_end` to the server, then awaits the final
// transcript. Failure modes (WS reject, network drop, server flag off)
// short-circuit the promise so the caller can fall back to the legacy
// multipart `voiceTurn({ audio: ... })` path.

export interface StreamingSttSession {
  /** Push a Int16 PCM frame at 16 kHz. */
  send(frame: Int16Array): void;
  /** Signal end of audio. Resolves to the final transcript. */
  end(): Promise<string>;
  /** Hard-cancel the WebSocket. */
  cancel(): void;
  /** Resolves to true once the server has accepted the connection. */
  ready: Promise<void>;
}

export function openStreamingStt(): StreamingSttSession {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/api/harness/voice/stream/stt`;

  let resolveReady!: () => void;
  let rejectReady!: (e: Error) => void;
  const ready = new Promise<void>((res, rej) => {
    resolveReady = res;
    rejectReady = rej;
  });

  let resolveTranscript!: (text: string) => void;
  let rejectTranscript!: (e: Error) => void;
  const transcriptPromise = new Promise<string>((res, rej) => {
    resolveTranscript = res;
    rejectTranscript = rej;
  });

  let ws: WebSocket;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    const e = err instanceof Error ? err : new Error(String(err));
    rejectReady(e);
    rejectTranscript(e);
    return {
      send: () => {},
      end: () => transcriptPromise,
      cancel: () => {},
      ready,
    };
  }
  ws.binaryType = "arraybuffer";

  let lastTranscript = "";
  let closed = false;
  // Frames produced by the worklet during the WebSocket's CONNECTING
  // window (~50-200 ms of TLS handshake) would otherwise be dropped.
  // We buffer them and flush in `onopen` so the streaming-STT pipeline
  // sees the whole utterance, not just the tail.
  const pendingFrames: ArrayBuffer[] = [];

  ws.onopen = () => {
    for (const buf of pendingFrames) {
      try {
        ws.send(buf);
      } catch {
        /* ignore -- onclose will fire and resolve with what we have */
      }
    }
    pendingFrames.length = 0;
    resolveReady();
  };
  ws.onerror = () => {
    const e = new Error("streaming-STT WebSocket error");
    rejectReady(e);
    rejectTranscript(e);
  };
  ws.onclose = () => {
    closed = true;
    // If the socket closed before we ever got a final_transcript event,
    // fall back to whatever partials we collected.
    resolveTranscript(lastTranscript);
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(typeof ev.data === "string" ? ev.data : "");
      if (msg.type === "partial_transcript" && typeof msg.text === "string") {
        lastTranscript += msg.text;
      } else if (msg.type === "final_transcript" && typeof msg.text === "string") {
        // The server's `final_transcript` is the authoritative
        // concatenation, not an additional chunk -- replace whatever
        // partials we accumulated.
        lastTranscript = msg.text;
        resolveTranscript(msg.text);
      } else if (msg.type === "error") {
        rejectTranscript(new Error(String(msg.message || "STT stream error")));
      }
    } catch {
      // ignore non-JSON frames (shouldn't happen)
    }
  };

  return {
    send(frame: Int16Array): void {
      if (closed) return;
      // Copy into a fresh ArrayBuffer so we always send a stable,
      // owned, non-shared byte range. Int16Array views can sit on top
      // of SharedArrayBuffer in some workers, which `WebSocket.send`
      // does not accept.
      const buf = new ArrayBuffer(frame.byteLength);
      new Uint8Array(buf).set(
        new Uint8Array(frame.buffer, frame.byteOffset, frame.byteLength),
      );
      if (ws.readyState === WebSocket.CONNECTING) {
        pendingFrames.push(buf);
        return;
      }
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(buf);
    },
    end(): Promise<string> {
      if (closed) return transcriptPromise;
      // If we haven't even finished connecting yet, wait for `ready`
      // (and thus the buffered-frame flush) before sending `end`. This
      // prevents the server from receiving an audio_stream_end before
      // any audio.
      if (ws.readyState === WebSocket.CONNECTING) {
        ready
          .then(() => {
            try {
              if (!closed && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "end" }));
              }
            } catch {
              /* the close handler will resolve with whatever we have */
            }
          })
          .catch(() => {
            /* ready already rejected -- transcriptPromise is rejected too */
          });
        return transcriptPromise;
      }
      if (ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ type: "end" }));
        } catch {
          /* ignore */
        }
      }
      return transcriptPromise;
    },
    cancel(): void {
      try {
        ws.close();
      } catch {
        /* already closed */
      }
    },
    ready,
  };
}

export { voiceTurn };

// Shape adapter for the imported GraphView component (which expects {label,type}).
export async function fetchGraph(brain: string): Promise<{
  nodes: { id: string; label: string; type: string }[];
  edges: { source: string; target: string }[];
}> {
  const g = await api.graph(brain);
  return {
    nodes: g.nodes.map((n) => ({ id: n.id, label: n.title, type: n.layer })),
    edges: g.edges,
  };
}

const LS_BRAIN = "kairos.activeBrain";
export function getActiveBrain(): string {
  const legacy = localStorage.getItem("jarvis.activeBrain");
  if (legacy && !localStorage.getItem(LS_BRAIN)) {
    localStorage.setItem(LS_BRAIN, legacy);
    localStorage.removeItem("jarvis.activeBrain");
  }
  return localStorage.getItem(LS_BRAIN) || "Bruno's Brain";
}
export function setActiveBrain(b: string) {
  localStorage.setItem(LS_BRAIN, b);
}
