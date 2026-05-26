// Hand-rolled force layout (no D3) + click-to-reveal flashcard.
// Data is fetched live from api.graph(brainId).
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { DisplayBrain } from "../hooks/useBrains";

type GraphNode = { id: string; title: string; layer: "hot" | "index" | "wiki" | "raw" };
type GraphEdge = { source: string; target: string };
type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };

function getCss(v: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || "white";
}

interface NodeS extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  degree: number;
}

// Strip YAML frontmatter + markdown noise and return the first content paragraph.
function extractPreview(body: string, maxLen = 260): string {
  let src = body;
  if (src.startsWith("---")) {
    const end = src.indexOf("\n---", 3);
    if (end !== -1) {
      const after = src.indexOf("\n", end + 1);
      src = after === -1 ? "" : src.slice(after + 1);
    }
  }
  const lines = src.split("\n");
  const paras: string[] = [];
  let buf: string[] = [];
  for (const ln of lines) {
    const s = ln.trim();
    if (!s) {
      if (buf.length) {
        paras.push(buf.join(" "));
        buf = [];
      }
      continue;
    }
    if (s.startsWith("#") || s.startsWith(">") || s.startsWith("|") || s.startsWith("```")) {
      if (buf.length) {
        paras.push(buf.join(" "));
        buf = [];
      }
      continue;
    }
    if (/^[-*]\s/.test(s) || /^\d+\.\s/.test(s)) {
      if (buf.length) {
        paras.push(buf.join(" "));
        buf = [];
      }
      paras.push(s.replace(/^[-*]\s+|^\d+\.\s+/, ""));
      continue;
    }
    buf.push(s);
  }
  if (buf.length) paras.push(buf.join(" "));

  const raw = paras.find((p) => p.length > 0) ?? "";
  const cleaned = raw
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_m, t, a) => a || t)
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (cleaned.length <= maxLen) return cleaned;
  return cleaned.slice(0, maxLen).replace(/\s+\S*$/, "") + "…";
}

type Selection = {
  node: GraphNode;
  loading: boolean;
  preview: string;
  error: string | null;
};

