// Fetches a corporate cover image from Wikipedia's REST summary endpoint.
// Used by the dashboard photo card to put a face on each competitor when
// a fly-to is triggered. The summary endpoint returns the infobox image
// (when present), the page extract, and a canonical URL — no auth, no
// API key, public CORS.

export type WikipediaSummary = {
  thumbnailUrl: string | null;
  imageUrl: string | null;
  extract: string | null;
  pageUrl: string | null;
};

const cache = new Map<string, Promise<WikipediaSummary>>();

export function fetchWikipediaSummary(title: string): Promise<WikipediaSummary> {
  const cached = cache.get(title);
  if (cached) return cached;
  const promise = (async (): Promise<WikipediaSummary> => {
    const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(
      title.replace(/ /g, "_"),
    )}`;
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`wikipedia ${res.status}`);
    const data = (await res.json()) as {
      thumbnail?: { source?: string };
      originalimage?: { source?: string };
      extract?: string;
      content_urls?: { desktop?: { page?: string } };
    };
    return {
      thumbnailUrl: data.thumbnail?.source ?? null,
      imageUrl: data.originalimage?.source ?? data.thumbnail?.source ?? null,
      extract: data.extract ?? null,
      pageUrl: data.content_urls?.desktop?.page ?? null,
    };
  })();
  // Don't cache failures — let the next click retry.
  promise.catch(() => cache.delete(title));
  cache.set(title, promise);
  return promise;
}
