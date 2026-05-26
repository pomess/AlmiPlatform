// Knowledge graph — static SVG mock that mirrors the cockpit's live
// graph view. Two indication hubs (AD, HS) with their drug/target/
// company satellites; layout is hand-tuned for visual balance, edges
// drawn with a subtle gradient + bloom so the section reads as a
// cinematic snapshot rather than a flat diagram.
type Layer = "hot" | "index" | "wiki" | "raw";
type Node = { id: string; label: string; layer: Layer; x: number; y: number; r: number };

// 100 × 60 viewBox.
const NODES: Node[] = [
  // ---- Indications (huge, central spine) ----
  { id: "ad", label: "Atopic Dermatitis", layer: "index", x: 35, y: 30, r: 5.5 },
  { id: "hs", label: "Hidradenitis Suppurativa", layer: "index", x: 70, y: 30, r: 5.5 },

  // ---- AD orbit (left) ----
  // Almirall asset — bigger, hot
  { id: "ebglyss", label: "Ebglyss", layer: "hot", x: 22, y: 16, r: 3.2 },
  { id: "almirall", label: "Almirall", layer: "hot", x: 12, y: 12, r: 3.2 },
  { id: "lebrikizumab", label: "lebrikizumab", layer: "raw", x: 22, y: 8, r: 1.8 },
  { id: "il13", label: "IL-13", layer: "raw", x: 32, y: 14, r: 2.0 },

  { id: "dupixent", label: "Dupixent", layer: "wiki", x: 14, y: 28, r: 2.4 },
  { id: "sanofi", label: "Sanofi", layer: "wiki", x: 4, y: 30, r: 2.0 },
  { id: "il4ra", label: "IL-4Rα", layer: "raw", x: 14, y: 36, r: 1.8 },

  { id: "rinvoq", label: "Rinvoq", layer: "wiki", x: 26, y: 46, r: 2.4 },
  { id: "abbvie", label: "AbbVie", layer: "wiki", x: 18, y: 52, r: 2.2 },
  { id: "jak1", label: "JAK1", layer: "raw", x: 32, y: 52, r: 1.8 },

  { id: "cibinqo", label: "Cibinqo", layer: "wiki", x: 8, y: 46, r: 2.0 },
  { id: "pfizer", label: "Pfizer", layer: "wiki", x: 4, y: 50, r: 2.0 },

  { id: "adbry", label: "Adbry", layer: "wiki", x: 32, y: 22, r: 2.0 },
  { id: "leo", label: "LEO Pharma", layer: "wiki", x: 38, y: 18, r: 2.0 },

  { id: "nemluvio", label: "Nemluvio", layer: "wiki", x: 36, y: 38, r: 2.0 },
  { id: "galderma", label: "Galderma", layer: "wiki", x: 42, y: 42, r: 2.0 },

  // ---- HS orbit (right) ----
  { id: "humira", label: "Humira", layer: "wiki", x: 78, y: 14, r: 2.6 },
  { id: "tnfa", label: "TNF-α", layer: "raw", x: 86, y: 10, r: 1.8 },

  { id: "cosentyx", label: "Cosentyx", layer: "wiki", x: 88, y: 26, r: 2.4 },
  { id: "novartis", label: "Novartis", layer: "wiki", x: 96, y: 22, r: 2.2 },

  { id: "bimzelx", label: "Bimzelx", layer: "wiki", x: 90, y: 38, r: 2.4 },
  { id: "ucb", label: "UCB", layer: "wiki", x: 96, y: 44, r: 2.0 },
  { id: "il17af", label: "IL-17A/F", layer: "raw", x: 80, y: 44, r: 1.8 },

  { id: "sonelokimab", label: "Sonelokimab", layer: "raw", x: 76, y: 50, r: 2.0 },
  { id: "moonlake", label: "MoonLake", layer: "wiki", x: 70, y: 54, r: 2.0 },

  { id: "phase3", label: "Phase III", layer: "index", x: 52, y: 50, r: 2.6 },
];

