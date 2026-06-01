import { useEffect, useState } from "react";
import type { ToolActivity } from "../hooks/useStreamChat";
import type { VoiceTurnStatus } from "../hooks/useVoiceTurn";
import { renderMarkdown } from "../lib/markdown";
import { downloadResearchReportPdf } from "../lib/reportPdf";

// Replies longer than this collapse to a chevron-expanded preview so the
// panel doesn't squat over half the map. Tuned to ~3-4 lines at the
// panel's font size.
const REPLY_COLLAPSE_THRESHOLD = 220;

interface DashboardActivityProps {
  status: VoiceTurnStatus;
  pttHeld: boolean;
  transcript: string | null;
  reply: string;
  researchReport: string | null;
  toolActivity: ToolActivity[];
  error: string | null;
}

const TOOL_LABELS: Record<string, string> = {
  fly_to_location: "Locating",
  search_wiki: "Searching memory",
  get_page: "Reading page",
  get_hot: "Reading hot cache",
  get_index: "Reading index",
  list_brains: "Listing brains",
  append_hot: "Updating hot cache",
  replace_hot: "Rewriting hot cache",
  write_note: "Writing note",
  plan_ingest: "Planning ingest",
  apply_ingest: "Applying ingest",
  lint_brain: "Linting brain",
  plan_solve: "Planning fix",
  apply_solve: "Applying fix",
};

function labelFor(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

function summarizeArgs(name: string, args: Record<string, unknown>): string | null {
  if (name === "fly_to_location") {
    const place = args.place;
    if (typeof place === "string" && place.trim()) return place;
    const lat = Number(args.lat);
    const lng = Number(args.lng);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return `${lat.toFixed(2)}°, ${lng.toFixed(2)}°`;
    }
    return null;
  }
  if (name === "search_wiki" && typeof args.query === "string") return args.query;
  if (name === "get_page" && typeof args.path === "string") return args.path;
  if (typeof args.brain === "string") return args.brain;
  return null;
}

