// Verbatim port of JARVIS/app/pages.jsx — Approvals / Brains / BrainDetail / Settings.
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type LintReport, type LintIssue } from "../lib/api";
import { renderMarkdown } from "../lib/markdown";
import { IngestPlanCard } from "./Chat";
import type { DisplayApproval } from "../hooks/useApprovalsLive";
import type { DisplayBrain } from "../hooks/useBrains";

// ============================================================
// APPROVALS
// ============================================================
function ApprovalCard({
  a,
  onResolve,
}: {
  a: DisplayApproval;
  onResolve: (id: string, decision: "approved" | "denied") => void;
}) {
  const [showArgs, setShowArgs] = useState(false);
  const urgent = a.status === "pending" && a.expires_in < 60;

  // When the approval wraps an ingest/solve plan, the plan card already
  // contains all the meaningful info (summary, ops, diffs) — render it
  // inline and skip the generic args pane.
  if (a.plan) {
    return (
      <div className={"appcard " + a.status + " appcard-plan"}>
        <IngestPlanCard
          plan={a.plan}
          pending={a.status === "pending" ? { expires_in: a.expires_in } : undefined}
          onApprove={a.status === "pending" ? () => onResolve(a.id, "approved") : undefined}
          onDeny={a.status === "pending" ? () => onResolve(a.id, "denied") : undefined}
        />
      </div>
    );
  }

  return (
    <div className={"appcard " + a.status}>
      <div className="row1">
        <span className={"status-pill " + a.status}>
          {a.status === "pending"
            ? "● PENDING"
            : a.status === "dnd_held"
              ? "☾ DND HELD"
              : a.status === "approved"
                ? "✓ APPROVED"
                : a.status === "denied"
                  ? "× DENIED"
                  : "○ EXPIRED"}
        </span>
        <span className="tool-name">{a.tool}</span>
        <span className={"countdown" + (urgent ? " urgent" : "")}>
          {a.status === "pending" &&
            `EXPIRES IN ${Math.floor(a.expires_in / 60)}:${String(a.expires_in % 60).padStart(2, "0")}`}
          {a.status === "dnd_held" && "HELD · drains 07:00"}
          {a.status === "approved" && `RESOLVED ${a.resolved_at} · via ${a.resolved_by}`}
          {a.status === "denied" && `DENIED ${a.resolved_at} · via ${a.resolved_by}`}
          {a.status === "expired" && `CREATED ${a.created_at}`}
        </span>
        <span className="shortid">{a.short}</span>
      </div>
      <div className={"rationale " + (a.status !== "pending" ? "muted" : "")}>{a.rationale}</div>
      {a.delta && (
        <div style={{ display: "flex", gap: 6 }}>
          <span className="chip chip-accent">{a.delta}</span>
          {a.ops_count && <span className="chip">{a.ops_count}</span>}
          <span className="chip chip-muted">{a.thread_id}</span>
        </div>
      )}
      <button className="args-toggle" onClick={() => setShowArgs((s) => !s)}>
        {showArgs ? "▾" : "›"} {showArgs ? "Hide" : "Show"} arguments
      </button>
      {showArgs && (
        <pre
          style={{
            margin: 0,
            padding: 14,
            background: "oklch(0.13 0.012 240)",
            border: "1px solid var(--border-hairline)",
            borderRadius: "var(--r-sm)",
            fontFamily: "var(--font-mono)",
            fontSize: 11.5,
            color: "var(--text-secondary)",
            overflow: "auto",
          }}
        >
          {JSON.stringify(a.args, null, 2)}
        </pre>
      )}
      {a.status === "pending" && (
        <div className="actions">
          <button className="btn" onClick={() => onResolve(a.id, "denied")}>
            Deny
          </button>
          <button className="btn btn-primary" onClick={() => onResolve(a.id, "approved")}>
            Approve →
          </button>
        </div>
      )}
    </div>
  );
}

type FilterId = "pending" | "dnd_held" | "approved" | "denied" | "expired" | "all";

