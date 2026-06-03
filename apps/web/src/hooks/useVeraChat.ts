import { useState, useCallback, useRef, useEffect } from "react";
import { veraStream, type VeraStreamHandle } from "../lib/api";
import type { ChatMessage } from "./useStreamChat";

// Shared thread key, kept distinct from the Chat tab so the two assistants
// don't trample each other's conversation id.
const THREAD_KEY = "disease360.veraThread";

function readThreadId(): string | null {
  try {
    return (
      window.localStorage.getItem(THREAD_KEY) ||
      window.sessionStorage.getItem(THREAD_KEY)
    );
  } catch {
    return null;
  }
}

function writeThreadId(id: string): void {
  try {
    window.localStorage.setItem(THREAD_KEY, id);
  } catch {
    /* ignore quota / privacy errors */
  }
}

/**
 * Streaming chat hook for the Vera tab.
 *
 * Vera is backed by a Databricks-served MLflow ResponsesAgent (proxied by the
 * harness), which has no LangGraph thread/checkpointer. So we keep the full
 * conversation in local state and send it on every turn; the harness forwards
 * it to Databricks. Tokens are revealed smoothly via a requestAnimationFrame
 * drain loop (same approach as `useStreamChat`).
 */
export function useVeraChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const initialThread = readThreadId();
  const [threadId, setThreadId] = useState<string | null>(initialThread);
  const threadRef = useRef<string | null>(initialThread);
  const handleRef = useRef<VeraStreamHandle | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  const pendingRef = useRef(""); // chars not yet committed to state
  const rafRef = useRef<number | null>(null);
  const finishedRef = useRef(false); // server said "done" — drain then stop

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
      rafRef.current = requestAnimationFrame(tick);
      return;
    }

    const reveal = Math.max(1, Math.min(queued.length, Math.ceil(queued.length / 6)));
    const slice = queued.slice(0, reveal);
    pendingRef.current = queued.slice(reveal);

    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.role !== "assistant") return prev;
      const updated = [...prev];
      updated[updated.length - 1] = { ...last, content: last.content + slice };
      messagesRef.current = updated;
      return updated;
    });

    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const startRaf = useCallback(() => {
    if (rafRef.current == null) {
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [tick]);

  useEffect(
    () => () => {
      handleRef.current?.cancel();
      stopRaf();
    },
    [stopRaf],
  );

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      handleRef.current?.cancel();
      stopRaf();
      pendingRef.current = "";
      finishedRef.current = false;

      const userMsg: ChatMessage = { role: "user", content: trimmed };
      const assistantMsg: ChatMessage = { role: "assistant", content: "" };
      // History sent to Databricks: prior turns + the new user message,
      // excluding the empty assistant placeholder.
      const history = [...messagesRef.current, userMsg];
      const next = [...history, assistantMsg];
      messagesRef.current = next;
      setMessages(next);
      setIsStreaming(true);

      const handle = veraStream(
        { messages: history, thread_id: threadRef.current },
        (evt) => {
          switch (evt.type) {
            case "meta":
              threadRef.current = evt.thread_id;
              setThreadId(evt.thread_id);
              writeThreadId(evt.thread_id);
              break;
            case "token": {
              const delta = evt.text;
              if (!delta) break;
              pendingRef.current += delta;
              startRaf();
              break;
            }
            case "done":
              threadRef.current = evt.thread_id;
              setThreadId(evt.thread_id);
              writeThreadId(evt.thread_id);
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
    [startRaf, stopRaf],
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
    messagesRef.current = [];
    setMessages([]);
    setIsStreaming(false);
  }, [stopRaf]);

  return {
    messages,
    isStreaming,
    threadId,
    sendMessage,
    clearMessages,
  };
}