function elapsedString(t: ToolActivity, now: number): string {
  const ms = (t.finishedAt ?? now) - t.startedAt;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

// Map raw research pipeline stages to clean, business-language phases.
const RESEARCH_PHASE_LABELS: Record<string, string> = {
  start: "Starting research",
  planning: "Planning the investigation",
  researching: "Researching",
  searching: "Searching the web",
  fetching: "Reading sources",
  compressing: "Distilling findings",
  synthesizing: "Writing the report",
  done: "Research complete",
  error: "Research failed",
};

// Build the single, self-contained status line shown under the
// deep_research step, e.g. "Sub-agents dispatched: 13 | Researching".
function researchStatusLine(rp: NonNullable<ToolActivity["researchProgress"]>): string {
  const phase = RESEARCH_PHASE_LABELS[rp.stage] || "Researching";
  const parts: string[] = [];
  if (rp.subagents > 0) parts.push(`Sub-agents dispatched: ${rp.subagents}`);
  if (rp.sources > 0) parts.push(`Sources: ${rp.sources}`);
  parts.push(phase);
  return parts.join(" | ");
}

function phaseFor(
  status: VoiceTurnStatus,
  hasRunningTool: boolean,
): { label: string; tone: string } {
  // The "LISTENING" phase is intentionally absent: while the user is
  // holding Space the center PTT bar already conveys that state, and
  // the panel hides itself entirely (see early return below).
  if (status === "error") return { label: "ERROR", tone: "is-error" };
  if (hasRunningTool) return { label: "EXECUTING", tone: "is-executing" };
  if (status === "thinking") return { label: "THINKING", tone: "is-thinking" };
  if (status === "speaking") return { label: "SPEAKING", tone: "is-speaking" };
  return { label: "STANDBY", tone: "is-idle" };
}

export function DashboardActivity({
  status,
  pttHeld,
  transcript,
  reply,
  researchReport,
  toolActivity,
  error,
}: DashboardActivityProps) {
  // Re-render once per second so running steps' elapsed time updates live.
  const [, tick] = useState(0);
  useEffect(() => {
    const hasRunning = toolActivity.some((t) => t.finishedAt == null);
    if (!hasRunning) return;
    const id = window.setInterval(() => tick((n) => n + 1), 250);
    return () => window.clearInterval(id);
  }, [toolActivity]);

  // PTT-held + the brief "capturing" status are visualized exclusively
  // by the center PTT bar; the top-right panel sits out those phases.
  const hasContent =
    (status !== "idle" && status !== "capturing") ||
    transcript != null ||
    reply.length > 0 ||
    (researchReport != null && researchReport.length > 0) ||
    toolActivity.length > 0;

  // Auto-hide a short moment after returning to idle so the panel doesn't
  // linger forever on the map.
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (hasContent) {
      setVisible(true);
      return;
    }
    const id = window.setTimeout(() => setVisible(false), 4000);
    return () => window.clearTimeout(id);
  }, [hasContent]);

  // Reply expand/collapse state. Reset whenever a fresh turn starts so
  // the new reply opens collapsed by default.
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (reply === "") setExpanded(false);
  }, [reply]);

  // Full deep-research report expand/collapse. Defaults open so the report
  // is visible the moment it lands (the spoken summary above is the TL;DR);
  // the body is height-capped + scrollable so it never swallows the map.
  const [reportExpanded, setReportExpanded] = useState(true);
  useEffect(() => {
    if (researchReport) setReportExpanded(true);
  }, [researchReport]);

  // Hide unconditionally while the user is holding Space, even if the
  // fade-out timer hasn't fired yet -- the user wants a clean center-only
  // listening indicator.
  if (pttHeld) return null;
  if (!visible) return null;

  const hasRunningTool = toolActivity.some((t) => t.finishedAt == null);
  const phase = phaseFor(status, hasRunningTool);
  const now = Date.now();
  const replyOverflows = reply.length > REPLY_COLLAPSE_THRESHOLD;
  const replyExpanded = expanded || !replyOverflows;

  return (
    <aside
      className={`dashboard-activity ${phase.tone}${hasContent ? " is-live" : " is-fading"}`}
      role="status"
      aria-live="polite"
    >
      <header className="dashboard-activity__header">
        <span className="dashboard-activity__dot" aria-hidden="true" />
        <span className="dashboard-activity__phase">{phase.label}</span>
        <span className="dashboard-activity__counter">
          {toolActivity.length > 0 ? `+${toolActivity.length} STEP${toolActivity.length === 1 ? "" : "S"}` : ""}
        </span>
      </header>

      {transcript && (
        <div className="dashboard-activity__transcript">
          <span className="dashboard-activity__caret">›</span>
          <span className="dashboard-activity__transcript-text">{transcript}</span>
        </div>
      )}

      {toolActivity.length > 0 && (
        <ol className="dashboard-activity__steps">
          {toolActivity.map((t, i) => {
            const done = t.finishedAt != null;
            const summary = summarizeArgs(t.name, t.args);
            return (
              <li
                key={`${t.toolCallId ?? t.name}-${i}`}
                className={`dashboard-activity__step ${done ? "is-done" : "is-running"}`}
              >
                <span className="dashboard-activity__step-glyph" aria-hidden="true">
                  {done ? "✓" : "·"}
                </span>
                <span className="dashboard-activity__step-name">{labelFor(t.name)}</span>
                {summary && <span className="dashboard-activity__step-summary">{summary}</span>}
                <span className="dashboard-activity__step-elapsed">
                  {elapsedString(t, now)}
                </span>
                {!done && t.researchProgress && (
                  <span className="dashboard-activity__research-status">
                    <span
                      className="dashboard-activity__research-live"
                      aria-hidden="true"
                    />
                    <span
                      key={researchStatusLine(t.researchProgress)}
                      className="dashboard-activity__research-text"
                    >
                      {researchStatusLine(t.researchProgress)}
                    </span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {reply && (
        <div className="dashboard-activity__reply">
          {researchReport && (
            <span className="dashboard-activity__reply-label">
              TL;DR · spoken summary
            </span>
          )}
          <div
            className={
              "dashboard-activity__reply-body dashboard-activity__md " +
              (replyExpanded ? "is-expanded" : "is-collapsed")
            }
          >
            {renderMarkdown(reply)}
          </div>
          {replyOverflows && (
            <button
              type="button"
              className="dashboard-activity__expand"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
            >
              <span>{expanded ? "Collapse" : "Show more"}</span>
              <svg
                className={
                  "dashboard-activity__chevron" +
                  (expanded ? " is-up" : "")
                }
                width="10"
                height="10"
                viewBox="0 0 10 10"
                aria-hidden="true"
              >
                <path
                  d="M2 3.5 L5 7 L8 3.5"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
        </div>
      )}

      {researchReport && (
        <div className="dashboard-activity__report">
          <div className="dashboard-activity__report-head">
            <button
              type="button"
              className="dashboard-activity__report-toggle"
              onClick={() => setReportExpanded((v) => !v)}
              aria-expanded={reportExpanded}
            >
              <span>Full research report</span>
              <svg
                className={
                  "dashboard-activity__chevron" + (reportExpanded ? " is-up" : "")
                }
                width="10"
                height="10"
                viewBox="0 0 10 10"
                aria-hidden="true"
              >
                <path
                  d="M2 3.5 L5 7 L8 3.5"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            <button
              type="button"
              className="dashboard-activity__report-download"
              onClick={() =>
                downloadResearchReportPdf(researchReport, { query: transcript })
              }
              title="Download report as PDF"
            >
              <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
                <path
                  d="M6 1 V7.5 M3.5 5.5 L6 8 L8.5 5.5 M2 10 H10"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>PDF</span>
            </button>
          </div>
          {reportExpanded && (
            <div className="dashboard-activity__report-body dashboard-activity__md">
              {renderMarkdown(researchReport)}
            </div>
          )}
        </div>
      )}

      {error && status === "error" && (
        <p className="dashboard-activity__error">{error}</p>
      )}
    </aside>
  );
}
