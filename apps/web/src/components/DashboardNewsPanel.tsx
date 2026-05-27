import { useEffect, useRef, useState } from "react";
import { useDailyNews } from "../hooks/useDailyNews";
import type { NewsSource } from "../lib/api";
import DashboardVideoTile from "./DashboardVideoTile";

const LS_COLLAPSED = "disease360.news.collapsed";
const LS_INTRO_DATE = "disease360.news.introPlayedDate";

// Spoken once on the first dashboard open of the day. Kept short so it
// doesn't fight the dashboard's existing voice/PTT loop. The greeting
// is time-of-day aware against the user's local clock; the body says
// "today's headlines" rather than "summary" because the panel renders
// raw feed items, not an LLM digest.
const INTRO_VOICE = "Algieba";

function greetingForHour(hour: number): string {
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function buildIntroLine(): string {
  return `${greetingForHour(new Date().getHours())}. Today's headlines, below.`;
}

const CATEGORY_LABELS: { key: "pharma" | "derm" | "competitors"; label: string }[] = [
  { key: "pharma", label: "Pharma" },
  { key: "derm", label: "Dermatology" },
  { key: "competitors", label: "Competitors" },
];

function flattenSources(sources: NewsSource[] | undefined): {
  source: string;
  title: string;
  link: string;
}[] {
  if (!sources) return [];
  const out: { source: string; title: string; link: string }[] = [];
  // Round-robin so the first item from each source appears before any
  // source's second item — keeps the panel diverse at a glance.
  const maxItems = Math.max(0, ...sources.map((s) => s.items.length));
  for (let i = 0; i < maxItems; i++) {
    for (const s of sources) {
      const item = s.items[i];
      if (item) out.push({ source: s.source, title: item.title, link: item.link });
    }
  }
  return out;
}

function todayHeader(): string {
  return new Date().toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

function todayLocalISO(): string {
  return new Date().toLocaleDateString("en-CA");
}

// Plays the intro line once per day. Returns a cleanup function that aborts
// any in-flight fetch and gesture listeners. Browsers block audio playback
// before a user gesture, so if the initial play() throws NotAllowedError we
// arm a one-shot listener that retries on the first pointer/key event.
function notifyIntroEnded(): void {
  window.__disease360NewsIntroSpeaking = false;
  const cb = window.__disease360OnNewsIntroEnd;
  if (cb) {
    window.__disease360OnNewsIntroEnd = null;
    try {
      cb();
    } catch {
      /* swallow */
    }
  }
}

function playIntroOnce(): () => void {
  if (localStorage.getItem(LS_INTRO_DATE) === todayLocalISO()) {
    // Already spoken today — make sure the flag is false so the video
    // tile starts right away on this load.
    window.__disease360NewsIntroSpeaking = false;
    return () => {};
  }
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    // Mark as played so we don't keep retrying for users who opt out of motion+audio.
    localStorage.setItem(LS_INTRO_DATE, todayLocalISO());
    window.__disease360NewsIntroSpeaking = false;
    return () => {};
  }

  // Latch the global flag so the video tile knows to defer its iframe
  // creation until the spoken line is done.
  window.__disease360NewsIntroSpeaking = true;

  const ctrl = new AbortController();
  let cleanupGesture: (() => void) | null = null;
  let audio: HTMLAudioElement | null = null;
  let blobUrl: string | null = null;

  const url = `/api/harness/voice/sample?voice=${encodeURIComponent(
    INTRO_VOICE,
  )}&text=${encodeURIComponent(buildIntroLine())}`;

  fetch(url, { signal: ctrl.signal })
    .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`${r.status}`))))
    .then((blob) => {
      if (ctrl.signal.aborted) return;
      blobUrl = URL.createObjectURL(blob);
      audio = new Audio(blobUrl);
      audio.preload = "auto";
      const markPlayed = () => {
        try {
          localStorage.setItem(LS_INTRO_DATE, todayLocalISO());
        } catch {
          /* ignore */
        }
      };
      audio.addEventListener("ended", () => {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        notifyIntroEnded();
      });
      const tryPlay = () => {
        if (!audio) return Promise.resolve();
        return audio.play().then(markPlayed);
      };
      tryPlay().catch(() => {
        // Autoplay blocked — wait for the first user gesture and retry once.
        const onGesture = () => {
          tryPlay().catch(() => {
            // Still blocked — release the video tile so it doesn't wait forever.
            notifyIntroEnded();
          });
          cleanup();
        };
        const cleanup = () => {
          window.removeEventListener("pointerdown", onGesture);
          window.removeEventListener("keydown", onGesture);
          cleanupGesture = null;
        };
        cleanupGesture = cleanup;
        window.addEventListener("pointerdown", onGesture, { once: true });
        window.addEventListener("keydown", onGesture, { once: true });
      });
    })
    .catch(() => {
      // Fetch failed — release the video tile, mark as played to avoid retry storms.
      try {
        localStorage.setItem(LS_INTRO_DATE, todayLocalISO());
      } catch {
        /* ignore */
      }
      notifyIntroEnded();
    });

  return () => {
    ctrl.abort();
    if (cleanupGesture) cleanupGesture();
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    // If the panel is unmounted mid-intro, release the gate so a future
    // remount of the video tile (e.g. user collapses + expands) isn't stuck.
    notifyIntroEnded();
  };
}