export function ApprovalsPage({
  approvals,
  onResolve,
}: {
  approvals: DisplayApproval[];
  onResolve: (id: string, decision: "approved" | "denied") => void;
}) {
  const [filter, setFilter] = useState<FilterId>("pending");
  const counts = useMemo(() => {
    const c: Record<string, number> = {
      pending: 0,
      dnd_held: 0,
      approved: 0,
      denied: 0,
      expired: 0,
    };
    approvals.forEach((a) => {
      c[a.status] = (c[a.status] || 0) + 1;
    });
    return c;
  }, [approvals]);
  const list = useMemo(
    () => (filter === "all" ? approvals : approvals.filter((a) => a.status === filter)),
    [approvals, filter],
  );

  const filters: { id: FilterId; label: string }[] = [
    { id: "pending", label: "Pending" },
    { id: "dnd_held", label: "DND" },
    { id: "approved", label: "Approved" },
    { id: "denied", label: "Denied" },
    { id: "expired", label: "Expired" },
    { id: "all", label: "All" },
  ];

  return (
    <div className="approvals-page page">
      <div className="approvals-inner">
        <div className="page-head approvals-page-head">
          <div>
            <span className="eyebrow">WORKFLOW</span>
            <h1>Approvals</h1>
            <p>
              Every mutating tool pauses here. Approve from the keyboard, the CLI, or by giving
              the camera a thumbs-up.
            </p>
          </div>
        </div>

        <div className="filter-row">
          <div className="filter-seg">
            {filters.map((f) => (
              <button
                key={f.id}
                className={filter === f.id ? "active" : ""}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
                <span className="ct">
                  {f.id === "all" ? approvals.length : counts[f.id] || 0}
                </span>
              </button>
            ))}
          </div>
          <button className="btn btn-ghost" disabled style={{ opacity: 0.6 }}>
            <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
              >
                <rect x="2" y="4" width="9" height="8" rx="1.5" />
                <path d="M11 7l3-1.5v5L11 9" />
              </svg>
              Enable gestures
            </span>
            <span
              className="mono"
              style={{ color: "var(--text-faint)", fontSize: 10.5, marginLeft: 8 }}
            >
              OFF
            </span>
          </button>
        </div>

        <div className="approvals-list">
          {list.length === 0 ? (
            <div className="empty-orb" style={{ margin: "60px auto" }}>
              <div className="orb"></div>
              <h2>Nothing here</h2>
              <p>
                No {filter === "all" ? "" : filter + " "}approvals. The agent has no pending
                work.
              </p>
            </div>
          ) : (
            list.map((a) => <ApprovalCard key={a.id} a={a} onResolve={onResolve} />)
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// BRAINS
// ============================================================
export function BrainsPage({ brains }: { brains: DisplayBrain[] }) {
  const location = useLocation();
  const navigate = useNavigate();
  const nav = location.state as { brainId?: string; pagePath?: string } | null;
  const [open, setOpen] = useState<string | null>(nav?.brainId ?? null);
  const [initialPage, setInitialPage] = useState<string | null>(nav?.pagePath ?? null);

  useEffect(() => {
    if (nav?.brainId) {
      setOpen(nav.brainId);
      setInitialPage(nav.pagePath ?? null);
      // Clear nav state so we don't keep re-applying it on re-renders.
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nav?.brainId, nav?.pagePath]);

  if (open) {
    const b = brains.find((x) => x.id === open);
    if (b)
      return (
        <BrainDetail
          brain={b}
          initialPage={initialPage}
          onBack={() => {
            setOpen(null);
            setInitialPage(null);
          }}
        />
      );
  }
  return (
    <div className="brains-page page">
      <div className="brains-inner">
        <div className="page-head">
          <span className="eyebrow">SECOND BRAIN</span>
          <h1>Brains</h1>
          <p>
            Each brain is a folder of markdown notes — hot cache, curated index, lint report.
            Portable, editable, yours.
          </p>
        </div>

        <div className="brains-grid">
          {brains.map((b, i) => {
            const initials = b.title
              .split(" ")
              .map((w) => w[0])
              .join("")
              .slice(0, 2)
              .toUpperCase();
            return (
              <div
                key={b.id}
                className={"bcard b" + ((i % 4) + 1)}
                onClick={() => setOpen(b.id)}
              >
                <div className="tile">{initials}</div>
                <div>
                  <h3>
                    {b.title}
                    {b.is_global && (
                      <span
                        className="global-tag"
                        style={{ marginLeft: 8, verticalAlign: "middle" }}
                      >
                        GLOBAL
                      </span>
                    )}
                  </h3>
                  <div className="chips">
                    <span className="chip chip-accent">{b.page_count} pages</span>
                    <span className={"chip " + (b.has_hot ? "chip-success" : "chip-muted")}>
                      {b.has_hot ? "hot" : "cold"}
                    </span>
                    {b.is_global && (
                      <span
                        className="chip chip-accent"
                        title="Links to and queries across all other brains"
                      >
                        links to all brains
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

type PageEntry = { id: string; title: string; layer: "hot" | "index" | "wiki" | "raw" };

function BrainDetail({
  brain,
  initialPage,
  onBack,
}: {
  brain: DisplayBrain;
  initialPage: string | null;
  onBack: () => void;
}) {
  const [pages, setPages] = useState<PageEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(initialPage);
  const [body, setBody] = useState<string>("");
  const [title, setTitle] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [filter, setFilter] = useState("");
  const [report, setReport] = useState<LintReport | null>(null);
  const [linting, setLinting] = useState(false);
  const [showLint, setShowLint] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  async function loadLint() {
    setLinting(true);
    try {
      setReport(await api.lintBrain(brain.id));
    } catch {
      setReport(null);
    } finally {
      setLinting(false);
    }
  }

  // Load page list from graph endpoint (same data powers the graph view).
  useEffect(() => {
    let cancelled = false;
    api
      .graph(brain.id)
      .then((g) => {
        if (cancelled) return;
        const list: PageEntry[] = g.nodes
          .filter((n) => n.id.endsWith(".md"))
          .map((n) => ({
            id: n.id,
            title: n.title,
            layer: (n.layer as PageEntry["layer"]) || "wiki",
          }))
          .sort((a, b) => {
            const order = { hot: 0, index: 1, wiki: 2, raw: 3 } as const;
            const d = order[a.layer] - order[b.layer];
            return d !== 0 ? d : a.title.localeCompare(b.title);
          });
        setPages(list);
        if (!selected && list.length > 0) setSelected(list[0].id);
      })
      .catch(() => setPages([]));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brain.id]);

  // If parent passes a new initialPage (e.g., a graph node click), jump to it.
  useEffect(() => {
    if (initialPage) setSelected(initialPage);
  }, [initialPage]);

  // Load page body whenever selection changes.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setNotFound(false);

    const loader =
      selected === "hot.md"
        ? api.hot(brain.id).then((r) => ({ body: r.body, title: "Hot cache" }))
        : selected === "index.md"
          ? api.index(brain.id).then((r) => ({ body: r.body, title: "Index" }))
          : api.page(brain.id, selected).then((r) => ({ body: r.body, title: r.title }));

    loader
      .then((r) => {
        if (cancelled) return;
        setBody(r.body);
        setTitle(r.title);
      })
      .catch(() => {
        if (cancelled) return;
        setBody("");
        setTitle("");
        setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brain.id, selected]);

  // Intercept wikilink clicks anywhere inside the rendered page.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    function onClick(e: MouseEvent) {
      const el = (e.target as HTMLElement).closest("a[data-wikilink]") as HTMLAnchorElement | null;
      if (!el) return;
      e.preventDefault();
      const target = el.dataset.wikilink || "";
      resolveAndOpen(target);
    }
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages]);

  function resolveAndOpen(target: string) {
    // Wikilinks reference a slug without .md. Match against known pages.
    const t = target.trim();
    if (!t) return;
    // 1. direct .md match (already a full path)
    const direct = pages.find((p) => p.id === t || p.id === `${t}.md`);
    if (direct) {
      setSelected(direct.id);
      return;
    }
    // 2. match by filename stem across any folder.
    const withMd = `${t}.md`;
    const byStem = pages.find(
      (p) => p.id.endsWith(`/${withMd}`) || p.id === withMd,
    );
    if (byStem) {
      setSelected(byStem.id);
      return;
    }
    // 3. match by title (case-insensitive).
    const byTitle = pages.find((p) => p.title.toLowerCase() === t.toLowerCase());
    if (byTitle) {
      setSelected(byTitle.id);
      return;
    }
    // Unresolved — keep current page, flash nothing for now.
  }

  async function fixIssue(iss: LintIssue) {
    try {
      const plan = await api.planSolve(brain.id, iss);
      await api.applySolve(brain.id, plan.plan_id);
      await loadLint();
    } catch (e) {
      alert(`Fix failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  const filteredPages = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter(
      (p) => p.title.toLowerCase().includes(q) || p.id.toLowerCase().includes(q),
    );
  }, [pages, filter]);

  const grouped = useMemo(() => {
    const g: Record<string, PageEntry[]> = { hot: [], index: [], wiki: [], raw: [] };
    for (const p of filteredPages) g[p.layer]?.push(p);
    return g;
  }, [filteredPages]);

  const groupLabels: { key: keyof typeof grouped; label: string }[] = [
    { key: "hot", label: "Hot" },
    { key: "index", label: "Index" },
    { key: "wiki", label: "Wiki" },
    { key: "raw", label: "Raw" },
  ];

  return (
    <div className="brains-page page">
      <div className="brains-inner">
        <button
          className="btn btn-ghost btn-sm"
          onClick={onBack}
          style={{ marginBottom: 16 }}
        >
          ← All brains
        </button>
        <div className="page-head">
          <span className="eyebrow">
            {brain.title.toUpperCase()} · {brain.page_count} PAGES
            {brain.is_global && " · GLOBAL"}
          </span>
          <h1>
            {brain.title}
            {brain.is_global && (
              <span
                className="global-tag"
                style={{ marginLeft: 14, verticalAlign: "middle", fontSize: 11 }}
              >
                GLOBAL
              </span>
            )}
          </h1>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <button
            className="btn btn-sm btn-ghost"
            onClick={() => {
              setShowLint((v) => !v);
              if (!report && !linting) loadLint();
            }}
          >
            {showLint ? "Hide lint" : "Show lint"}
          </button>
          {showLint && (
            <button className="btn btn-sm btn-ghost" onClick={loadLint} disabled={linting}>
              {linting ? "Linting…" : "↻ Re-lint"}
            </button>
          )}
        </div>

        <div className="brain-detail">
          <aside className="brain-sidebar">
            <input
              className="filter"
              placeholder="Filter pages…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            {groupLabels.map(({ key, label }) =>
              grouped[key].length === 0 ? null : (
                <div key={key}>
                  <div className="group-head">{label}</div>
                  {grouped[key].map((p) => (
                    <a
                      key={p.id}
                      className={"nav-item" + (selected === p.id ? " active" : "")}
                      onClick={(e) => {
                        e.preventDefault();
                        setSelected(p.id);
                      }}
                      href="#"
                      title={p.id}
                    >
                      {p.title}
                    </a>
                  ))}
                </div>
              ),
            )}
            {filteredPages.length === 0 && (
              <div className="group-head" style={{ color: "var(--text-muted)" }}>
                No pages match
              </div>
            )}
          </aside>

          <div>
            <div className="card" style={{ padding: "20px 24px" }} ref={containerRef}>
              {selected && (
                <div className="page-path">{selected}</div>
              )}
              {loading ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading page…</p>
              ) : notFound ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                  Page not found: {selected}
                </p>
              ) : (
                <div className="page-body">
                  {!body.trimStart().startsWith("#") && title && <h1>{title}</h1>}
                  {renderMarkdown(body)}
                </div>
              )}
            </div>

            {showLint && (
              <div className="card" style={{ padding: "20px 24px", marginTop: 16 }}>
                <h3
                  style={{
                    margin: "0 0 12px",
                    fontFamily: "var(--font-mono)",
                    fontSize: 13,
                    letterSpacing: "0.08em",
                  }}
                >
                  Lint report
                </h3>
                {report ? (
                  <>
                    <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                      {report.stats.total_pages != null && (
                        <span className="chip chip-accent">
                          {report.stats.total_pages} pages
                        </span>
                      )}
                      {report.stats.orphans != null && (
                        <span className="chip chip-danger">{report.stats.orphans} orphans</span>
                      )}
                      {report.stats.missing_pages != null && (
                        <span className="chip chip-danger">
                          {report.stats.missing_pages} missing
                        </span>
                      )}
                      <span className="chip">{report.issues.length} issues</span>
                    </div>
                    <p
                      style={{
                        color: "var(--text-secondary)",
                        fontSize: 13.5,
                        margin: "0 0 16px",
                        lineHeight: 1.55,
                      }}
                    >
                      {report.summary}
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {report.issues.map((iss, i) => (
                        <div
                          key={i}
                          style={{
                            display: "grid",
                            gridTemplateColumns: "auto 1fr auto",
                            gap: 14,
                            padding: "12px 14px",
                            border: "1px solid var(--border-hairline)",
                            borderRadius: "var(--r-sm)",
                            alignItems: "start",
                          }}
                        >
                          <span
                            className={
                              "chip " +
                              (iss.severity === "high"
                                ? "chip-danger"
                                : iss.severity === "medium"
                                  ? "chip-accent"
                                  : "chip-muted")
                            }
                          >
                            {iss.severity.toUpperCase()}
                          </span>
                          <div>
                            <div
                              style={{
                                display: "flex",
                                gap: 8,
                                alignItems: "center",
                                marginBottom: 4,
                              }}
                            >
                              <span
                                style={{
                                  fontFamily: "var(--font-mono)",
                                  fontSize: 10.5,
                                  color: "var(--text-faint)",
                                  letterSpacing: "0.08em",
                                  textTransform: "uppercase",
                                }}
                              >
                                {iss.type}
                              </span>
                              <a
                                href="#"
                                onClick={(e) => {
                                  e.preventDefault();
                                  if (iss.page) resolveAndOpen(iss.page);
                                }}
                                style={{
                                  fontFamily: "var(--font-mono)",
                                  fontSize: 11.5,
                                  color: "var(--accent-bright)",
                                  textDecoration: "none",
                                }}
                              >
                                {iss.page}
                              </a>
                            </div>
                            <div
                              style={{
                                fontSize: 13,
                                color: "var(--text-secondary)",
                                marginBottom: 4,
                              }}
                            >
                              {iss.description}
                            </div>
                            <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                              → {iss.suggestion}
                            </div>
                          </div>
                          <button className="btn btn-sm" onClick={() => fixIssue(iss)}>
                            Plan & apply fix
                          </button>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    {linting ? "Running lint…" : "Lint unavailable."}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// SETTINGS — gesture knobs, persisted to localStorage.
// ============================================================
const GESTURE_KEY = "kairos.gestureSettings";

type GestureSettings = { fps: number; conf: number; frames: number; cool: number };
const GESTURE_DEFAULTS: GestureSettings = { fps: 3, conf: 0.65, frames: 3, cool: 2000 };

export function SettingsPage() {
  const [s, setS] = useState<GestureSettings>(() => {
    try {
      const raw = localStorage.getItem(GESTURE_KEY);
      if (raw) return { ...GESTURE_DEFAULTS, ...JSON.parse(raw) };
    } catch {
      /* ignore */
    }
    return GESTURE_DEFAULTS;
  });

  useEffect(() => {
    try {
      localStorage.setItem(GESTURE_KEY, JSON.stringify(s));
    } catch {
      /* ignore */
    }
  }, [s]);

  const sliders = [
    {
      lbl: "Frame rate",
      hint: "How often the camera samples a frame.",
      v: s.fps,
      key: "fps" as const,
      min: 1,
      max: 10,
      step: 1,
      fmt: (v: number) => `${v} fps`,
    },
    {
      lbl: "Confidence",
      hint: "Minimum model score to count a gesture.",
      v: s.conf,
      key: "conf" as const,
      min: 0.3,
      max: 0.95,
      step: 0.05,
      fmt: (v: number) => v.toFixed(2),
    },
    {
      lbl: "Confirm frames",
      hint: "Consecutive matching frames before firing.",
      v: s.frames,
      key: "frames" as const,
      min: 1,
      max: 10,
      step: 1,
      fmt: (v: number) => `${v}`,
    },
    {
      lbl: "Cooldown",
      hint: "Quiet period after a gesture fires.",
      v: s.cool,
      key: "cool" as const,
      min: 500,
      max: 5000,
      step: 250,
      fmt: (v: number) => `${(v / 1000).toFixed(2)} s`,
    },
  ];

  return (
    <div className="settings-page page">
      <div className="settings-inner">
        <div className="page-head">
          <span className="eyebrow">PREFERENCES</span>
          <h1>Settings</h1>
          <p>Tune gesture recognition. More controls land here as the surface grows.</p>
        </div>

        <div className="settings-card">
          <h3>
            Gestures <span className="desc">Camera-based approval shortcut</span>
          </h3>
          {sliders.map((sl) => {
            const p = ((sl.v - sl.min) / (sl.max - sl.min)) * 100;
            return (
              <div className="slider-row" key={sl.key}>
                <div className="slider-top">
                  <div>
                    <div className="lbl">{sl.lbl}</div>
                    <div className="hint">{sl.hint}</div>
                  </div>
                  <div className="val">{sl.fmt(sl.v)}</div>
                </div>
                <input
                  type="range"
                  min={sl.min}
                  max={sl.max}
                  step={sl.step}
                  value={sl.v}
                  style={{ ["--p" as never]: p + "%" } as React.CSSProperties}
                  onChange={(e) =>
                    setS((prev) => ({ ...prev, [sl.key]: parseFloat(e.target.value) }))
                  }
                />
              </div>
            );
          })}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setS(GESTURE_DEFAULTS)}>
              Reset to defaults
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
