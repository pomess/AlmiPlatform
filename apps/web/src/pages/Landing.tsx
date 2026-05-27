// Almirall Platform — landing for the Bullseye competitive-intelligence cockpit.
// Reuses the existing Landing.css classes; swaps copy + preview for pharma.
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { LandingGlobeMock } from "../components/LandingGlobeMock";
import { LandingGraphDive } from "../components/LandingGraphDive";
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
            <span className="stack">Everything you need.</span>
            <span className="accent">In one place.</span>
          </h1>
          <p className="hero-sub">
            A unified competitive-intelligence platform for Almirall's dermatology franchise.
            Landscape maps, knowledge graphs, global dashboards — all connected, all live,
            all in one place.
          </p>
          <div className="hero-cta">
            <button className="enter-btn" type="button" onClick={handleOpenApp}>
              Open the Bullseye <span className="mono">→</span>
            </button>
            <a
              className="ghost"
              href="#section-1"
              onClick={(e) => {
                e.preventDefault();
                document
                  .getElementById("section-1")
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

      {/* SECTION 01 — Bullseye demo + value cards */}
      <section
        id="section-1"
        className="hero"
        style={{ minHeight: "auto", padding: "40px 24px 0", scrollMarginTop: 96 }}
      >
        <div className="preview-wrap" id="previewWrap">
          <div className="preview hud-frame" id="previewPanel">
            <div className="preview-body preview-body--snapshot">
              <img
                className="preview-bullseye-snapshot"
                src="/snapshots/bullseye-ad.png"
                alt="Bullseye — atopic dermatitis competitive landscape"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </section>

      <div className="section-head" style={{ marginTop: 40 }}>
        <h2>
          Every drug <em>in your sights.</em>
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

      {/* SECTION 02 — Dashboard globe showcase + deep dives */}
      <div className="section-2-dark">
      <div className="section-head" style={{ marginTop: 0, paddingTop: 80 }}>
        <h2>
          The three things <em>your franchise team</em> will use weekly.
        </h2>
        <div className="meta">SECTION 02 / 03</div>
      </div>

      <section className="strip">
        <div className="strip-inner globe-showcase-wrap">
          <article className="globe-showcase hud-frame fade-up">
            <div className="globe-showcase-text">
              <div className="ix">DASHBOARD · GLOBAL VIEW</div>
              <h3>The competitive map. Pinned.</h3>
              <p>
                Almirall HQ at the centre. Every pharma running on Spanish soil — red on the
                globe. Pull out to Europe and watch the whole field at once. Ask about any
                drug or company and the camera flies to where it lives.
              </p>
            </div>
            <div className="globe-showcase-visual">
              <LandingGlobeMock />
            </div>
          </article>
        </div>
      </section>
      </div>


      {/* KNOWLEDGE GRAPH — static SVG mock */}
      <LandingGraphDive />

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
