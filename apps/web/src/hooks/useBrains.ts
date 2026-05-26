// Augments live brains with the design's display fields (color + is_global).
// Color palette is deterministic; the first brain is treated as global.
import { useEffect, useState } from "react";
import { api, type Brain as ApiBrain } from "../lib/api";

export type DisplayBrain = ApiBrain & {
  color: string;
  is_global: boolean;
};

const PALETTE = [
  "var(--layer-wiki)",
  "var(--layer-index)",
  "var(--c-success)",
  "var(--layer-raw)",
  "var(--layer-hot)",
];

const GLOBAL_KEY = "kairos.globalBrain";

export function useBrains(): {
  brains: DisplayBrain[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [brains, setBrains] = useState<DisplayBrain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .brains()
      .then((list) => {
        if (cancelled) return;
        const globalId =
          (typeof localStorage !== "undefined" && localStorage.getItem(GLOBAL_KEY)) ||
          list[0]?.id ||
          "";
        const display = list.map((b, i) => ({
          ...b,
          color: PALETTE[i % PALETTE.length],
          is_global: b.id === globalId,
        }));
        setBrains(display);
        setError(null);
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

  return { brains, loading, error, refresh: () => setTick((n) => n + 1) };
}