export function GraphPage({ brain }: { brain: DisplayBrain | null }) {
  const [data, setData] = useState<GraphData>({ nodes: [], edges: [] });
  const navigate = useNavigate();

  useEffect(() => {
    if (!brain) return;
    let cancelled = false;
    api
      .graph(brain.id)
      .then((g) => {
        if (!cancelled) setData(g as GraphData);
      })
      .catch(() => {
        if (!cancelled) setData({ nodes: [], edges: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [brain?.id]);

  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [tt, setTt] = useState<{ x: number; y: number; n: GraphNode } | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [selection, setSelection] = useState<Selection | null>(null);

  // The currently-selected node id is read from the simulation draw loop so
  // the card can track live. Keep it in a ref mirror of `selection`.
  const selectedIdRef = useRef<string | null>(null);
  // Sticky anchor: where the card currently sits. Only re-anchor when the
  // node leaves this footprint (so dragging a node within the card area
  // doesn't shove the card around).
  const anchorRef = useRef<{
    id: string;
    left: number;
    top: number;
    tilt: string;
  } | null>(null);
  useEffect(() => {
    selectedIdRef.current = selection?.node.id ?? null;
    // New selection → force a fresh anchor placement on next tick.
    if (selection?.node.id !== anchorRef.current?.id) anchorRef.current = null;
  }, [selection?.node.id]);

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const w = wrap.clientWidth;
    const h = wrap.clientHeight;
    if (w > 0 && h > 0) setSize({ w, h });
  }, []);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (!r) return;
      setSize((prev) =>
        prev.w === Math.round(r.width) && prev.h === Math.round(r.height)
          ? prev
          : { w: Math.round(r.width), h: Math.round(r.height) },
      );
    });
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  const layerColors = useMemo(
    () => ({
      hot: getCss("--layer-hot"),
      index: getCss("--layer-index"),
      wiki: getCss("--layer-wiki"),
      raw: getCss("--layer-raw"),
    }),
    [],
  );

  // Fetch preview body when a node is selected.
  useEffect(() => {
    if (!selection || !brain) return;
    if (!selection.loading) return;
    const id = selection.node.id;
    let cancelled = false;

    const loader =
      id === "hot.md"
        ? api.hot(brain.id).then((r) => r.body)
        : id === "index.md"
          ? api.index(brain.id).then((r) => r.body)
          : api.page(brain.id, id).then((r) => r.body);

    loader
      .then((body) => {
        if (cancelled) return;
        setSelection((cur) =>
          cur && cur.node.id === id
            ? { ...cur, loading: false, preview: extractPreview(body), error: null }
            : cur,
        );
      })
      .catch((e) => {
        if (cancelled) return;
        setSelection((cur) =>
          cur && cur.node.id === id
            ? {
                ...cur,
                loading: false,
                preview: "",
                error: e instanceof Error ? e.message : String(e),
              }
            : cur,
        );
      });
    return () => {
      cancelled = true;
    };
  }, [selection?.node.id, selection?.loading, brain]);

  useEffect(() => {
    const wrap = wrapRef.current;
    const svg = svgRef.current;
    if (!wrap || !svg || data.nodes.length === 0) return;
    const W = size.w || wrap.clientWidth;
    const H = size.h || wrap.clientHeight;
    if (W === 0 || H === 0) {
      let rafId = 0;
      const wait = () => {
        const w2 = wrap.clientWidth;
        const h2 = wrap.clientHeight;
        if (w2 > 0 && h2 > 0) {
          setSize({ w: w2, h: h2 });
        } else {
          rafId = requestAnimationFrame(wait);
        }
      };
      rafId = requestAnimationFrame(wait);
      return () => cancelAnimationFrame(rafId);
    }

    const nodes: NodeS[] = data.nodes.map((n) => ({
      ...n,
      x: W / 2 + (Math.random() - 0.5) * W * 0.7,
      y: H / 2 + (Math.random() - 0.5) * H * 0.7,
      vx: 0,
      vy: 0,
      degree: 0,
    }));
    const idx: Record<string, number> = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
    const edges = data.edges
      .filter((e) => idx[e.source] != null && idx[e.target] != null)
      .map((e) => ({ s: idx[e.source], t: idx[e.target] }));
    edges.forEach((e) => {
      nodes[e.s].degree++;
      nodes[e.t].degree++;
    });

    const state = {
      nodes,
      edges,
      W,
      H,
      transform: { k: 1, x: 0, y: 0 },
      alpha: 0.35,
      dragging: null as NodeS | null,
      pinned: null as NodeS | null,
    };
    const MAX_STEP = 6;

    function step(a: number) {
      const n = state.nodes;
      for (let i = 0; i < n.length; i++) {
        for (let j = i + 1; j < n.length; j++) {
          const dx = n[j].x - n[i].x;
          const dy = n[j].y - n[i].y;
          const d2 = dx * dx + dy * dy + 0.01;
          const d = Math.sqrt(d2);
          const f = 1400 / d2;
          const fx = (dx / d) * f;
          const fy = (dy / d) * f;
          n[i].vx -= fx * a;
          n[i].vy -= fy * a;
          n[j].vx += fx * a;
          n[j].vy += fy * a;
        }
      }
      for (const e of state.edges) {
        const s = n[e.s];
        const t = n[e.t];
        // If either endpoint is pinned, skip the spring force — otherwise the
        // pinned node's fixed position would tow its neighbors toward it and
        // they'd pile up underneath the flashcard.
        if (state.pinned === s || state.pinned === t) continue;
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const f = (d - 70) * 0.04;
        const fx = (dx / d) * f;
        const fy = (dy / d) * f;
        s.vx += fx * a;
        s.vy += fy * a;
        t.vx -= fx * a;
        t.vy -= fy * a;
      }
      for (const p of n) {
        p.vx += (state.W / 2 - p.x) * 0.0012 * a;
        p.vy += (state.H / 2 - p.y) * 0.0012 * a;
        p.vx *= 0.78;
        p.vy *= 0.78;
        if (state.dragging !== p && state.pinned !== p) {
          const sp = Math.hypot(p.vx, p.vy);
          if (sp > MAX_STEP) {
            const k = MAX_STEP / sp;
            p.vx *= k;
            p.vy *= k;
          }
          p.x += p.vx;
          p.y += p.vy;
        } else if (state.pinned === p && state.dragging !== p) {
          // Pinned but not actively being dragged — kill residual momentum so
          // it doesn't creep when released.
          p.vx = 0;
          p.vy = 0;
        }
      }
    }

    for (let w = 0; w < 220; w++) step(1);
    for (const p of state.nodes) {
      p.vx = 0;
      p.vy = 0;
    }

    let raf = 0;
    function tick() {
      // Sync pin state from the selection ref each frame. Cheap, and avoids
      // plumbing a separate effect through to the sim closure.
      const selId = selectedIdRef.current;
      if (selId) {
        const selIdx = idx[selId];
        state.pinned = selIdx != null ? state.nodes[selIdx] : null;
      } else {
        state.pinned = null;
      }
      step(state.alpha);
      state.alpha *= 0.992;
      if (state.alpha < 0.02) state.alpha = 0.02;
      draw();
      raf = requestAnimationFrame(tick);
    }

    function draw() {
      if (!svg) return;
      const g = svg.querySelector("#scene") as SVGGElement | null;
      if (!g) return;
      const t = state.transform;
      g.setAttribute("transform", `translate(${t.x},${t.y}) scale(${t.k})`);
      const elines = svg.querySelectorAll<SVGLineElement>(".gedge");
      elines.forEach((el, i) => {
        const e = state.edges[i];
        if (!e) return;
        const s = state.nodes[e.s];
        const tn = state.nodes[e.t];
        el.setAttribute("x1", String(s.x));
        el.setAttribute("y1", String(s.y));
        el.setAttribute("x2", String(tn.x));
        el.setAttribute("y2", String(tn.y));
      });
      const enodes = svg.querySelectorAll<SVGGElement>(".gnode");
      enodes.forEach((el, i) => {
        const p = state.nodes[i];
        if (!p) return;
        el.setAttribute("transform", `translate(${p.x},${p.y})`);
      });

      // Position the flashcard alongside the selected node. Sticky: we only
      // re-anchor when the node leaves the card's current footprint, so the
      // card stays put while the user nudges the node around nearby.
      const card = cardRef.current;
      const selId = selectedIdRef.current;
      if (card && selId) {
        const selIdx = idx[selId];
        if (selIdx != null) {
          const p = state.nodes[selIdx];
          const sx = t.x + p.x * t.k;
          const sy = t.y + p.y * t.k;
          const cardW = card.offsetWidth || 300;
          const cardH = card.offsetHeight || 160;
          const pad = 24;

          const anchor = anchorRef.current;
          // Check if the node is still inside (or adjacent to) the current
          // card bounds. We keep a small buffer so the node can sit right on
          // the card edge without bouncing the anchor.
          const BUFFER = 16;
          let keep = false;
          if (anchor && anchor.id === selId) {
            keep =
              sx >= anchor.left - BUFFER &&
              sx <= anchor.left + cardW + BUFFER &&
              sy >= anchor.top - BUFFER &&
              sy <= anchor.top + cardH + BUFFER;
          }

          if (!keep) {
            const offsetRight = sx + pad + cardW <= state.W - 12;
            const left = offsetRight ? sx + pad : sx - pad - cardW;
            let top = sy - cardH / 2;
            if (top < 12) top = 12;
            if (top + cardH > state.H - 12) top = state.H - cardH - 12;
            anchorRef.current = {
              id: selId,
              left,
              top,
              tilt: offsetRight ? "-10deg" : "10deg",
            };
            card.style.setProperty("--cx", `${left}px`);
            card.style.setProperty("--cy", `${top}px`);
            card.style.setProperty("--tilt", offsetRight ? "-10deg" : "10deg");
          }
        }
      }
    }

    tick();

    let panning: { x: number; y: number; ox: number; oy: number } | null = null;
    let pressed: { x: number; y: number; node: NodeS | null } | null = null;

    function onDown(e: MouseEvent) {
      if (!svg) return;
      // Prevent the browser from starting a text selection as the drag leaves
      // the SVG and sweeps across HTML overlays (legend, stats, card).
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      const sx = (e.clientX - r.left - state.transform.x) / state.transform.k;
      const sy = (e.clientY - r.top - state.transform.y) / state.transform.k;
      let hitIdx = -1;
      for (let i = state.nodes.length - 1; i >= 0; i--) {
        const p = state.nodes[i];
        const r2 = (5 + Math.min(9, p.degree)) ** 2;
        if ((p.x - sx) ** 2 + (p.y - sy) ** 2 < r2 + 12) {
          hitIdx = i;
          break;
        }
      }
      pressed = {
        x: e.clientX,
        y: e.clientY,
        node: hitIdx >= 0 ? state.nodes[hitIdx] : null,
      };
      if (hitIdx >= 0) {
        state.dragging = state.nodes[hitIdx];
        state.alpha = 0.6;
      } else {
        panning = { x: e.clientX, y: e.clientY, ox: state.transform.x, oy: state.transform.y };
      }
    }

    function onMove(e: MouseEvent) {
      if (!svg) return;
      const r = svg.getBoundingClientRect();
      if (state.dragging) {
        state.dragging.x = (e.clientX - r.left - state.transform.x) / state.transform.k;
        state.dragging.y = (e.clientY - r.top - state.transform.y) / state.transform.k;
        state.dragging.vx = 0;
        state.dragging.vy = 0;
      } else if (panning) {
        state.transform.x = panning.ox + (e.clientX - panning.x);
        state.transform.y = panning.oy + (e.clientY - panning.y);
      } else {
        const sx = (e.clientX - r.left - state.transform.x) / state.transform.k;
        const sy = (e.clientY - r.top - state.transform.y) / state.transform.k;
        let hitIdx = -1;
        for (let i = state.nodes.length - 1; i >= 0; i--) {
          const p = state.nodes[i];
          const r2 = (5 + Math.min(9, p.degree)) ** 2;
          if ((p.x - sx) ** 2 + (p.y - sy) ** 2 < r2 + 8) {
            hitIdx = i;
            break;
          }
        }
        if (hitIdx >= 0) {
          const n = state.nodes[hitIdx];
          setHover(n.id);
          setTt({ x: e.clientX - r.left + 14, y: e.clientY - r.top + 14, n });
        } else {
          setHover(null);
          setTt(null);
        }
      }
    }

    function onUp(e: MouseEvent) {
      // Short click — select node for flashcard, or dismiss on empty space.
      if (pressed && Math.hypot(e.clientX - pressed.x, e.clientY - pressed.y) < 4) {
        if (pressed.node) {
          const n = pressed.node;
          setSelection((cur) =>
            cur && cur.node.id === n.id
              ? cur
              : {
                  node: { id: n.id, title: n.title, layer: n.layer },
                  loading: true,
                  preview: "",
                  error: null,
                },
          );
        } else {
          setSelection(null);
        }
      }
      pressed = null;
      state.dragging = null;
      panning = null;
    }

    function onWheel(e: WheelEvent) {
      e.preventDefault();
      if (!svg) return;
      const r = svg.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const my = e.clientY - r.top;
      const factor = Math.exp(-e.deltaY * 0.0015);
      const newK = Math.max(0.4, Math.min(3, state.transform.k * factor));
      state.transform.x = mx - (mx - state.transform.x) * (newK / state.transform.k);
      state.transform.y = my - (my - state.transform.y) * (newK / state.transform.k);
      state.transform.k = newK;
    }

    svg.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      svg.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      svg.removeEventListener("wheel", onWheel);
    };
  }, [data, size.w, size.h]);

  // Highlight selected node's neighborhood (plus hover neighborhood).
  const highlight = useMemo(() => {
    const focus = selection?.node.id ?? hover;
    if (!focus) return null;
    const set = new Set([focus]);
    for (const e of data.edges) {
      if (e.source === focus) set.add(e.target);
      if (e.target === focus) set.add(e.source);
    }
    return set;
  }, [hover, selection?.node.id, data]);

  // Count of direct connections for the selected node.
  const connectionCount = useMemo(() => {
    if (!selection) return 0;
    const id = selection.node.id;
    let c = 0;
    for (const e of data.edges) if (e.source === id || e.target === id) c++;
    return c;
  }, [selection?.node.id, data]);

  function openSelected() {
    if (!selection || !brain) return;
    // Belt-and-suspenders: only real markdown files have a backing page.
    // Phantom nodes (unresolved wikilinks) would dead-end on "Page not found".
    if (!selection.node.id.endsWith(".md")) return;
    navigate("/app/brains", {
      state: { brainId: brain.id, pagePath: selection.node.id },
    });
  }

  return (
    <div className="graph-page" ref={wrapRef}>
      <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <radialGradient id="halo" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="oklch(0.62 0.15 260 / 0.18)" />
            <stop offset="100%" stopColor="oklch(0.62 0.15 260 / 0)" />
          </radialGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" />
          </filter>
        </defs>
        <g id="scene">
          {data.edges.map((e, i) => {
            const a =
              highlight && (!highlight.has(e.source) || !highlight.has(e.target)) ? 0.04 : 0.16;
            return (
              <line
                key={i}
                className="gedge"
                stroke="white"
                strokeOpacity={a}
                strokeWidth="0.6"
              />
            );
          })}
          {data.nodes.map((n, i) => {
            const dim = highlight && !highlight.has(n.id);
            const isSelected = selection?.node.id === n.id;
            const r =
              5 +
              Math.min(
                9,
                data.edges.filter((e) => e.source === n.id || e.target === n.id).length,
              );
            const color = layerColors[n.layer] || layerColors.wiki;
            return (
              <g
                key={i}
                className="gnode"
                style={{
                  opacity: dim ? 0.18 : 1,
                  transition: "opacity 200ms",
                  cursor: "pointer",
                }}
              >
                <circle r={r + 3} fill={color} opacity={isSelected ? 0.35 : 0.18} />
                <circle
                  r={r}
                  fill={color}
                  stroke={isSelected ? "white" : "oklch(0 0 0 / 0.2)"}
                  strokeWidth={isSelected ? 1.4 : 0.5}
                />
                {isSelected && (
                  <circle r={r + 2} fill="none" stroke={color} strokeWidth="1.2">
                    <animate
                      attributeName="r"
                      values={`${r + 2};${r + 14};${r + 2}`}
                      dur="1.8s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="0.9;0;0.9"
                      dur="1.8s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                {n.layer === "hot" && (
                  <circle r={r} fill="none" stroke={layerColors.hot} strokeWidth="1">
                    <animate
                      attributeName="r"
                      values={`${r};${r + 12};${r}`}
                      dur="2.4s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      values="0.7;0;0.7"
                      dur="2.4s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      <div className="graph-overlay graph-legend">
        <h4>Layers</h4>
        <div className="item">
          <span className="sw" style={{ background: layerColors.hot }}></span>
          <span className="lbl">hot</span>
          <span className="desc">in prompt</span>
        </div>
        <div className="item">
          <span className="sw" style={{ background: layerColors.index }}></span>
          <span className="lbl">index</span>
          <span className="desc">entry pts</span>
        </div>
        <div className="item">
          <span className="sw" style={{ background: layerColors.wiki }}></span>
          <span className="lbl">wiki</span>
          <span className="desc">notes</span>
        </div>
        <div className="item">
          <span className="sw" style={{ background: layerColors.raw }}></span>
          <span className="lbl">raw</span>
          <span className="desc">captures</span>
        </div>
      </div>

      <div className="graph-overlay graph-stats">
        <div className="pill">
          {data.nodes.length} <span className="v">NODES</span>
        </div>
        <div className="pill">
          {data.edges.length} <span className="v">EDGES</span>
        </div>
        <div className="pill">
          <span className="v">WHEEL</span> ZOOM · <span className="v">DRAG</span> PAN ·{" "}
          <span className="v">CLICK</span> PEEK
        </div>
      </div>

      {tt && (
        <div className="graph-tooltip" style={{ left: tt.x, top: tt.y }}>
          <div>{tt.n.title}</div>
          <div className="layer" style={{ color: layerColors[tt.n.layer] }}>
            {tt.n.layer.toUpperCase()}
          </div>
        </div>
      )}

      <div
        ref={cardRef}
        className={"node-flashcard" + (selection ? " open" : "")}
        style={{
          // Accent color of the card follows the node's layer.
          ["--card-accent" as string]: selection
            ? layerColors[selection.node.layer]
            : layerColors.wiki,
        }}
        aria-hidden={!selection}
      >
        {selection && (
          <>
            <div className="card-inner">
              <div className="card-head">
                <span
                  className="layer-chip"
                  style={{ color: layerColors[selection.node.layer] }}
                >
                  <span
                    className="dot"
                    style={{ background: layerColors[selection.node.layer] }}
                  />
                  {selection.node.layer.toUpperCase()}
                </span>
                <button
                  className="close"
                  onClick={() => setSelection(null)}
                  aria-label="Dismiss"
                  title="Dismiss"
                >
                  ×
                </button>
              </div>
              <h3 className="card-title">{selection.node.title}</h3>
              <div className="card-path">{selection.node.id}</div>
              <div className="card-preview">
                {selection.loading ? (
                  <span className="dim">Loading preview…</span>
                ) : selection.error ? (
                  <span className="dim">Preview unavailable.</span>
                ) : selection.preview ? (
                  selection.preview
                ) : (
                  <span className="dim">No preview text.</span>
                )}
              </div>
              <div className="card-meta">
                <span className="meta-pill">
                  <span className="v">{connectionCount}</span> CONN
                </span>
              </div>
              <button className="card-cta" onClick={openSelected}>
                Open page →
              </button>
            </div>
            <div className="card-shine" aria-hidden="true" />
            <div className="card-grid" aria-hidden="true" />
          </>
        )}
      </div>
    </div>
  );
}
