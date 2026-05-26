// Live approvals: polls every 3s, derives the design's display fields.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Approval, type IngestPlan } from "../lib/api";

export type DisplayApproval = Approval & {
  short: string;
  expires_in: number; // seconds, derived from expires_at - now
  delta: string | null;
  ops_count: string | null;
  plan: IngestPlan | null;
};

function derive(a: Approval, now: number): DisplayApproval {
  const expiresAt = Date.parse(a.expires_at);
  const expires_in = Number.isFinite(expiresAt)
    ? Math.max(0, Math.floor((expiresAt - now) / 1000))
    : 0;
  const short =
    a.id.length > 12
      ? `${a.id.slice(0, 6)}…${a.id.slice(-2)}`
      : a.id;
  const plan = (a.args && (a.args as { plan?: IngestPlan }).plan) || null;
  let delta: string | null = null;
  let ops_count: string | null = null;
  if (plan && Array.isArray(plan.ops)) {
    let adds = 0;
    let dels = 0;
    for (const op of plan.ops) {
      const before = (op.before || "").split("\n").length;
      const after = (op.after || "").split("\n").length;
      if (op.kind === "create") adds += after;
      else {
        adds += Math.max(0, after - before);
        dels += Math.max(0, before - after);
      }
    }
    delta = `+${adds} / −${dels}`;
    ops_count = `${plan.ops.length} ops`;
  }
  return { ...a, short, expires_in, delta, ops_count, plan };
}

export type ResolveOutcome = {
  thread_id: string;
  final_text: string;
};

export function useApprovalsLive(pollMs = 3000): {
  approvals: DisplayApproval[];
  pendingCount: number;
  refresh: () => Promise<void>;
  resolve: (
    id: string,
    decision: "approved" | "denied",
  ) => Promise<ResolveOutcome | null>;
} {
  const [raw, setRaw] = useState<Approval[]>([]);
  const [now, setNow] = useState(Date.now());
  const tickerRef = useRef<number | null>(null);

  const refresh = useRef(async () => {
    try {
      const list = await api.listApprovals("");
      setRaw(list);
    } catch {
      /* swallow — keep last good list */
    }
  }).current;

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [pollMs, refresh]);

  // 1Hz ticker for countdowns
  useEffect(() => {
    tickerRef.current = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      if (tickerRef.current != null) clearInterval(tickerRef.current);
    };
  }, []);

  const approvals = useMemo(() => raw.map((a) => derive(a, now)), [raw, now]);
  const pendingCount = useMemo(
    () => approvals.filter((a) => a.status === "pending").length,
    [approvals],
  );

  async function resolve(
    id: string,
    decision: "approved" | "denied",
  ): Promise<ResolveOutcome | null> {
    // Capture the thread BEFORE the call: once the approval flips out of
    // pending the next refresh may drop it from our list.
    const target = raw.find((x) => x.id === id);
    const threadId = target?.thread_id ?? "";
    let finalText = "";
    try {
      const res =
        decision === "approved" ? await api.approve(id) : await api.deny(id);
      finalText = (res?.final_text ?? "").toString();
    } finally {
      await refresh();
    }
    if (!threadId) return null;
    return { thread_id: threadId, final_text: finalText };
  }

  return { approvals, pendingCount, refresh, resolve };
}
