// Verbatim port of JARVIS/app/chat.jsx (Thinking, ToolCallout, IngestPlan,
// ChatStream, SkeletonAnswer, Composer). Live-wired via useStreamChat:
// the streaming hook drives messages + toolActivity, and tool callouts
// render between the current user message and the in-progress assistant.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { I } from "../lib/icons";
import { renderMarkdown } from "../lib/markdown";
import type { ResearchStep, ToolActivity } from "../hooks/useStreamChat";
import type { IngestPlan, WikiEditOp } from "../lib/api";

// ============================================================
// THINKING STRIP (kept for inline live tool console while streaming)
// ============================================================
export function Thinking({
  label,
  tool,
  elapsed,
  steps,
  console: lines,
}: {
  label: string;
  tool: string;
  elapsed: number;
  steps: number;
  console: { kind: "fire" | "ok" | "warn"; name?: string; args?: string; text?: string }[];
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className={"thinking" + (open ? " open" : "")}>
      <div className="row" onClick={() => setOpen((o) => !o)}>
        <span className="dots">
          <i></i>
          <i></i>
          <i></i>
        </span>
        <span className="label">
          {label} <span className="light">· current tool</span>{" "}
          <span style={{ color: "var(--accent-bright)" }}>{tool}</span>
        </span>
        <span className="meta-r">
          <span>{elapsed.toFixed(1)}s</span>
          <span>+{steps} steps</span>
        </span>
        <span className="chevron">▾</span>
      </div>
      <div className="console">
        {lines.map((c, i) => (
          <div key={i} className="console-line">
            <span className={"marker " + (c.kind === "ok" ? "ok" : c.kind === "warn" ? "warn" : "")}>
              {c.kind === "ok" ? "✓" : c.kind === "warn" ? "⋯" : "▸"}
            </span>
            <span className="body">
              {c.name && <span className="name">{c.name}</span>}
              {c.name && c.args && " "}
              {c.args && <span className="args">{c.args}</span>}
              {c.text && <span>{c.text}</span>}
            </span>
            <span className="t">{c.kind === "fire" ? "→" : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// TOOL GROUP — consecutive tool calls collapsed into one strip
// ============================================================
type ToolEntry = {
  tool: string;
  args: Record<string, unknown>;
  result: string;
  elapsed: string;
  done: boolean;
  progressMessage?: string;
  steps?: ResearchStep[];
};

function ResearchSteps({ steps }: { steps: ResearchStep[] }) {
  if (!steps || steps.length === 0) return null;
  return (
    <div className="research-steps">
      {steps.map((s, i) => {
        if (s.stage === "search") {
          return (
            <div key={i} className="rs-row">
              <span className="rs-icon" aria-hidden>{I.search}</span>
              <div className="rs-body">
                <div className="rs-q">
                  {s.cached ? "cached " : ""}
                  <span className="rs-q-text">{s.query || s.message}</span>
                </div>
                {s.urls && s.urls.length > 0 && (
                  <div className="rs-urls">
                    {s.urls.slice(0, 5).map((u, j) => (
                      <a
                        key={j}
                        href={u}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="rs-url"
                        title={u}
                      >
                        {(s.titles && s.titles[j]) || hostnameOf(u)}
                      </a>
                    ))}
                    {s.urls.length > 5 && (
                      <span className="rs-url-more">+{s.urls.length - 5}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        }
        if (s.stage === "fetch") {
          return (
            <div key={i} className="rs-row">
              <span className="rs-icon" aria-hidden>↓</span>
              <div className="rs-body">
                <div className="rs-q">
                  {s.cached ? "cached " : s.ok === false ? "failed " : ""}
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="rs-url"
                    title={s.url}
                  >
                    {hostnameOf(s.url || "") || s.url}
                  </a>
                </div>
              </div>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function formatToolName(name: string): string {
  return name.replace(/_/g, " ");
}

function formatElapsed(ms: string): string {
  const n = parseFloat(ms);
  if (isNaN(n)) return ms;
  if (n >= 60) return `${(n / 60).toFixed(1)}m`;
  return `${n.toFixed(1)}s`;
}

export function ToolGroup({ entries }: { entries: ToolEntry[] }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const allDone = entries.every((e) => e.done);
  const count = entries.length;
  const primaryTool = entries[0]?.tool || "";
  const displayName = count === 1 ? formatToolName(primaryTool) : `${count} tools`;

  const liveResearch = !allDone && entries.some(
    (e) => e.tool === "deep_research" && e.steps && e.steps.length > 0,
  );

  const totalElapsed = entries.find((e) => e.elapsed)?.elapsed;

  return (
    <div className={"tool-group" + (open ? " open" : "") + (allDone ? " done" : " running")}>
      <div className="tg-head" onClick={() => setOpen((o) => !o)}>
        <span className={"tg-indicator" + (allDone ? " done" : "")}>
          {allDone ? (
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />
            </svg>
          ) : (
            <span className="tg-pulse" />
          )}
        </span>
        <span className="tg-label">
          <span className="tg-name">{displayName}</span>
          {!allDone && entries[0]?.progressMessage && (
            <span className="tg-progress">{entries[0].progressMessage}</span>
          )}
        </span>
        <span className="tg-meta">
          {totalElapsed && <span className="tg-elapsed">{formatElapsed(totalElapsed)}</span>}
          <span className="tg-chev">{I.caret}</span>
        </span>
      </div>
      {liveResearch && !open && (
        <div className="tg-body live">
          {entries.map((e, i) =>
            e.steps && e.steps.length > 0 ? (
              <ResearchSteps key={`live-${i}`} steps={e.steps} />
            ) : null,
          )}
        </div>
      )}
      {open && (
        <div className="tg-body">
          {entries.map((e, i) => {
            const isOpen = !!expanded[i];
            return (
              <div key={i} className={"tg-row" + (isOpen ? " expanded" : "")}>
                <div
                  className="tg-row-head"
                  onClick={() => setExpanded((s) => ({ ...s, [i]: !s[i] }))}
                >
                  <span className={"tg-row-indicator" + (e.done ? " done" : "")}>
                    {e.done ? (
                      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />
                      </svg>
                    ) : (
                      <span className="tg-pulse sm" />
                    )}
                  </span>
                  <span className="tg-row-name">{formatToolName(e.tool)}</span>
                  <span className="tg-row-result">{e.result}</span>
                  <span className="tg-row-right">
                    <span className="tg-row-elapsed">{e.elapsed}</span>
                  </span>
                </div>
                {isOpen && (
                  <>
                    <div className="tg-row-detail">
                      {Object.entries(e.args).map(([k, v]) => (
                        <div key={k} className="tg-row-field">
                          <span className="tg-field-key">{formatToolName(k)}</span>
                          <span className="tg-field-val">{typeof v === "string" ? v : JSON.stringify(v)}</span>
                        </div>
                      ))}
                    </div>
                    {e.steps && e.steps.length > 0 && (
                      <ResearchSteps steps={e.steps} />
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================
// INGEST PLAN — diff renderer (computed from before/after on server ops)
// ============================================================
type DiffLineT = { type: "ctx" | "add" | "del"; n1?: number; n2?: number; t: string };

function lcsDiff(beforeText: string, afterText: string): DiffLineT[] {
  const a = beforeText.split("\n");
  const b = afterText.split("\n");
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLineT[] = [];
  let i = 0;
  let j = 0;
  let ln1 = 1;
  let ln2 = 1;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      out.push({ type: "ctx", n1: ln1++, n2: ln2++, t: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: "del", n1: ln1++, t: a[i] });
      i++;
    } else {
      out.push({ type: "add", n2: ln2++, t: b[j] });
      j++;
    }
  }
  while (i < m) out.push({ type: "del", n1: ln1++, t: a[i++] });
  while (j < n) out.push({ type: "add", n2: ln2++, t: b[j++] });
  return out;
}

function DiffLine({ d }: { d: DiffLineT }) {
  const cls = d.type;
  return (
    <div className="line">
      <div className={"ln " + cls}>
        {d.type === "add" ? "+" : d.type === "del" ? "−" : ""}
        {d.n2 || d.n1}
      </div>
      <div className={"tx " + cls}>{d.t || " "}</div>
    </div>
  );
}

function IngestOp({ op }: { op: WikiEditOp }) {
  const [open, setOpen] = useState(op.kind === "create");
  const diff = (() => {
    if (op.kind === "create") {
      return op.after.split("\n").map((t, i) => ({ type: "add" as const, n2: i + 1, t }));
    }
    return lcsDiff(op.before || "", op.after);
  })();
  const adds = diff.filter((d) => d.type === "add").length;
  const dels = diff.filter((d) => d.type === "del").length;
  return (
    <div className={"op" + (open ? " open" : "")}>
      <div className="ohead" onClick={() => setOpen((o) => !o)}>
        <span className="chevron">›</span>
        <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
          <span className={"kind " + op.kind}>{op.kind.toUpperCase()}</span>
          <span className="path">{op.path}</span>
        </div>
        <span className="delta">
          <span className="add">+{adds}</span>
          <span className="del">−{dels}</span>
        </span>
        <span
          style={{
            color: "var(--text-faint)",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
          }}
        >
          {diff.length} lines
        </span>
      </div>
      {open && (
        <div className="diff">
          {diff.map((d, i) => (
            <DiffLine key={i} d={d} />
          ))}
        </div>
      )}
    </div>
  );
}

export function IngestPlanCard({
  plan,
  pending,
  onApprove,
  onDeny,
}: {
  plan: IngestPlan;
  pending?: { expires_in: number };
  onApprove?: () => void;
  onDeny?: () => void;
}) {
  return (
    <div className="ingest">
      <div className="ihead">
        <span className="icon">⤓</span>
        <div>
          <h4>
            Ingest plan ·{" "}
            <span className="mono accent" style={{ fontSize: "12.5px" }}>
              {plan.brain}
            </span>
          </h4>
          <div className="summary">{plan.summary}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="chip chip-accent">{plan.ops.length} ops</span>
          {pending && (
            <span className="pending-pill">
              PENDING · {Math.floor(pending.expires_in / 60)}:
              {String(pending.expires_in % 60).padStart(2, "0")}
            </span>
          )}
        </div>
      </div>
      <div>
        {plan.ops.map((op, i) => (
          <IngestOp key={i} op={op} />
        ))}
      </div>
      {pending && (onApprove || onDeny) && (
        <div className="actions" style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
          {onDeny && (
            <button className="btn" onClick={onDeny}>
              Deny
            </button>
          )}
          {onApprove && (
            <button className="btn btn-primary" onClick={onApprove}>
              Approve →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// MESSAGES + SKELETON
// ============================================================
export type ChatMsg =
  | { role: "user"; ts: string; content: string }
  | { role: "assistant"; ts: string; content: string }
  | {
      role: "tool";
      tool: string;
      args: Record<string, unknown>;
      result: string;
      elapsed: string;
      done: boolean;
      progressMessage?: string;
      steps?: ResearchStep[];
    };

function SkeletonAnswer() {
  return (
    <div className="msg">
      <div className="meta">
        <span className="who jarvis">KAIROS</span>
        <span>·</span>
      </div>
      <div style={{ display: "grid", gap: 8, maxWidth: 520 }}>
        <div className="skel" style={{ width: "94%" }}></div>
        <div className="skel" style={{ width: "86%" }}></div>
        <div className="skel" style={{ width: "72%" }}></div>
      </div>
    </div>
  );
}

export function ChatStream({
  items,
  streaming,
  footer,
  onWikilinkClick,
}: {
  items: ChatMsg[];
  streaming: boolean;
  footer?: ReactNode;
  onWikilinkClick?: (target: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [items.length, streaming]);

  useEffect(() => {
    const root = ref.current;
    if (!root || !onWikilinkClick) return;
    function onClick(e: MouseEvent) {
      const el = (e.target as HTMLElement).closest("a[data-wikilink]") as HTMLAnchorElement | null;
      if (!el) return;
      e.preventDefault();
      const target = el.dataset.wikilink || "";
      if (target) onWikilinkClick!(target);
    }
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  }, [onWikilinkClick]);

  // Collapse consecutive tool messages into a single group block.
  // Key the group by the index of its FIRST tool — stable as more tools
  // arrive in the same run, so the user's expanded state is preserved.
  const rendered: ReactNode[] = [];
  let toolBuf: ToolEntry[] = [];
  let groupStart = -1;
  const flushTools = () => {
    if (toolBuf.length === 0) return;
    rendered.push(<ToolGroup key={`tg-${groupStart}`} entries={toolBuf} />);
    toolBuf = [];
    groupStart = -1;
  };
  items.forEach((m, i) => {
    if (m.role === "tool") {
      if (groupStart < 0) groupStart = i;
      toolBuf.push({
        tool: m.tool,
        args: m.args,
        result: m.result,
        elapsed: m.elapsed,
        done: m.done,
        progressMessage: m.progressMessage,
        steps: m.steps,
      });
      return;
    }
    flushTools();
    if (m.role === "user") {
      rendered.push(
        <div className="msg user" key={i}>
          <div className="meta">
            <span className="who">BRUNO</span>
            <span>{m.ts}</span>
          </div>
          <div className="body">{renderMarkdown(m.content)}</div>
        </div>,
      );
      return;
    }
    if (streaming && m.content === "" && i === items.length - 1) {
      rendered.push(<SkeletonAnswer key={i} />);
      return;
    }
    rendered.push(
      <div className="msg" key={i}>
        <div className="meta">
          <span className="who jarvis">KAIROS</span>
          <span>{m.ts}</span>
        </div>
        <div className="body">{renderMarkdown(m.content)}</div>
      </div>,
    );
  });
  flushTools();

  return (
    <div className="messages" ref={ref}>
      <div className="messages-inner">
        {rendered}
        {footer}
      </div>
    </div>
  );
}

// ============================================================
// COMPOSER
// ============================================================
export function Composer({
  onSend,
  streaming,
  tokenInfo,
}: {
  onSend: (text: string, opts?: { useResearch?: boolean }) => void;
  streaming: boolean;
  tokenInfo?: { tokens: number; max: number };
}) {
  const [val, setVal] = useState("");
  const [researchMode, setResearchMode] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const t = ref.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(120, t.scrollHeight) + "px";
  }, [val]);

  function submit() {
    if (!val.trim() || streaming) return;
    onSend(val, { useResearch: researchMode });
    setVal("");
  }

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={ref}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={researchMode ? "Enter your research query…" : "Ask, plan, capture, or recall — your brain is loaded."}
        />
        <button
          className="send-btn"
          disabled={!val.trim() || streaming}
          onClick={submit}
          title="Send"
        >
          {I.send}
        </button>
        <div className="composer-foot">
          <span>
            <kbd>↵</kbd> SEND · <kbd>⇧↵</kbd> NEWLINE
          </span>
          <span style={{ display: "flex", gap: 14, alignItems: "center" }}>
            <button
              className={"research-toggle" + (researchMode ? " active" : "")}
              onClick={() => setResearchMode((v) => !v)}
              title={researchMode ? "Deep research ON — click to disable" : "Enable deep research mode"}
              type="button"
            >
              {I.search} RESEARCH
            </button>
            {tokenInfo && (
              <span style={{ color: "var(--text-muted)" }} className="mono">
                {tokenInfo.tokens}/{tokenInfo.max} TOK
              </span>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Build the unified message stream from useStreamChat outputs.
// ============================================================
export function buildItems(
  messages: { role: "user" | "assistant"; content: string }[],
  toolActivity: ToolActivity[],
  isStreaming: boolean,
): ChatMsg[] {
  const out: ChatMsg[] = [];
  const now = Date.now();
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    out.push({ role: m.role, ts: tsOf(i, messages.length), content: m.content });
    // After the final user message (just before the in-progress assistant),
    // splice in tool callouts for the current turn.
    const isLastUser =
      m.role === "user" && i === messages.length - 2 && messages[i + 1]?.role === "assistant";
    if (isLastUser && toolActivity.length > 0) {
      for (const t of toolActivity) {
        const elapsedMs = (t.finishedAt ?? now) - t.startedAt;
        out.push({
          role: "tool",
          tool: t.name,
          args: t.args,
          result: t.finishedAt ? "done" : isStreaming ? "running…" : "done",
          elapsed: `${(elapsedMs / 1000).toFixed(2)}s`,
          done: !!t.finishedAt,
          progressMessage: t.progressMessage,
          steps: t.steps,
        });
      }
    }
  }
  return out;
}

function tsOf(i: number, total: number): string {
  // We don't track real timestamps; show the wall-clock for the latest pair
  // and a hyphen for older messages so the UI doesn't lie.
  if (i >= total - 2) {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  return "—";
}
