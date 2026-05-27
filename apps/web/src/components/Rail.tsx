// Live port of JARVIS/app/rail.jsx — fetches hot cache, derives pinned pages
// from wikilinks in hot.md, lists recent tool activity.
import { useEffect, useState, type CSSProperties } from "react";
import { api } from "../lib/api";
import type { ToolActivity } from "../hooks/useStreamChat";
import type { DisplayBrain } from "../hooks/useBrains";

type PinnedPage = { name: string; tok: number; layer: "hot" | "index" | "wiki" | "raw" };

function layerFor(name: string): PinnedPage["layer"] {
  const n = name.toLowerCase();
  if (n.startsWith("hot") || n.startsWith("memory/")) return "hot";
  if (n.startsWith("index") || n.startsWith("overview")) return "index";
  if (n.startsWith("raw/")) return "raw";
  return "wiki";
}

function useHot(brainId?: string): { tokens: number; max: number; pinned: PinnedPage[] } {
  const [state, setState] = useState({ tokens: 0, max: 1500, pinned: [] as PinnedPage[] });
  useEffect(() => {
    if (!brainId) return;
    let cancelled = false;
    api
      .hot(brainId)
      .then(({ body }) => {
        if (cancelled) return;
        const tokens = Math.ceil(body.length / 4);
        const seen = new Map<string, PinnedPage>();
        for (const m of body.matchAll(/\[\[([^\]]+)\]\]/g)) {
          const name = m[1];
          if (!seen.has(name)) {
            seen.set(name, {
              name,
              tok: Math.max(20, Math.ceil(name.length / 4) * 8),
              layer: layerFor(name),
            });
          }
        }
        setState({ tokens, max: 1500, pinned: Array.from(seen.values()).slice(0, 12) });
      })
      .catch(() => {
        /* keep last */
      });
    return () => {
      cancelled = true;
    };
  }, [brainId]);
  return state;
}

interface RailProps {
  brain: DisplayBrain | null;
  toolActivity: ToolActivity[];
}

export function Rail({ brain, toolActivity }: RailProps) {
  const hot = useHot(brain?.id);
  const tools = toolActivity.slice(-5).map((t) => {
    const elapsedMs = (t.finishedAt ?? Date.now()) - t.startedAt;
    return { name: t.name, elapsed: `${(elapsedMs / 1000).toFixed(2)}s` };
  });

  return (
    <aside className="rail">
      <div className="group">
        <h4>
          HOT CACHE <span className="actions">{(brain?.title ?? "—").toUpperCase()}</span>
        </h4>
        <div className="bar">
          <span
            style={
              {
                ["--w" as never]: `${Math.min(100, (hot.tokens / hot.max) * 100)}%`,
              } as CSSProperties
            }
          ></span>
        </div>
        <div className="tele">
          <span>tokens</span>
          <span className="v accent">
            {hot.tokens.toLocaleString()} / {hot.max.toLocaleString()}
          </span>
        </div>
        <div className="tele">
          <span>pages pinned</span>
          <span className="v">{hot.pinned.length}</span>
        </div>
        <div className="pin-list">
          {hot.pinned.map((p, i) => (
            <div className="pin" key={i}>
              <span className={"swatch " + p.layer}></span>
              <span className="name">{p.name}</span>
              <span className="tok">{p.tok}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="group">
        <h4>
          TOOLS THIS TURN <span className="actions">+{tools.length} STEPS</span>
        </h4>
        {tools.map((t, i) => (
          <div className="tele" key={i}>
            <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent-bright)" }}>
              {t.name}
            </span>
            <span className="v">{t.elapsed}</span>
          </div>
        ))}
      </div>

      <div className="group">
        <h4>NODE LAYERS</h4>
        <div className="legend">
          <div>
            <span className="sw" style={{ background: "var(--layer-hot)" }}></span> hot
          </div>
          <div>
            <span className="sw" style={{ background: "var(--layer-index)" }}></span> index
          </div>
          <div>
            <span className="sw" style={{ background: "var(--layer-wiki)" }}></span> wiki
          </div>
          <div>
            <span className="sw" style={{ background: "var(--layer-raw)" }}></span> raw
          </div>
        </div>
      </div>
    </aside>
  );
}
