// Almirall Platform — landing for the Bullseye competitive-intelligence cockpit.
// Reuses the existing Landing.css classes; swaps copy + preview for pharma.
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./Landing.css";

const BOOT_MESSAGES = [
  "almirall :: bullseye · 12 assets tracked · 2 indications",
  "almirall :: ebglyss · IL-13 · EU rights · approved 2024",
  "almirall :: HS landscape · 3 approved · 3 in late-stage trials",
  "almirall :: next readout · sonelokimab VELA Ph III · watching",
];

export function Landing() {
  const navigate = useNavigate();

  const handleOpenApp = () => {
    navigate("/app");
  };

  useEffect(() => {
    document.body.classList.add("on-landing");
    return () => {
      document.body.classList.remove("on-landing");
    };
  }, []);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ---------- parallax ----------
    const wrap = document.getElementById("previewWrap");
    const panel = document.getElementById("previewPanel");
    const floats = document.querySelectorAll<HTMLElement>(".float");
    const hero = document.querySelector<HTMLElement>(".hero");

    let mx = 0;
    let my = 0;
    let tx = 0;
    let ty = 0;
    let scrollY = window.scrollY;
    let raf = 0;
    let running = false;
    let heroVisible = true;
    const EPS = 0.0005;

    function start() {
      if (running || reduceMotion || document.hidden || !heroVisible) return;
      running = true;
      raf = requestAnimationFrame(loop);
    }
    function stop() {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    }

    function onMove(e: MouseEvent) {
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      tx = (e.clientX - cx) / cx;
      ty = (e.clientY - cy) / cy;
      start();
    }
    function onScroll() {
      scrollY = window.scrollY;
      start();
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });

    function loop() {
      const dx = tx - mx;
      const dy = ty - my;
      mx += dx * 0.06;
      my += dy * 0.06;
      if (panel && wrap) {
        const rect = wrap.getBoundingClientRect();
        const ry = mx * 4;
        const rx = -my * 3;
        const ty2 = Math.max(-40, Math.min(40, (rect.top - 200) * -0.04));
        panel.style.transform = `translateY(${ty2}px) rotateX(${rx}deg) rotateY(${ry}deg)`;
      }
      floats.forEach((el, i) => {
        const depth = parseFloat(el.style.getPropertyValue("--d")) || 16;
        const px = mx * depth;
        const py = my * depth + scrollY * 0.04 * (i % 2 === 0 ? -1 : 1);
        el.style.transform = `translate(${px}px, ${py}px)`;
      });
      if (Math.abs(dx) < EPS && Math.abs(dy) < EPS) {
        stop();
        return;
      }
      raf = requestAnimationFrame(loop);
    }

    const heroIo = hero
      ? new IntersectionObserver(
          (entries) => {
            heroVisible = entries[0]?.isIntersecting ?? true;
            if (heroVisible) start();
            else stop();
          },
          { threshold: 0 },
        )
      : null;
    if (hero && heroIo) heroIo.observe(hero);

    function onVisibility() {
      if (document.hidden) stop();
      else start();
    }
    document.addEventListener("visibilitychange", onVisibility);

    if (!reduceMotion) start();

    // ---------- fade-up ----------
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.15 },
    );
    document.querySelectorAll(".fade-up").forEach((el) => io.observe(el));

    // ---------- boot caret ----------
    let bootI = 0;
    const bootEl = document.getElementById("boot");
    const bootInt = window.setInterval(() => {
      if (!bootEl) return;
      bootI = (bootI + 1) % BOOT_MESSAGES.length;
      bootEl.style.opacity = "0.3";
      setTimeout(() => {
        bootEl.textContent = BOOT_MESSAGES[bootI];
        bootEl.style.opacity = "1";
      }, 220);
    }, 3600);

    return () => {
      stop();
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("scroll", onScroll);
      document.removeEventListener("visibilitychange", onVisibility);
      heroIo?.disconnect();
      io.disconnect();
      clearInterval(bootInt);
    };
  }, []);

  return (
    <div className="landing-stage">
      <header className="top">
        <div className="brand">
          <img className="mark" src="/logos/almirall_logo_navy.svg" alt="Almirall" />
        </div>
        <div className="top-right">
          <span className="pill">
            <span
              className="dot dot-pulse"
              style={{
                background: "var(--c-success)",
                boxShadow: "0 0 8px oklch(0.78 0.13 155 / 0.6)",
              }}
            ></span>{" "}
            COMPETITIVE INTELLIGENCE PLATFORM
          </span>
          <button className="top-link mono" type="button" onClick={handleOpenApp}>
            Open platform →
          </button>
          <a className="enter-btn" href="#preview">
            See the Bullseye →
          </a>
        </div>
      </header>

      {/* HERO */}
      <section className="hero">
        <div className="hero-aurora"></div>
        <div className="hero-aurora b"></div>
        <div className="hero-grid"></div>

        <div
          className="float"
          style={{ left: "6%", top: "26%", ["--d" as never]: 18 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">●</span> Atopic Dermatitis ·{" "}
            <span className="num mono">6 assets tracked</span>
          </span>
        </div>
        <div
          className="float"
          style={{ right: "8%", top: "22%", ["--d" as never]: 24 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">▲</span> Hidradenitis Suppurativa ·{" "}
            <span className="num mono">6 assets · 3 in trial</span>
          </span>
        </div>
        <div
          className="float"
          style={{ left: "12%", top: "64%", ["--d" as never]: 12 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">◆</span> Ebglyss · IL-13 ·{" "}
            <span className="num mono">EU rights · Almirall</span>
          </span>
        </div>
        <div
          className="float"
          style={{ right: "14%", top: "70%", ["--d" as never]: 30 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">◇</span> Late-stage readouts ·{" "}
            <span className="num mono">3 catalysts watched</span>
          </span>
        </div>
        <div className="float-line" style={{ left: 0, right: "60%", top: "38%" }}></div>
        <div className="float-line" style={{ left: "55%", right: 0, top: "58%" }}></div>

        <div className="hero-inner">
          <div className="eyebrow">
            <span className="live-dot"></span>
            <span className="mono">ALMIRALL · DERMATOLOGY COMPETITIVE INTELLIGENCE</span>
          </div>
          <h1 className="hero-title">
            <span className="stack">Every drug. Every phase.</span>
            <span className="accent">One bullseye.</span>
          </h1>
          <p className="hero-sub">
            A live competitive-intelligence cockpit for Almirall's dermatology franchise. Track
            every biologic and small molecule across atopic dermatitis and hidradenitis
            suppurativa — rendered as a single radial map you can read in seconds.
          </p>
          <div className="hero-cta">
            <button className="enter-btn" type="button" onClick={handleOpenApp}>
              Open the Bullseye <span className="mono">→</span>
            </button>
            <a
              className="ghost"
              href="#preview"
              onClick={(e) => {
                e.preventDefault();
                document
                  .getElementById("preview")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              <span className="mono">See the live map</span>
              <kbd>↓</kbd>
            </a>
          </div>

          <div className="boot mono" id="boot">
            12 assets · 2 indications · concentric phase rings · drill into any drug
          </div>
        </div>
      </section>

      {/* LIVE PREVIEW */}
      <section className="hero" id="preview" style={{ minHeight: "auto", padding: "0 24px 80px" }}>
        <div className="preview-wrap" id="previewWrap">
          <div className="preview hud-frame" id="previewPanel">
            <div className="preview-bar">
              <div className="preview-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <div className="url">
                <span className="accent">platform</span>.almirall /{" "}
                <span className="mono">bullseye</span>
              </div>
              <div className="corner mono">DEMO PREVIEW</div>
            </div>

            <div className="pv-top">
              <div className="pv-top-left">
                <span className="pv-mark">A</span>
                <span className="pv-wordmark">ALMIRALL</span>
                <span className="pv-corner">
                  <span className="pv-live"></span> ONLINE · COMPETITIVE INTEL
                </span>
              </div>
              <nav className="pv-nav-pill">
                <button>Chat</button>
                <button>Dashboard</button>
                <button className="active">Bullseye</button>
                <button>Graph</button>
                <button>Approvals</button>
                <button>Brains</button>
                <button>Settings</button>
              </nav>
              <div className="pv-top-right">
                <span className="pv-brain-pill">
                  <span
                    className="pv-swatch"
                    style={{ background: "var(--accent)" }}
                  ></span>
                  <span className="pv-brain-lbl">INDICATION</span>
                  <span className="pv-brain-name">Atopic Dermatitis</span>
                  <span className="pv-caret">▾</span>
                </span>
              </div>
            </div>

            <div
              className="preview-body"
              style={{ display: "grid", placeItems: "center", padding: "32px 40px 48px" }}
            >
              <div
                style={{
                  display: "grid",
                  placeItems: "center",
                  width: "100%",
                  maxWidth: 720,
                  aspectRatio: "1 / 1",
                  position: "relative",
                }}
              >
                <svg viewBox="0 0 100 100" style={{ width: "100%", height: "100%" }}>
                  <defs>
                    <radialGradient id="bullsg" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="oklch(0.82 0.16 175 / 0.22)" />
                      <stop offset="70%" stopColor="oklch(0.82 0.16 175 / 0)" />
                    </radialGradient>
                  </defs>
                  <circle cx="50" cy="50" r="50" fill="url(#bullsg)" />
                  {[9, 18, 27, 36, 45].map((r) => (
                    <circle
                      key={r}
                      cx="50"
                      cy="50"
                      r={r}
                      fill="none"
                      stroke="oklch(1 0 0 / 0.08)"
                      strokeWidth="0.25"
                    />
                  ))}
                  {[
                    { brand: "Dupixent", company: "Sanofi", angle: -90, r: 9, color: "oklch(0.74 0.18 50)" },
                    { brand: "Ebglyss", company: "Almirall", angle: -30, r: 9, color: "oklch(0.82 0.16 175)", almirall: true },
                    { brand: "Adbry", company: "LEO", angle: 30, r: 9, color: "oklch(0.74 0.18 50)" },
                    { brand: "Nemluvio", company: "Galderma", angle: 90, r: 9, color: "oklch(0.74 0.18 50)" },
                    { brand: "Rinvoq", company: "AbbVie", angle: 150, r: 9, color: "oklch(0.84 0.16 90)" },
                    { brand: "Cibinqo", company: "Pfizer", angle: 210, r: 9, color: "oklch(0.84 0.16 90)" },
                    { brand: "Ph II asset", company: "—", angle: -60, r: 27, color: "oklch(0.84 0.16 90)" },
                    { brand: "Ph III asset", company: "—", angle: 60, r: 18, color: "oklch(0.74 0.18 50)" },
                  ].map((d) => {
                    const rad = (d.angle * Math.PI) / 180;
                    const x = 50 + d.r * Math.cos(rad);
                    const y = 50 + d.r * Math.sin(rad);
                    return (
                      <g key={d.brand + d.angle}>
                        {d.almirall && (
                          <circle cx={x} cy={y} r="2.6" fill="none" stroke="var(--accent-bright)" strokeWidth="0.4" opacity="0.6" />
                        )}
                        <circle cx={x} cy={y} r="1.5" fill={d.color} />
                      </g>
                    );
                  })}
                  <text x="50" y="50.5" textAnchor="middle" fontSize="3" fill="oklch(1 0 0 / 0.5)" fontFamily="var(--font-mono)" letterSpacing="0.3">
                    AD
                  </text>
                  {["Approved", "Phase III", "Phase II", "Phase I", "Preclinical"].map((p, i) => (
                    <text
                      key={p}
                      x="50"
                      y={50 - [9, 18, 27, 36, 45][i] + 1.5}
                      textAnchor="middle"
                      fontSize="1.6"
                      fill="oklch(1 0 0 / 0.35)"
                      fontFamily="var(--font-mono)"
                      letterSpacing="0.15"
                    >
                      {p.toUpperCase()}
                    </text>
                  ))}
                </svg>
                <div
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    textAlign: "center",
                    fontFamily: "var(--font-mono)",
                    fontSize: 10.5,
                    color: "var(--text-faint)",
                    letterSpacing: "0.16em",
                  }}
                >
                  6 ASSETS · 6 COMPANIES · ATOPIC DERMATITIS{" "}
                  <span style={{ color: "var(--accent)" }}>· EBGLYSS HIGHLIGHTED</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* VALUE STRIP */}
      <div className="section-head" style={{ marginTop: 40 }}>
        <h2>
          Built for the <em>franchises Almirall actually runs.</em>
        </h2>
        <div className="meta">SECTION 01 / 03</div>
      </div>

      <section className="strip">
        <div className="strip-inner">
          <article className="feat hud-frame fade-up">
            <div className="ix">01 · RADIAL LANDSCAPE</div>
            <h3>Phase rings, at a glance</h3>
            <p>
              Concentric rings for Approved, Phase III, II, I, Preclinical. Companies fan around
              the perimeter. One look tells you who's where — no scrolling tables.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">02 · ALMIRALL HIGHLIGHTED</div>
            <h3>Your assets, instantly visible</h3>
            <p>
              Ebglyss and any future Almirall asset wear a navy halo. You always see where you
              stand against Sanofi, Lilly, AbbVie, LEO, Galderma, and the late-stage challengers.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">03 · DRILL INTO ANY DRUG</div>
            <h3>One click, full dossier</h3>
            <p>
              Click a dot — target, modality, route, highest phase, first approval, development
              timeline, notes. Sourced once, kept current, and ready for every cross-functional
              review.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">04 · TWO INDICATIONS, ONE SHELL</div>
            <h3>AD today. HS today. More tomorrow.</h3>
            <p>
              Atopic dermatitis and hidradenitis suppurativa are wired in. Psoriasis, prurigo,
              alopecia areata — same shell, same map, same drill-down. Add an indication, not a
              tool.
            </p>
          </article>
        </div>
      </section>

      {/* DEEP DIVES */}
      <div className="section-head" style={{ marginTop: 80 }}>
        <h2>
          The three things <em>your franchise team</em> will use weekly.
        </h2>
        <div className="meta">SECTION 02 / 03</div>
      </div>

      <section className="deep">
        <div className="deep-inner">
          <div className="deep-row">
            <div className="text fade-up">
              <span className="eyebrow">01 — THE LANDSCAPE, READABLE</span>
              <h3>
                Every competitor,{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>placed</em>.
              </h3>
              <p>
                The Bullseye places every tracked asset by company (angle) and by clinical stage
                (radius). No more spreadsheets that go stale the day a readout drops — open the
                map, see the move.
              </p>
              <ul className="bullets">
                <li>Concentric rings: Approved → Phase III → II → I → Preclinical.</li>
                <li>Companies fan around the perimeter — no two collide.</li>
                <li>Color-coded by modality: mAb, small molecule, nanobody, affibody.</li>
              </ul>
            </div>
            <div className="visual hud-frame fade-up">
              <div className="eyebrow" style={{ marginBottom: 14 }}>
                INDICATION · HIDRADENITIS SUPPURATIVA
              </div>
              <div
                style={{
                  display: "grid",
                  gap: 10,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--text-secondary)",
                }}
              >
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>●</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>Humira</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>· AbbVie · TNF-α · 2015</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>●</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>Cosentyx</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>· Novartis · IL-17A · 2023</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>●</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>Bimzelx</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>· UCB · IL-17A/F · 2024</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--accent)" }}>◐</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>Sonelokimab</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>· MoonLake · Ph III</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--accent)" }}>◐</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>Povorcitinib</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>· Incyte · oral JAK1 · Ph III</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10, color: "var(--accent)" }}>
                  <span>⋯</span>
                  <span>3 approved · 3 in late-stage · landscape moving fast</span>
                </div>
              </div>
              <div
                style={{
                  position: "absolute",
                  right: 16,
                  bottom: 16,
                  fontFamily: "var(--font-mono)",
                  fontSize: 10.5,
                  color: "var(--text-faint)",
                  letterSpacing: "0.16em",
                }}
              >
                INDICATION · HS · 6 ASSETS
              </div>
            </div>
          </div>

          <div className="deep-row flip">
            <div className="visual hud-frame fade-up" style={{ padding: 20 }}>
              <div className="eyebrow" style={{ marginBottom: 14 }}>
                ASSET DETAIL · EBGLYSS
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                <div className="approval-mini pending">
                  <div className="row1">
                    <span className="tool">Ebglyss · lebrikizumab</span>
                    <span className="countdown mono">APPROVED 2024</span>
                  </div>
                  <div className="rationale">
                    IL-13 selective monoclonal antibody. Almirall holds EU commercial rights;
                    Eli Lilly retains US/RoW. Positioned on Q4 maintenance dosing vs Dupixent's
                    Q2 schedule.
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className="chip chip-success">Approved · EU + US</span>
                    <span className="chip">SC · adults & adolescents</span>
                    <span className="chip chip-accent">Almirall franchise</span>
                  </div>
                  <div className="actions">
                    <button className="b">Compare to Dupixent</button>
                    <button className="b approve">Open dossier →</button>
                  </div>
                </div>
                <div className="approval-mini">
                  <div className="row1">
                    <span className="tool" style={{ color: "var(--text-secondary)" }}>
                      Adjacent · Adbry / Adtralza (LEO Pharma)
                    </span>
                    <span
                      className="mono"
                      style={{ color: "var(--text-muted)", fontSize: 11 }}
                    >
                      IL-13 · APPROVED 2021
                    </span>
                  </div>
                  <div className="rationale" style={{ color: "var(--text-muted)" }}>
                    Same target, earlier launch. Direct head-to-head on AD durability and itch
                    control endpoints.
                  </div>
                </div>
              </div>
            </div>
            <div className="text fade-up">
              <span className="eyebrow">02 — DRILL INTO ANY ASSET</span>
              <h3>
                A dossier{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>per dot</em>.
              </h3>
              <p>
                Click any drug on the Bullseye and a full panel slides in: target, mechanism,
                route, highest phase, first approval, full development timeline, and the notes
                that matter for positioning.
              </p>
              <ul className="bullets">
                <li>Modality, target, route — the metadata your team already asks for.</li>
                <li>Phase timeline showing past, current, and what's still ahead.</li>
                <li>Notes capture the qualitative edge — boxed warnings, label expansions, mechanism nuances.</li>
              </ul>
            </div>
          </div>

          <div className="deep-row">
            <div className="text fade-up">
              <span className="eyebrow">03 — THE FRANCHISE MAP</span>
              <h3>
                The shape of{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>
                  a therapeutic area.
                </em>
              </h3>
              <p>
                Every approved drug, every late-stage challenger, every preclinical signal —
                arranged by company and by phase. Drop into one indication and the rest of the
                portfolio fades. Where Almirall stands becomes a position, not a story.
              </p>
              <ul className="bullets">
                <li>
                  <span style={{ color: "var(--layer-hot)" }}>●</span> &nbsp; mAb — the dominant
                  modality across both indications.
                </li>
                <li>
                  <span style={{ color: "var(--layer-index)" }}>●</span> &nbsp; small molecule —
                  oral JAKs, label-constrained.
                </li>
                <li>
                  <span style={{ color: "var(--layer-wiki)" }}>●</span> &nbsp; nanobody — emerging
                  late-stage challenger format.
                </li>
                <li>
                  <span style={{ color: "var(--layer-raw)" }}>●</span> &nbsp; affibody — small
                  Ph II reads, mixed signals.
                </li>
              </ul>
            </div>
            <div
              className="visual hud-frame fade-up"
              style={{ display: "grid", placeItems: "center" }}
            >
              <svg className="graph-mock" viewBox="0 0 480 320" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <radialGradient id="rg" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="oklch(0.82 0.16 175 / 0.18)" />
                    <stop offset="60%" stopColor="oklch(0.82 0.16 175 / 0)" />
                  </radialGradient>
                </defs>
                <g transform="translate(24, 0) scale(0.9, 0.85)">
                  <circle cx="240" cy="160" r="200" fill="url(#rg)" />
                  {[40, 80, 120, 160, 200].map((r) => (
                    <circle
                      key={r}
                      cx="240"
                      cy="160"
                      r={r}
                      fill="none"
                      stroke="oklch(1 0 0 / 0.08)"
                      strokeWidth="0.7"
                    />
                  ))}
                  <g>
                    <circle cx="240" cy="80" r="6" fill="var(--layer-hot)" />
                    <circle cx="320" cy="100" r="6" fill="var(--accent)" />
                    <circle cx="320" cy="220" r="6" fill="var(--layer-hot)" />
                    <circle cx="240" cy="240" r="6" fill="var(--layer-hot)" />
                    <circle cx="160" cy="220" r="6" fill="var(--layer-index)" />
                    <circle cx="160" cy="100" r="6" fill="var(--layer-index)" />
                    <circle cx="380" cy="160" r="5" fill="var(--layer-hot)" />
                    <circle cx="100" cy="160" r="5" fill="var(--layer-wiki)" />
                    <circle cx="240" cy="40" r="4" fill="var(--layer-index)" />
                    <circle cx="380" cy="60" r="4" fill="var(--layer-raw)" />
                  </g>
                  <circle
                    cx="320"
                    cy="100"
                    r="6"
                    fill="none"
                    stroke="var(--accent-bright)"
                    strokeWidth="1"
                  >
                    <animate
                      attributeName="r"
                      values="6;14;6"
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
                </g>
                <text
                  x="240"
                  y="312"
                  textAnchor="middle"
                  fill="var(--text-faint)"
                  fontFamily="var(--font-mono)"
                  fontSize="9"
                  letterSpacing="2"
                >
                  12 ASSETS · 2 INDICATIONS · ALMIRALL FRANCHISE{" "}
                  <tspan fill="var(--accent)">· EBGLYSS HIGHLIGHTED</tspan>
                </text>
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <div className="section-head" style={{ marginTop: 80 }}>
        <h2>Open the platform.</h2>
        <div className="meta">SECTION 03 / 03</div>
      </div>
      <section style={{ padding: "60px 24px 0", display: "grid", placeItems: "center" }}>
        <div
          className="card hud-frame"
          style={{
            padding: 56,
            maxWidth: 980,
            width: "100%",
            textAlign: "center",
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div className="aurora" style={{ left: -200, top: -200 }}></div>
          <div className="aurora" style={{ right: -200, bottom: -200 }}></div>
          <div className="eyebrow" style={{ marginBottom: 18 }}>
            COMPETITIVE INTEL · ASSET DRILL-DOWN · TWO INDICATIONS WIRED
          </div>
          <h2
            style={{
              margin: "0 0 14px",
              fontSize: "clamp(32px, 5vw, 56px)",
              fontWeight: 500,
              letterSpacing: "-0.025em",
            }}
          >
            See the dermatology landscape.
          </h2>
          <p
            style={{
              margin: "0 auto 32px",
              maxWidth: 540,
              color: "var(--text-secondary)",
              fontSize: 16,
              lineHeight: 1.55,
            }}
          >
            Atopic dermatitis and hidradenitis suppurativa, end-to-end. Open the Bullseye and
            click any dot to drill into the asset behind it.
          </p>
          <button
            className="enter-btn"
            type="button"
            onClick={handleOpenApp}
            style={{ height: 40, padding: "0 22px", fontSize: 13.5 }}
          >
            Open the platform
            <span className="mono" style={{ opacity: 0.7 }}>
              →
            </span>
          </button>
        </div>
      </section>

      <footer>
        <div className="row">
          <div>
            <span className="mono">© 2026 ALMIRALL</span>
          </div>
          <div className="links">
            <a href="#preview">See the Bullseye</a>
          </div>
          <div className="mono">ALMIRALL · COMPETITIVE INTELLIGENCE PLATFORM</div>
        </div>
      </footer>
    </div>
  );
}
