// Read-only port of D360/app/pages.jsx — Brains / BrainDetail.
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { renderMarkdown } from "../lib/markdown";
import type { DisplayBrain } from "../hooks/useBrains";

// ============================================================
// BRAINS
// ============================================================
export function BrainsPage({ brains }: { brains: DisplayBrain[] }) {
  const location = useLocation();
  const navigate = useNavigate();
  const nav = location.state as { brainId?: string; pagePath?: string } | null;
  const [open, setOpen] = useState<string | null>(nav?.brainId ?? null);
  const [initialPage, setInitialPage] = useState<string | null>(nav?.pagePath ?? null);

  useEffect(() => {
    if (nav?.brainId) {
      setOpen(nav.brainId);
      setInitialPage(nav.pagePath ?? null);
      // Clear nav state so we don't keep re-applying it on re-renders.
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nav?.brainId, nav?.pagePath]);

  if (open) {
    const b = brains.find((x) => x.id === open);
    if (b)
      return (
        <BrainDetail
          brain={b}
          initialPage={initialPage}
          onBack={() => {
            setOpen(null);
            setInitialPage(null);
          }}
        />
      );
  }
  return (
    <div className="brains-page page">
      <div className="brains-inner">
        <div className="page-head">
          <span className="eyebrow">SECOND BRAIN</span>
          <h1>Brains</h1>
          <p>
            Each brain is a folder of markdown notes — hot cache, curated index, lint report.
            Portable, editable, yours.
          </p>
        </div>

        <div className="brains-grid">
          {brains.map((b, i) => {
            const initials = b.title
              .split(" ")
              .map((w) => w[0])
              .join("")
              .slice(0, 2)
              .toUpperCase();
            return (
              <div
                key={b.id}
                className={"bcard b" + ((i % 4) + 1)}
                onClick={() => setOpen(b.id)}
              >
                <div className="tile">{initials}</div>
                <div>
                  <h3>
                    {b.title}
                    {b.is_global && (
                      <span
                        className="global-tag"
                        style={{ marginLeft: 8, verticalAlign: "middle" }}
                      >
                        GLOBAL
                      </span>
                    )}
                  </h3>
                  <div className="chips">
                    <span className="chip chip-accent">{b.page_count} pages</span>
                    <span className={"chip " + (b.has_hot ? "chip-success" : "chip-muted")}>
                      {b.has_hot ? "hot" : "cold"}
                    </span>
                    {b.is_global && (
                      <span
                        className="chip chip-accent"
                        title="Links to and queries across all other brains"
                      >
                        links to all brains
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

type PageEntry = { id: string; title: string; layer: "hot" | "index" | "wiki" | "raw" };

function BrainDetail({
  brain,
  initialPage,
  onBack,
}: {
  brain: DisplayBrain;
  initialPage: string | null;
  onBack: () => void;
}) {
  const [pages, setPages] = useState<PageEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(initialPage);
  const [body, setBody] = useState<string>("");
  const [title, setTitle] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [filter, setFilter] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  // Load page list from graph endpoint (same data powers the graph view).
  useEffect(() => {
    let cancelled = false;
    api
      .graph(brain.id)
      .then((g) => {
        if (cancelled) return;
        const list: PageEntry[] = g.nodes
          .filter((n) => n.id.endsWith(".md"))
          .map((n) => ({
            id: n.id,
            title: n.title,
            layer: (n.layer as PageEntry["layer"]) || "wiki",
          }))
          .sort((a, b) => {
            const order = { hot: 0, index: 1, wiki: 2, raw: 3 } as const;
            const d = order[a.layer] - order[b.layer];
            return d !== 0 ? d : a.title.localeCompare(b.title);
          });
        setPages(list);
        if (!selected && list.length > 0) setSelected(list[0].id);
      })
      .catch(() => setPages([]));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brain.id]);

  // If parent passes a new initialPage (e.g., a graph node click), jump to it.
  useEffect(() => {
    if (initialPage) setSelected(initialPage);
  }, [initialPage]);

  // Load page body whenever selection changes.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    setNotFound(false);

    const loader =
      selected === "hot.md"
        ? api.hot(brain.id).then((r) => ({ body: r.body, title: "Hot cache" }))
        : selected === "index.md"
          ? api.index(brain.id).then((r) => ({ body: r.body, title: "Index" }))
          : api.page(brain.id, selected).then((r) => ({ body: r.body, title: r.title }));

    loader
      .then((r) => {
        if (cancelled) return;
        setBody(r.body);
        setTitle(r.title);
      })
      .catch(() => {
        if (cancelled) return;
        setBody("");
        setTitle("");
        setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brain.id, selected]);

  // Intercept wikilink clicks anywhere inside the rendered page.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    function onClick(e: MouseEvent) {
      const el = (e.target as HTMLElement).closest("a[data-wikilink]") as HTMLAnchorElement | null;
      if (!el) return;
      e.preventDefault();
      const target = el.dataset.wikilink || "";
      resolveAndOpen(target);
    }
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages]);

  function resolveAndOpen(target: string) {
    // Wikilinks reference a slug without .md. Match against known pages.
    const t = target.trim();
    if (!t) return;
    // 1. direct .md match (already a full path)
    const direct = pages.find((p) => p.id === t || p.id === `${t}.md`);
    if (direct) {
      setSelected(direct.id);
      return;
    }
    // 2. match by filename stem across any folder.
    const withMd = `${t}.md`;
    const byStem = pages.find(
      (p) => p.id.endsWith(`/${withMd}`) || p.id === withMd,
    );
    if (byStem) {
      setSelected(byStem.id);
      return;
    }
    // 3. match by title (case-insensitive).
    const byTitle = pages.find((p) => p.title.toLowerCase() === t.toLowerCase());
    if (byTitle) {
      setSelected(byTitle.id);
      return;
    }
    // Unresolved — keep current page, flash nothing for now.
  }

  const filteredPages = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return pages;
    return pages.filter(
      (p) => p.title.toLowerCase().includes(q) || p.id.toLowerCase().includes(q),
    );
  }, [pages, filter]);

  const grouped = useMemo(() => {
    const g: Record<string, PageEntry[]> = { hot: [], index: [], wiki: [], raw: [] };
    for (const p of filteredPages) g[p.layer]?.push(p);
    return g;
  }, [filteredPages]);

  const groupLabels: { key: keyof typeof grouped; label: string }[] = [
    { key: "hot", label: "Hot" },
    { key: "index", label: "Index" },
    { key: "wiki", label: "Wiki" },
    { key: "raw", label: "Raw" },
  ];

  return (
    <div className="brains-page page">
      <div className="brains-inner">
        <button
          className="btn btn-ghost btn-sm"
          onClick={onBack}
          style={{ marginBottom: 16 }}
        >
          ← All brains
        </button>
        <div className="page-head">
          <span className="eyebrow">
            {brain.title.toUpperCase()} · {brain.page_count} PAGES
            {brain.is_global && " · GLOBAL"}
          </span>
          <h1>
            {brain.title}
            {brain.is_global && (
              <span
                className="global-tag"
                style={{ marginLeft: 14, verticalAlign: "middle", fontSize: 11 }}
              >
                GLOBAL
              </span>
            )}
          </h1>
        </div>

        <div className="brain-detail">
          <aside className="brain-sidebar">
            <input
              className="filter"
              placeholder="Filter pages…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            {groupLabels.map(({ key, label }) =>
              grouped[key].length === 0 ? null : (
                <div key={key}>
                  <div className="group-head">{label}</div>
                  {grouped[key].map((p) => (
                    <a
                      key={p.id}
                      className={"nav-item" + (selected === p.id ? " active" : "")}
                      onClick={(e) => {
                        e.preventDefault();
                        setSelected(p.id);
                      }}
                      href="#"
                      title={p.id}
                    >
                      {p.title}
                    </a>
                  ))}
                </div>
              ),
            )}
            {filteredPages.length === 0 && (
              <div className="group-head" style={{ color: "var(--text-muted)" }}>
                No pages match
              </div>
            )}
          </aside>

          <div>
            <div className="card" style={{ padding: "20px 24px" }} ref={containerRef}>
              {selected && (
                <div className="page-path">{selected}</div>
              )}
              {loading ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading page…</p>
              ) : notFound ? (
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                  Page not found: {selected}
                </p>
              ) : (
                <div className="page-body">
                  {!body.trimStart().startsWith("#") && title && <h1>{title}</h1>}
                  {renderMarkdown(body)}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

