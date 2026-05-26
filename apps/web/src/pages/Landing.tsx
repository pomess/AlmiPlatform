// signkairos.com landing — copy aligned to marketing/hero.md (fractional-CFO buyer).
// CSS lives next to this file in Landing.css.
// Scripts (parallax, fade-up, boot caret) are reimplemented as effects.
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./Landing.css";

const BOOT_MESSAGES = [
  "kairos :: ready · 6 client engagements · all approvals current",
  "kairos :: audit log · 1,284 entries · last export 4 days ago",
  "kairos :: 2 board packs in draft · awaiting your sign-off",
  "kairos :: per-client memory · zero cross-references this month",
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
      // settle: stop the loop when motion is below a perceptible threshold
      if (Math.abs(dx) < EPS && Math.abs(dy) < EPS) {
        stop();
        return;
      }
      raf = requestAnimationFrame(loop);
    }

    // Pause when the hero is off-screen (parallax targets live in it).
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

    // Kick once so initial transform is applied, then settle immediately.
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
          <img className="mark" src="/logos/kairos_logo_navy.png" alt="Kairos" />
          <div className="wordmark">KAIROS</div>
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
            FOR FRACTIONAL CFOs
          </span>
          <button className="top-link mono" type="button" onClick={handleOpenApp}>
            Open app →
          </button>
          <a
            className="enter-btn"
            href="https://calendly.com/signkairos/30min"
            target="_blank"
            rel="noreferrer"
          >
            Book a 30-min walkthrough →
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
            <span className="ico mono">●</span> 6 client engagements ·{" "}
            <span className="num mono">1,284 audit entries</span>
          </span>
        </div>
        <div
          className="float"
          style={{ right: "8%", top: "22%", ["--d" as never]: 24 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">▲</span> approvals queue ·{" "}
            <span className="num mono">2 awaiting sign-off</span>
          </span>
        </div>
        <div
          className="float"
          style={{ left: "12%", top: "64%", ["--d" as never]: 12 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">◆</span> per-client memory ·{" "}
            <span className="num mono">zero cross-refs</span>
          </span>
        </div>
        <div
          className="float"
          style={{ right: "14%", top: "70%", ["--d" as never]: 30 } as React.CSSProperties}
        >
          <span className="tag">
            <span className="ico mono">◇</span> board packs in draft ·{" "}
            <span className="num mono">2 of 6</span>
          </span>
        </div>
        <div className="float-line" style={{ left: 0, right: "60%", top: "38%" }}></div>
        <div className="float-line" style={{ left: "55%", right: 0, top: "58%" }}></div>

        <div className="hero-inner">
          <div className="eyebrow">
            <span className="live-dot"></span>
            <span className="mono">AI WORKSPACE FOR FRACTIONAL CFOs</span>
          </div>
          <h1 className="hero-title">
            <span className="stack">Six clients. One workspace.</span>
            <span className="accent">Zero crossed wires.</span>
          </h1>
          <p className="hero-sub">
            Kairos remembers every client engagement, drafts your board packs, and queues every
            send for your sign-off. With an exportable audit log for every engagement-end review.
          </p>
          <div className="hero-cta">
            <button className="enter-btn" type="button" onClick={handleOpenApp}>
              Open app <span className="mono">→</span>
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
              <span className="mono">Watch the 90-sec demo</span>
              <kbd>↓</kbd>
            </a>
          </div>

          <div className="boot mono" id="boot">
            Built for portfolio practices · Per-client memory · Approve every send · Export the
            audit log
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
                <span className="accent">app</span>.signkairos.com /{" "}
                <span className="mono">chat</span>
              </div>
              <div className="corner mono">DEMO PREVIEW</div>
            </div>

            {/* Cockpit-style top bar — mirrors the real /app header */}
            <div className="pv-top">
              <div className="pv-top-left">
                <span className="pv-mark">K</span>
                <span className="pv-wordmark">KAIROS</span>
                <span className="pv-corner">
                  <span className="pv-live"></span> ONLINE · GEMINI FLASH
                </span>
              </div>
              <nav className="pv-nav-pill">
                <button className="active">Chat</button>
                <button>Dashboard</button>
                <button>Graph</button>
                <button>
                  Approvals
                  <span className="pv-badge">2</span>
                </button>
                <button>Brains</button>
                <button>Settings</button>
              </nav>
              <div className="pv-top-right">
                <span className="pv-brain-pill">
                  <span
                    className="pv-swatch"
                    style={{ background: "var(--layer-wiki)" }}
                  ></span>
                  <span className="pv-brain-lbl">CLIENT</span>
                  <span className="pv-brain-name">Acme SaaS Inc</span>
                  <span className="pv-caret">▾</span>
                </span>
              </div>
            </div>

            <div className="preview-body">
              <aside className="pv-side">
                <div className="lbl">Threads</div>
                <div className="row active">
                  <span>March board prep · Acme</span>
                  <span className="num">●</span>
                </div>
                <div className="row">
                  <span>Beacon · investor reply</span>
                  <span className="num">2h</span>
                </div>
                <div className="row">
                  <span>Acme · runway model v3</span>
                  <span className="num">1d</span>
                </div>
                <div className="row">
                  <span>Beacon · fleet utilisation</span>
                  <span className="num">2d</span>
                </div>

                <div className="lbl">Pinned pages</div>
                <div className="row">
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      className="dot"
                      style={{ background: "var(--layer-hot)" }}
                    ></span>{" "}
                    Acme · hot.md
                  </span>
                  <span className="num">412</span>
                </div>
                <div className="row">
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      className="dot"
                      style={{ background: "var(--layer-index)" }}
                    ></span>{" "}
                    Acme · index
                  </span>
                  <span className="num">208</span>
                </div>
                <div className="row">
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      className="dot"
                      style={{ background: "var(--layer-wiki)" }}
                    ></span>{" "}
                    Feb 2026 P&amp;L
                  </span>
                  <span className="num">142</span>
                </div>
              </aside>

              <main className="pv-main">
                <div className="hdr">
                  <div className="left">
                    <span className="eyebrow">THREAD</span>
                    <h3>March board prep · Acme</h3>
                    <span
                      className="mono"
                      style={{ color: "var(--text-faint)", fontSize: 11 }}
                    >
                      ID 8af3·9c41
                    </span>
                  </div>
                  <span className="chip chip-accent">
                    <span className="dot dot-pulse"></span> streaming
                  </span>
                </div>

                <div className="pv-msg user">
                  <span className="who">Bruno · 09:42</span>
                  <div className="body">
                    Summarise this week's decisions on the Acme bridge round, and tell me what's
                    still open before Tuesday's board.
                  </div>
                </div>

                <div className="pv-think">
                  <span className="dots">
                    <i></i>
                    <i></i>
                    <i></i>
                  </span>
                  <span>
                    Searching{" "}
                    <span className="mono accent" style={{ marginLeft: 4 }}>
                      Acme SaaS Inc
                    </span>{" "}
                    · <span className="mono">bridge round</span>
                  </span>
                  <span className="elapsed mono">2.1s · +3 steps</span>
                </div>

                <div className="pv-msg">
                  <span className="who">KAIROS</span>
                  <div className="body">
                    Three decisions this week, per{" "}
                    <a className="pv-link" href="#">
                      2026-03-12 Sarah 1:1
                    </a>{" "}
                    and{" "}
                    <a className="pv-link" href="#">
                      Feb 2026 P&amp;L
                    </a>
                    : raise <span className="mono">$2.4M</span> at a flat valuation, hold the
                    sales hire until Q3, and extend runway to{" "}
                    <span className="mono">14 months</span>. Still open before Tuesday: lead
                    investor confirmation and the updated{" "}
                    <a className="pv-link" href="#">
                      runway model
                    </a>
                    .
                  </div>
                </div>
              </main>

              <aside className="pv-rail">
                <div className="group">
                  <h4>
                    HOT CONTEXT <span className="pv-rail-meta">ACME SAAS INC</span>
                  </h4>
                  <div className="bar">
                    <span style={{ ["--w" as never]: "65%" } as React.CSSProperties}></span>
                  </div>
                  <div className="telemetry-row">
                    <span>pages cited</span>
                    <span className="v">7 / 12</span>
                  </div>
                </div>
                <div className="group">
                  <h4>
                    SOURCES THIS TURN <span className="pv-rail-meta">+3 STEPS</span>
                  </h4>
                  <div className="telemetry-row">
                    <span style={{ color: "var(--accent-bright)" }}>open_page</span>
                    <span className="v">1.2s</span>
                  </div>
                  <div className="telemetry-row">
                    <span style={{ color: "var(--accent-bright)" }}>open_page</span>
                    <span className="v">0.4s</span>
                  </div>
                  <div className="telemetry-row">
                    <span style={{ color: "var(--accent-bright)" }}>compose_reply</span>
                    <span className="v">0.8s</span>
                  </div>
                </div>
                <div className="group">
                  <h4>
                    APPROVALS QUEUE <span className="pv-rail-meta">2 PENDING</span>
                  </h4>
                  <div className="pv-approval-row pending">
                    <div>
                      <div className="pv-approval-tool">Send · Mar board pack</div>
                      <div className="pv-approval-desc">+412 / 3 sources</div>
                    </div>
                    <span className="pv-countdown mono">04:21</span>
                  </div>
                  <div className="pv-approval-row pending">
                    <div>
                      <div className="pv-approval-tool">Reply · Investor</div>
                      <div className="pv-approval-desc">Beacon · 1 figure flagged</div>
                    </div>
                    <span className="pv-countdown mono">02:08</span>
                  </div>
                </div>
              </aside>
            </div>
          </div>
        </div>
      </section>

      {/* VALUE STRIP */}
      <div className="section-head" style={{ marginTop: 40 }}>
        <h2>
          Built for the <em>practice you actually run.</em>
        </h2>
        <div className="meta">SECTION 01 / 03</div>
      </div>

      <section className="strip">
        <div className="strip-inner">
          <article className="feat hud-frame fade-up">
            <div className="ix">01 · PER-CLIENT MEMORY</div>
            <h3>One workspace per engagement</h3>
            <p>
              Every meeting, variance note, and investor draft lives in a separate space per
              client. Cross-contamination is impossible by design — not a policy, a wall.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">02 · BOARD PACK DRAFTER</div>
            <h3>The work, drafted</h3>
            <p>
              Last month's update, the variance commentary you took on Thursday's call, the
              runway model — pulled together into a clean draft you actually want to send.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">03 · APPROVE EVERY SEND</div>
            <h3>Nothing leaves without you</h3>
            <p>
              Drafts the email. Drafts the board pack. Drafts the Slack reply. Then waits.
              Nothing reaches a client until you tap approve.
            </p>
          </article>
          <article className="feat hud-frame fade-up">
            <div className="ix">04 · A RECORD THAT HOLDS UP</div>
            <h3>Exportable audit log</h3>
            <p>
              Every action — drafted, approved, denied, sent — appended to a tamper-evident log.
              Export to PDF for any engagement-end review.
            </p>
          </article>
        </div>
      </section>

      {/* DEEP DIVES */}
      <div className="section-head" style={{ marginTop: 80 }}>
        <h2>
          The three things <em>your malpractice carrier</em> will care about.
        </h2>
        <div className="meta">SECTION 02 / 03</div>
      </div>

      <section className="deep">
        <div className="deep-inner">
          <div className="deep-row">
            <div className="text fade-up">
              <span className="eyebrow">01 — WATCH THE WORK ASSEMBLE</span>
              <h3>
                Every source,{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>cited</em>.
              </h3>
              <p>
                You see which prior meeting, which P&amp;L snapshot, which investor update Kairos
                pulled from to draft your reply. No black-box "the AI said so" — every claim has
                a page behind it.
              </p>
              <ul className="bullets">
                <li>Every draft cites the engagement notes it leaned on.</li>
                <li>Live activity streams as it works — no waiting on a spinner.</li>
                <li>Cancel mid-draft without losing the thread.</li>
              </ul>
            </div>
            <div className="visual hud-frame fade-up">
              <div className="eyebrow" style={{ marginBottom: 14 }}>
                ASSEMBLING · MARCH BOARD UPDATE
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
                  <span style={{ color: "var(--accent-bright)" }}>▸</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>open</span> &nbsp;
                    <span style={{ color: "var(--text-muted)" }}>
                      Acme · Feb 2026 P&amp;L
                    </span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>✓</span>
                  <span style={{ color: "var(--text-muted)" }}>
                    → reconciled to QuickBooks · 0.81s
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--accent-bright)" }}>▸</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>open</span> &nbsp;
                    <span style={{ color: "var(--text-muted)" }}>2026-03-12 Sarah 1:1</span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>✓</span>
                  <span style={{ color: "var(--text-muted)" }}>
                    → variance notes on top 3 lines · 0.4s
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--accent-bright)" }}>▸</span>
                  <span>
                    <span style={{ color: "var(--accent-bright)" }}>open</span> &nbsp;
                    <span style={{ color: "var(--text-muted)" }}>
                      Feb 2026 board update (sent)
                    </span>
                  </span>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <span style={{ color: "var(--c-success)" }}>✓</span>
                  <span style={{ color: "var(--text-muted)" }}>→ tone-matched · 1.18s</span>
                </div>
                <div style={{ display: "flex", gap: 10, color: "var(--accent)" }}>
                  <span>⋯</span>
                  <span>drafting · 4 sections · awaiting your sign-off</span>
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
                ELAPSED · 00:04.62
              </div>
            </div>
          </div>

          <div className="deep-row flip">
            <div className="visual hud-frame fade-up" style={{ padding: 20 }}>
              <div className="eyebrow" style={{ marginBottom: 14 }}>
                AWAITING SIGN-OFF · OLDEST FIRST
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                <div className="approval-mini pending">
                  <div className="row1">
                    <span className="tool">Send · March board update</span>
                    <span className="countdown mono">EXPIRES 04:21</span>
                  </div>
                  <div className="rationale">
                    Drafted from{" "}
                    <span className="mono accent">Acme · Feb 2026 P&amp;L</span> and three
                    meeting notes. Recipient: ceo@acme.com. Subject and body editable before
                    send.
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className="chip chip-success">+412 words</span>
                    <span className="chip">3 sources cited</span>
                    <span className="chip chip-accent">Acme SaaS Inc</span>
                  </div>
                  <div className="actions">
                    <button className="b">Deny</button>
                    <button className="b approve">Approve →</button>
                  </div>
                </div>
                <div className="approval-mini">
                  <div className="row1">
                    <span className="tool" style={{ color: "var(--text-secondary)" }}>
                      Reply · Investor question on burn
                    </span>
                    <span
                      className="mono"
                      style={{ color: "var(--text-muted)", fontSize: 11 }}
                    >
                      HELD · awaiting your edit
                    </span>
                  </div>
                  <div className="rationale" style={{ color: "var(--text-muted)" }}>
                    Drafted reply for <span className="mono">Beacon Logistics</span>; flagged
                    one figure for confirmation before sending.
                  </div>
                </div>
              </div>
            </div>
            <div className="text fade-up">
              <span className="eyebrow">02 — APPROVE EVERY SEND</span>
              <h3>
                Safe by default.{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>
                  One keystroke
                </em>{" "}
                to ship.
              </h3>
              <p>
                Every outbound message — board update, investor reply, Slack DM — pauses in the
                queue with a full preview and a 5-minute countdown. Nothing reaches a client
                until you say so.
              </p>
              <ul className="bullets">
                <li>Color-coded statuses: pending, held, approved, denied, expired.</li>
                <li>Word-level diffs on every edit, before anything is sent.</li>
                <li>Approve from the browser or your phone — same queue, both places.</li>
              </ul>
            </div>
          </div>

          <div className="deep-row">
            <div className="text fade-up">
              <span className="eyebrow">03 — THE PORTFOLIO MAP</span>
              <h3>
                The shape of{" "}
                <em style={{ color: "var(--accent)", fontStyle: "italic" }}>
                  an engagement.
                </em>
              </h3>
              <p>
                Every meeting, every decision, every investor update — connected to the people
                they involve and the snapshots that back them. Drop into one client and the rest
                of the portfolio fades. Cross-contamination becomes visible, not just policy.
              </p>
              <ul className="bullets">
                <li>
                  <span style={{ color: "var(--layer-hot)" }}>●</span> &nbsp; this client — the
                  active engagement, fully visible.
                </li>
                <li>
                  <span style={{ color: "var(--layer-index)" }}>●</span> &nbsp; key people —
                  CEOs, board members, lead investors.
                </li>
                <li>
                  <span style={{ color: "var(--layer-wiki)" }}>●</span> &nbsp; meetings &amp;
                  decisions — the engagement's history.
                </li>
                <li>
                  <span style={{ color: "var(--layer-raw)" }}>●</span> &nbsp; source documents —
                  P&amp;Ls, contracts, emails.
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
                    <stop offset="0%" stopColor="oklch(0.62 0.15 260 / 0.18)" />
                    <stop offset="60%" stopColor="oklch(0.62 0.15 260 / 0)" />
                  </radialGradient>
                </defs>
                <g transform="translate(24, 0) scale(0.9, 0.85)">
                  <circle cx="240" cy="160" r="200" fill="url(#rg)" />
                  <g stroke="oklch(1 0 0 / 0.08)" strokeWidth="0.7" fill="none">
                    <line x1="240" y1="160" x2="120" y2="80" />
                    <line x1="240" y1="160" x2="360" y2="100" />
                    <line x1="240" y1="160" x2="180" y2="240" />
                    <line x1="240" y1="160" x2="320" y2="220" />
                    <line x1="240" y1="160" x2="80" y2="180" />
                    <line x1="240" y1="160" x2="400" y2="180" />
                    <line x1="180" y1="50" x2="60" y2="40" />
                    <line x1="120" y1="80" x2="180" y2="50" />
                    <line x1="360" y1="100" x2="320" y2="50" />
                    <line x1="180" y1="240" x2="140" y2="290" />
                    <line x1="180" y1="240" x2="240" y2="290" />
                    <line x1="320" y1="220" x2="380" y2="270" />
                    <line x1="80" y1="180" x2="40" y2="240" />
                    <line x1="400" y1="180" x2="450" y2="230" />
                    <line x1="180" y1="50" x2="240" y2="20" />
                    <line x1="180" y1="50" x2="120" y2="80" />
                    <line x1="320" y1="50" x2="430" y2="60" />
                  </g>
                  <g>
                    <circle cx="240" cy="160" r="11" fill="var(--layer-hot)" />
                    <circle cx="120" cy="80" r="8" fill="var(--layer-index)" />
                    <circle cx="360" cy="100" r="8" fill="var(--layer-index)" />
                    <circle cx="180" cy="240" r="6" fill="var(--layer-wiki)" />
                    <circle cx="320" cy="220" r="7" fill="var(--layer-wiki)" />
                    <circle cx="80" cy="180" r="5" fill="var(--layer-wiki)" />
                    <circle cx="400" cy="180" r="6" fill="var(--layer-wiki)" />
                    <circle cx="60" cy="40" r="4" fill="var(--layer-raw)" />
                    <circle cx="180" cy="50" r="5" fill="var(--layer-wiki)" />
                    <circle cx="430" cy="60" r="4" fill="var(--layer-raw)" />
                    <circle cx="320" cy="50" r="5" fill="var(--layer-wiki)" />
                    <circle cx="140" cy="290" r="4" fill="var(--layer-raw)" />
                    <circle cx="240" cy="290" r="4" fill="var(--layer-raw)" />
                    <circle cx="380" cy="270" r="5" fill="var(--layer-wiki)" />
                    <circle cx="40" cy="240" r="4" fill="var(--layer-raw)" />
                    <circle cx="450" cy="230" r="4" fill="var(--layer-raw)" />
                    <circle cx="240" cy="20" r="4" fill="var(--layer-raw)" />
                  </g>
                  <circle
                    cx="240"
                    cy="160"
                    r="11"
                    fill="none"
                    stroke="var(--layer-hot)"
                    strokeWidth="1"
                  >
                    <animate
                      attributeName="r"
                      values="11;26;11"
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
                  142 PAGES · 318 LINKS · ACME SAAS INC{" "}
                  <tspan fill="var(--accent)">· ACTIVE</tspan>
                </text>
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <div className="section-head" style={{ marginTop: 80 }}>
        <h2>Your data stays yours.</h2>
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
            PER-CLIENT MEMORY · APPROVE EVERY SEND · EXPORTABLE AUDIT LOG
          </div>
          <h2
            style={{
              margin: "0 0 14px",
              fontSize: "clamp(32px, 5vw, 56px)",
              fontWeight: 500,
              letterSpacing: "-0.025em",
            }}
          >
            Book a 30-minute walkthrough.
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
            Bring one engagement you'd want to scope. We'll walk through how Kairos remembers
            it, drafts your next board update, and queues every send for your sign-off. No model
            ever trains on your client's data.
          </p>
          <a
            className="enter-btn"
            href="https://calendly.com/signkairos/30min"
            target="_blank"
            rel="noreferrer"
            style={{ height: 40, padding: "0 22px", fontSize: 13.5 }}
          >
            Book the walkthrough
            <span className="mono" style={{ opacity: 0.7 }}>
              →
            </span>
          </a>
        </div>
      </section>

      <footer>
        <div className="row">
          <div>
            <span className="mono">© 2026 KAIROS</span>
          </div>
          <div className="links">
            <a href="mailto:hello@signkairos.com">hello@signkairos.com</a>
          </div>
          <div className="mono">SIGNKAIROS.COM</div>
        </div>
      </footer>
    </div>
  );
}