export function DashboardNewsPanel({
  selectedCompetitor,
  onDismissCompetitor,
}: {
  selectedCompetitor?: string | null;
  onDismissCompetitor?: () => void;
}) {
  const { data, loading, error } = useDailyNews();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_COLLAPSED) === "1";
    } catch {
      return false;
    }
  });
  const introArmed = useRef(false);

  useEffect(() => {
    try {
      localStorage.setItem(LS_COLLAPSED, collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  // Fire the spoken intro once per day, only when the panel is visible and
  // the news has loaded — so the voice arrives roughly as the slide-in
  // settles. The stored date prevents replays on subsequent reloads.
  useEffect(() => {
    if (introArmed.current) return;
    if (collapsed || !data) return;
    introArmed.current = true;
    const stop = playIntroOnce();
    return stop;
  }, [collapsed, data]);

  // Build competitor-filtered items when a pin is selected
  const competitorItems = (() => {
    if (!selectedCompetitor || !data) return [];
    const needle = selectedCompetitor.toLowerCase();
    // First try exact source match from competitor feeds
    const directItems = flattenSources(
      data.competitors?.filter((s) => s.source.toLowerCase() === needle),
    );
    if (directItems.length > 0) return directItems;
    // Fallback: scan all news for title mentions
    const allItems = [
      ...flattenSources(data.pharma),
      ...flattenSources(data.competitors),
      ...flattenSources(data.derm),
    ];
    return allItems.filter((it) => it.title.toLowerCase().includes(needle));
  })();

  if (collapsed) {
    return (
      <button
        type="button"
        className="dashboard-news-pill"
        onClick={() => setCollapsed(false)}
        aria-label="Show daily news"
      >
        NEWS
      </button>
    );
  }

  return (
    <>
    <aside
      className={`dashboard-news-panel${selectedCompetitor ? " dashboard-news-panel--competitor" : ""}`}
      aria-label={selectedCompetitor ? `${selectedCompetitor} news` : "Daily news"}
    >
      {selectedCompetitor ? (
        <>
          <header className="dashboard-news-header">
            <span className="dashboard-news-competitor-name">{selectedCompetitor}</span>
            <button
              type="button"
              className="dashboard-news-close"
              onClick={onDismissCompetitor}
              aria-label="Dismiss competitor news"
            >
              ×
            </button>
          </header>
          <div className="dashboard-news-body">
            {competitorItems.length === 0 ? (
              <div className="dashboard-news-empty">
                No headlines found for {selectedCompetitor}.
              </div>
            ) : (
              <ul className="dashboard-news-list">
                {competitorItems.slice(0, 12).map((it, i) => (
                  <li key={`comp-${i}`} className="dashboard-news-item">
                    <a
                      href={it.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`${it.source} — ${it.title}`}
                    >
                      {it.title}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : (
        <>
      <header className="dashboard-news-header">
        <span className="dashboard-news-title">NEWS · {todayHeader()}</span>
        <button
          type="button"
          className="dashboard-news-close"
          onClick={() => setCollapsed(true)}
          aria-label="Hide news panel"
        >
          ×
        </button>
      </header>

      {error && !data && (
        <div className="dashboard-news-empty">News unavailable.</div>
      )}
      {loading && !data && (
        <div className="dashboard-news-empty">Loading…</div>
      )}

      {data && (
        <div className="dashboard-news-body">
          {CATEGORY_LABELS.map(({ key, label }, idx) => {
            const items = flattenSources(data[key]);
            return (
              <details
                key={key}
                className="dashboard-news-section"
                open={idx === 0}
              >
                <summary className="dashboard-news-section-summary">
                  {label}
                </summary>
                {items.length === 0 ? (
                  <div className="dashboard-news-empty">No headlines.</div>
                ) : (
                  <ul className="dashboard-news-list">
                    {items.slice(0, 8).map((it, i) => (
                      <li key={`${key}-${i}`} className="dashboard-news-item">
                        <a
                          href={it.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={`${it.source} — ${it.title}`}
                        >
                          {it.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            );
          })}
        </div>
      )}
        </>
      )}
    </aside>
    {data?.video && !selectedCompetitor && <DashboardVideoTile video={data.video} />}
    </>
  );
}

export default DashboardNewsPanel;
