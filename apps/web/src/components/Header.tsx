// Verbatim port of D360/app/header.jsx. Same DOM, same classes.
import { useEffect, useRef, useState } from "react";
import type { DisplayBrain } from "../hooks/useBrains";

type Tab = {
  id: string;
  label: string;
};

interface HeaderProps {
  route: string;
  setRoute: (r: string) => void;
  brain: DisplayBrain | null;
  brains: DisplayBrain[];
  setBrain: (b: DisplayBrain) => void;
  dnd?: boolean;
  theme?: "dark" | "light";
  onToggleTheme?: () => void;
}

export function Header({
  route,
  setRoute,
  brain,
  brains,
  setBrain,
  dnd,
  theme = "dark",
  onToggleTheme,
}: HeaderProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function h(e: MouseEvent) {
      if (open && ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function k(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", h);
    document.addEventListener("keydown", k);
    return () => {
      document.removeEventListener("mousedown", h);
      document.removeEventListener("keydown", k);
    };
  }, [open]);

  const tabs: Tab[] = [
    { id: "chat", label: "Chat" },
    { id: "vera", label: "Vera" },
    { id: "dashboard", label: "Dashboard" },
    { id: "bullseye", label: "Bullseye" },
    { id: "graph", label: "Graph" },
    { id: "brains", label: "Brains" },
  ];
  const showBrain = ["chat", "graph", "brains"].includes(route);

  return (
    <header className="app-top">
      <div className="left">
        <a className="brand-link" href="/" title="Landing">
          <img
            className="mark"
            src={theme === "light" ? "/logos/almirall_logo_navy.svg" : "/logos/almirall_logo_white.svg"}
            alt="Almirall"
          />
        </a>
        <span className="corner">
          <span className="live"></span>
          ONLINE · COMPETITIVE INTEL
        </span>
        {dnd && (
          <span className="dnd-badge">
            <span className="moon"></span>
            DND · 01:00 → 07:00 · 1 HELD
          </span>
        )}
      </div>

      <nav className="nav-pill" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={route === t.id ? "active" : ""}
            onClick={() => setRoute(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="right">
        {onToggleTheme && (
          <button
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-pressed={theme === "light"}
            aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
            title={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
          >
            {theme === "light" ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="4.2" />
                <line x1="12" y1="2.5" x2="12" y2="5" />
                <line x1="12" y1="19" x2="12" y2="21.5" />
                <line x1="2.5" y1="12" x2="5" y2="12" />
                <line x1="19" y1="12" x2="21.5" y2="12" />
                <line x1="4.9" y1="4.9" x2="6.6" y2="6.6" />
                <line x1="17.4" y1="17.4" x2="19.1" y2="19.1" />
                <line x1="4.9" y1="19.1" x2="6.6" y2="17.4" />
                <line x1="17.4" y1="6.6" x2="19.1" y2="4.9" />
              </svg>
            )}
          </button>
        )}
        {showBrain && brain && (
          <div ref={ref} style={{ position: "relative" }}>
            <button className="brain-pill" onClick={() => setOpen((o) => !o)}>
              <span
                className="swatch"
                style={{ background: brain.color, boxShadow: `0 0 6px ${brain.color}` }}
              ></span>
              <span className="lbl">BRAIN</span>
              <span className="name">{brain.title}</span>
              {brain.is_global && (
                <span className="global-tag" title="Global brain — links across all others">
                  GLOBAL
                </span>
              )}
              <span className="caret">▾</span>
            </button>
            {open && (
              <div className="brain-menu">
                <div className="mhead">
                  <span>SELECT BRAIN</span>
                  <span>{brains.length} TOTAL</span>
                </div>
                {brains.map((b) => (
                  <div
                    key={b.id}
                    className={"row" + (b.id === brain.id ? " active" : "")}
                    onClick={() => {
                      setBrain(b);
                      setOpen(false);
                    }}
                  >
                    <span
                      className="swatch"
                      style={{ background: b.color, boxShadow: `0 0 6px ${b.color}` }}
                    ></span>
                    <span className="name">
                      {b.title}
                      {b.is_global && (
                        <span className="global-tag" style={{ marginLeft: 8 }}>
                          GLOBAL
                        </span>
                      )}
                    </span>
                    <span className="num">{b.page_count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
