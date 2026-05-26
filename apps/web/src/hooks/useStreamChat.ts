import { useState, useCallback, useRef, useEffect } from "react";
import { api, type ChatStreamHandle } from "../lib/api";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ResearchStep {
  stage: string;        // "search" | "fetch" | "classifier" | ...
  message: string;
  query?: string;
  urls?: string[];
  titles?: string[];
  url?: string;         // for fetch stage
  ok?: boolean;
  cached?: boolean;
  at: number;
}

export interface ToolActivity {
  name: string;
  args: Record<string, unknown>;
  startedAt: number;
  toolCallId?: string;
  finishedAt?: number;
  progressMessage?: string;
  /** Most recent research-pipeline steps (newest last). Capped at 30. */
  steps?: ResearchStep[];
}

// Shared with the voice hook so a thread started by speaking on the
// dashboard continues when the user types on the chat page (and vice
// versa).
const THREAD_KEY = "kairos.thread";

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

/**
 * Streaming chat hook.
 *
 * The harness emits real model tokens over SSE, but providers like Gemini
 * batch them into chunks of 30–100+ characters. We feed those chunks into a
 * `pendingRef` buffer and drain it from a `requestAnimationFrame` loop, so
 * the visible message grows smoothly character-by-character with the speed
 * scaled to the backlog (faster the more text is queued, never slower than
 * 1 char/frame).
 */
export function useStreamChat(brain?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([]);
  const initialThread = readSharedThreadId();
  const [threadId, setThreadId] = useState<string | null>(initialThread);
  const threadRef = useRef<string | null>(initialThread);
  const handleRef = useRef<ChatStreamHandle | null>(null);

  const pendingRef = useRef("");      // chars not yet committed to state
  const rafRef = useRef<number | null>(null);
  const finishedRef = useRef(false);   // server said "done" — drain then stop

  const stopRaf = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    rafRef.current = null;
    const queued = pendingRef.current;
    if (queued.length === 0) {
      if (finishedRef.current) {
        setIsStreaming(false);
        return;
      }
      // wait for more tokens — restart on next paint
      rafRef.current = requestAnimationFrame(tick);
      return;
    }

    // Reveal a slice this frame. Speed scales gently with backlog so a big
    // batch doesn't sit there for ages, but small dribbles still type out.
    const reveal = Math.max(1, Math.min(queued.length, Math.ceil(queued.length / 6)));
    const slice = queued.slice(0, reveal);
    pendingRef.current = queued.slice(reveal);

    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.role !== "assistant") return prev;
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + slice };
      return updated;
    });

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const startRaf = useCallback(() => {
    if (rafRef.current == null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [tick]);

  useEffect(() => () => {
    handleRef.current?.cancel();
    stopRaf();
  }, [stopRaf]);

  const sendMessage = useCallback(
    (text: string, opts?: { useResearch?: boolean }) => {
      handleRef.current?.cancel();
      stopRaf();
      pendingRef.current = "";
      finishedRef.current = false;
      setToolActivity([]);

      const userMsg: ChatMessage = { role: "user", content: text };
      const assistantMsg: ChatMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      // Track the cumulative text the server has produced so we can compute
      // the *new* slice on each event. Some providers may send overlapping
      // chunks; we treat tokens as deltas but normalise via length check.
      let serverTotal = "";

      const handle = api.chatStream(
        {
          message: text,
          brain: brain || "",
          thread_id: opts?.useResearch ? null : threadRef.current,
          use_research: opts?.useResearch || false,
        },
        (evt) => {
          switch (evt.type) {
            case "meta":
              threadRef.current = evt.thread_id;
              setThreadId(evt.thread_id);
              writeSharedThreadId(evt.thread_id);
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
            case "tool_progress":
              setToolActivity((prev) =>
                prev.map((t) => {
                  if (t.name !== evt.name || t.finishedAt != null) return t;
                  const detail = evt.detail || {};
                  const stage = evt.stage || "";
                  // Only append a step entry for real per-action stages.
                  // Pipeline-level stages (start/classifier/brief/...) only
                  // update the progressMessage so the bottom status line
                  // shows the active phase.
                  const isStep = stage === "search" || stage === "fetch";
                  if (!isStep) {
                    return { ...t, progressMessage: evt.message };
                  }
                  const step: ResearchStep = {
                    stage,
                    message: evt.message,
                    query:
                      typeof detail.query === "string"
                        ? detail.query
                        : undefined,
                    urls: Array.isArray(detail.urls)
                      ? (detail.urls as string[])
                      : undefined,
                    titles: Array.isArray(detail.titles)
                      ? (detail.titles as string[])
                      : undefined,
                    url:
                      typeof detail.url === "string" ? detail.url : undefined,
                    ok:
                      typeof detail.ok === "boolean" ? detail.ok : undefined,
                    cached:
                      typeof detail.cached === "boolean"
                        ? detail.cached
                        : undefined,
                    at: Date.now(),
                  };
                  const nextSteps = [...(t.steps || []), step].slice(-30);
                  return {
                    ...t,
                    progressMessage: evt.message,
                    steps: nextSteps,
                  };
                }),
              );
              break;
            case "token": {
              const delta = evt.text;
              if (!delta) break;
              serverTotal += delta;
              pendingRef.current += delta;
              startRaf();
              break;
            }
            case "done":
              threadRef.current = evt.thread_id;
              setThreadId(evt.thread_id);
              writeSharedThreadId(evt.thread_id);
              if (evt.interrupted) {
                const n = evt.approvals.length;
                pendingRef.current +=
                  (serverTotal && !serverTotal.endsWith("\n") ? "\n\n" : "") +
                  `⏸ paused — ${n} approval${n === 1 ? "" : "s"} pending. Open the Approvals page.`;
              }
              finishedRef.current = true;
              startRaf();
              break;
            case "error":
              pendingRef.current += `\n\n⚠ ${evt.message}`;
              finishedRef.current = true;
              startRaf();
              break;
          }
        },
      );
      handleRef.current = handle;
    },
    [brain, startRaf, stopRaf],
  );

  const clearMessages = useCallback(() => {
    handleRef.current?.cancel();
    stopRaf();
    pendingRef.current = "";
    finishedRef.current = false;
    threadRef.current = null;
    setThreadId(null);
    try {
      window.localStorage.removeItem(THREAD_KEY);
      window.sessionStorage.removeItem(THREAD_KEY);
    } catch {
      /* ignore */
    }
    setMessages([]);
    setIsStreaming(false);
    setToolActivity([]);
  }, [stopRaf]);

  // Inject an assistant message into the thread without going through the
  // streaming path. Used when the harness's approval-resume produces a
  // post-approval reply (`final_text`) -- without this, the chat message
  // list stays frozen at "paused — 1 approval pending" even after the
  // user approves, because the resume runs out-of-band of /chat/stream.
  const injectAssistantMessage = useCallback((text: string) => {
    const trimmed = (text || "").trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { role: "assistant", content: trimmed }]);
  }, []);

  return {
    messages,
    isStreaming,
    toolActivity,
    threadId,
    sendMessage,
    clearMessages,
    injectAssistantMessage,
  };
}
