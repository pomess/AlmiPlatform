// Once-per-day news loader for the dashboard.
//
// Hot path: stored payload from today -> render synchronously, no network.
// Cold path: fetch /api/harness/news, write date+payload to localStorage.
// The server has its own 24h cache, so even the cold path is fast.

import { useCallback, useEffect, useState } from "react";
import { fetchDailyNews, type NewsBriefing } from "../lib/api";

const LS_DATE = "kairos.news.lastFetchDate";
const LS_PAYLOAD = "kairos.news.payload";

function todayLocalISO(): string {
  // en-CA gives YYYY-MM-DD which sorts and compares correctly.
  return new Date().toLocaleDateString("en-CA");
}

function readCached(): NewsBriefing | null {
  try {
    const date = localStorage.getItem(LS_DATE);
    if (date !== todayLocalISO()) return null;
    const raw = localStorage.getItem(LS_PAYLOAD);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<NewsBriefing>;
    // Reject cache entries from before the schema added `video`. Treating
    // missing keys as "stale" lets the hook self-heal on field additions
    // without forcing the user to clear localStorage.
    if (!("video" in parsed)) return null;
    return parsed as NewsBriefing;
  } catch {
    return null;
  }
}

function writeCached(payload: NewsBriefing): void {
  try {
    localStorage.setItem(LS_DATE, todayLocalISO());
    localStorage.setItem(LS_PAYLOAD, JSON.stringify(payload));
  } catch {
    /* localStorage full / unavailable — non-fatal */
  }
}

export function useDailyNews(): {
  data: NewsBriefing | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [data, setData] = useState<NewsBriefing | null>(() => readCached());
  const [loading, setLoading] = useState<boolean>(() => readCached() === null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (data && tick === 0) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDailyNews(tick > 0)
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        writeCached(payload);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const refresh = useCallback(() => setTick((n) => n + 1), []);
  return { data, loading, error, refresh };
}
