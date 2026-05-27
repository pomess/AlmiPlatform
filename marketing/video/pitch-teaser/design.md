# Disease360 — Pitch teaser design

Mood: cinematic obsidian glass, navy accent, HUD frames. Match the cockpit (apps/web/src/styles/tokens.css). Quiet but alive — restraint is the credibility signal. No gradient slop, no glassmorphism cliché.

## Palette (hex equivalents of the cockpit's oklch tokens)

| Token             | Hex       | Use                                |
|-------------------|-----------|------------------------------------|
| `--bg-void`       | `#0c0e14` | Deepest midnight, page bg          |
| `--bg-base`       | `#11141c` | Default surface                    |
| `--bg-surface`    | `#171a24` | Cards, panels                      |
| `--bg-elevated`   | `#1f2331` | Tooltip / dropdown                 |
| `--accent`        | `#5a6cff` | Greek navy — primary accent        |
| `--accent-bright` | `#8294ff` | Hover / glow apex                  |
| `--accent-deep`   | `#2c3a8a` | Halo, deep accent                  |
| `--text-primary`  | `#f1f3fa` | Primary copy                       |
| `--text-secondary`| `#b2b6c7` | Secondary copy                     |
| `--text-muted`    | `#777b8c` | Labels, eyebrows                   |
| `--border-hairline`| `rgba(255,255,255,0.06)` | Card stroke         |
| `--border-accent` | `rgba(132,148,255,0.55)` | HUD bracket         |
| `--c-success`     | `#7fd9a3` | Approve glow                       |
| `--c-danger`      | `#ff6b6b` | Deny / reject                      |
| `--layer-hot`     | `#ffa760` | Hot cache nodes                    |
| `--layer-wiki`    | `#c79bff` | Wiki nodes                         |
| `--layer-raw`     | `#7fc8ff` | Raw capture nodes                  |

## Typography

- **Display / headline** — `Space Grotesk`, weight 600 for body, weight 200 for "vs" tension type. Letter-spacing -0.04em on display. (Cockpit uses Geist; Space Grotesk is the closest video-ready substitute auto-embedded by HyperFrames.)
- **Mono / data / labels** — `JetBrains Mono`, weight 400. Used for eyebrows (uppercase, tracking 0.18em), wikilinks `[[ ]]`, audit log lines, timestamps.
- **No serifs.** Cockpit uses none.
- **Pairing tension:** Geist (humanist sans) vs Geist Mono (terminal). One register: editorial. Other register: machine. The product *is* that tension — drafts read like a CFO, but every action is logged like a server.

## Decorative motifs from the cockpit

- **HUD bracket frame** — 14px corner brackets, `border: 1px solid var(--border-accent)`, top-left + bottom-right only.
- **Aurora glow blob** — soft radial, `oklch(0.82 0.17 260 / 0.18)` core, blur 40px. Lives behind hero text; drifts.
- **HUD grid** — 56px square grid at `rgba(255,255,255,0.018)`, masked with radial gradient.
- **Scanlines** — repeating 2-3px horizontal lines, 1.2% opacity, mix-blend overlay.
- **Wikilink chip** — `[[name]]` with mono brackets at 60% opacity, navy fill `accent-faint`, hairline border.

## Motion language

- Cinema ease: `cubic-bezier(0.22, 0.61, 0.36, 1)` (matches `--ease-cinema` in cockpit).
- Entrances vary: blur-clear, letter-spacing collapse, fade-up, scale-from-0.96, stagger-cascade.
- Ambient: aurora drifts on a 12s sine, scanlines breathe, accent dot pulses at 1.6s.
- Transitions: cut-on-pulse for tense beats, blur-through for narrative beats, no slow dissolves.

## Do not

- Glassmorphism (frosted gradient cards). The cockpit doesn't use it; faking it cheapens the brand.
- Pastel gradients. We're obsidian + one navy, full stop.
- Centered floating text. Anchor to grid corners, use HUD frames.
- Cliché AI motifs: glowing brain, neural pulse rings, particles. We're a workspace, not Cortana.
- Personal-AI / second-brain language. Banned in marketing/hero.md.
