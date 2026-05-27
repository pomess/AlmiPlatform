// Verbatim port of JARVIS/app/header.jsx. Same DOM, same classes.
import { useEffect, useRef, useState } from "react";
import type { DisplayBrain } from "../hooks/useBrains";

type Tab = {
  id: string;
  label: string;
  badge?: number | null;
};

interface HeaderProps {
  route: string;
  setRoute: (r: string) => void;
  brain: DisplayBrain | null;
  brains: DisplayBrain[];
  setBrain: (b: DisplayBrain) => void;
  dnd?: boolean;
  pendingCount: number;
}

export function Header({
  route,
  setRoute,
  brain,
  brains,
  setBrain,
  dnd,
  pendingCount,
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
    { id: "dashboard", label: "Dashboard" },
    { id: "bullseye", label: "Bullseye" },
    { id: "graph", label: "Graph" },
    { id: "approvals", label: "Approvals", badge: pendingCount > 0 ? pendingCount : null },
    { id: "brains", label: "Brains" },
  ];
  const showBrain = ["chat", "graph", "brains"].includes(route);

  return (
    <header className="app-top">
      <div className="left">
        <a className="brand-link" href="/" title="Landing">
          <img className="mark" src="/logos/almirall_logo_white.svg" alt="Almirall" />
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
            {t.badge ? <span className="badge">{t.badge}</span> : null}
          </button>
        ))}
      </nav>

      <div className="right">
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