const EDGES: [string, string][] = [
  // AD ↔ assets
  ["ad", "ebglyss"], ["ad", "dupixent"], ["ad", "rinvoq"], ["ad", "cibinqo"],
  ["ad", "adbry"], ["ad", "nemluvio"],
  ["ebglyss", "almirall"], ["ebglyss", "lebrikizumab"], ["ebglyss", "il13"],
  ["lebrikizumab", "il13"], ["adbry", "il13"],
  ["dupixent", "sanofi"], ["dupixent", "il4ra"],
  ["rinvoq", "abbvie"], ["rinvoq", "jak1"],
  ["cibinqo", "pfizer"], ["cibinqo", "jak1"],
  ["nemluvio", "galderma"],
  ["adbry", "leo"],
  // HS ↔ assets
  ["hs", "humira"], ["hs", "cosentyx"], ["hs", "bimzelx"], ["hs", "sonelokimab"],
  ["humira", "tnfa"], ["humira", "abbvie"],
  ["cosentyx", "novartis"], ["cosentyx", "il17af"],
  ["bimzelx", "ucb"], ["bimzelx", "il17af"],
  ["sonelokimab", "moonlake"], ["sonelokimab", "il17af"],
  // Bridges
  ["ad", "hs"],
  ["phase3", "sonelokimab"], ["phase3", "ebglyss"],
];

const LAYER_COLOR: Record<Layer, string> = {
  // Tuned for legibility on the light landing surface — slightly darker
  // and more saturated than the cockpit values so they don't wash out.
  hot: "oklch(0.55 0.15 175)",       // Almirall mint — pops as "yours"
  index: "oklch(0.62 0.16 60)",      // amber — indication anchors
  wiki: "oklch(0.55 0.16 295)",      // violet — companies / brand drugs
  raw: "oklch(0.58 0.13 235)",       // sky — atomic facts (targets, INNs)
};

export function LandingGraphDive() {
  const nodeIndex = new Map(NODES.map((n) => [n.id, n] as const));

  return (
    <section className="kg-section">
      <div className="kg-text">
        <div className="ix">KNOWLEDGE GRAPH</div>
        <h3>Every fact, linked.</h3>
        <p>
          Drugs, targets, mechanisms, companies, indications — every entity
          in your franchise wired into a living graph.
        </p>
      </div>

      <div className="kg-stage">
        <svg
          className="kg-svg"
          viewBox="0 0 100 60"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            {/* Soft mint vignette behind the entire graph */}
            <radialGradient id="kg-vignette" cx="50%" cy="50%" r="60%">
              <stop offset="0%" stopColor="oklch(0.55 0.15 175 / 0.18)" />
              <stop offset="80%" stopColor="oklch(0.55 0.15 175 / 0)" />
            </radialGradient>
            {/* Subtle mint-tinted edge gradient that brightens at ends */}
            <linearGradient id="kg-edge" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="oklch(0.65 0.13 175 / 0.10)" />
              <stop offset="50%" stopColor="oklch(0.78 0.14 175 / 0.32)" />
              <stop offset="100%" stopColor="oklch(0.65 0.13 175 / 0.10)" />
            </linearGradient>
            {/* Bloom filter applied to nodes — produces a halo around the
                solid disc so the graph reads as luminous. */}
            <filter id="kg-bloom" x="-100%" y="-100%" width="300%" height="300%">
              <feGaussianBlur stdDeviation="0.6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Background vignette */}
          <ellipse cx="50" cy="32" rx="58" ry="32" fill="url(#kg-vignette)" />

          {/* Edges */}
          <g className="kg-edges">
            {EDGES.map(([a, b], i) => {
              const A = nodeIndex.get(a);
              const B = nodeIndex.get(b);
              if (!A || !B) return null;
              return (
                <line
                  key={i}
                  x1={A.x}
                  y1={A.y}
                  x2={B.x}
                  y2={B.y}
                  className="kg-edge"
                  stroke="url(#kg-edge)"
                />
              );
            })}
          </g>

          {/* Nodes — outer halo, inner ring, then crisp dot */}
          <g className="kg-nodes">
            {NODES.map((n) => {
              const color = LAYER_COLOR[n.layer];
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x}, ${n.y})`}
                  className={`kg-node kg-node--${n.layer}`}
                >
                  {/* Outer soft halo */}
                  <circle
                    r={n.r * 2.2}
                    fill={color}
                    opacity="0.10"
                    filter="url(#kg-bloom)"
                  />
                  {/* Mid ring */}
                  <circle
                    r={n.r}
                    fill="none"
                    stroke={color}
                    strokeWidth="0.35"
                    opacity="0.75"
                  />
                  {/* Solid dot */}
                  <circle r={n.r * 0.55} fill={color} />
                  {/* Label */}
                  <text
                    x={0}
                    y={n.r + 2.2}
                    textAnchor="middle"
                    className="kg-label"
                  >
                    {n.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}
