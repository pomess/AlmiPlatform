import { useEffect, useState } from "react";
import { COMPETITORS, type Competitor } from "../lib/pharma";
import { fetchWikipediaSummary } from "../lib/wikipediaPhoto";

// Top-right photo card that surfaces a corporate cover image + a tight
// metadata strip (city/country, therapy areas) whenever the dashboard
// fly-to lands on a known competitor. Source is Wikipedia's REST summary
// endpoint — see [[wikipediaPhoto]] for the cache + shape. Sits below
// the activity panel (top: 16px) but offset further down so the two
// don't collide when the agent is mid-turn.

type Props = {
  selectedCompetitor: string | null;
};

type Loaded = {
  thumb: string | null;
  pageUrl: string | null;
};

export function CompetitorPhotoCard({ selectedCompetitor }: Props) {
  const [data, setData] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);

  const competitor: Competitor | null = selectedCompetitor
    ? COMPETITORS.find((c) => c.name === selectedCompetitor) ?? null
    : null;

  useEffect(() => {
    if (!competitor) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setData(null);
    fetchWikipediaSummary(competitor.wikipedia)
      .then((s) => {
        if (cancelled) return;
        setData({ thumb: s.thumbnailUrl, pageUrl: s.pageUrl });
      })
      .catch(() => {
        if (cancelled) return;
        setData({ thumb: null, pageUrl: null });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [competitor]);

  if (!competitor) return null;

  return (
    <aside
      className="dashboard-photo-card"
      aria-label={`${competitor.name} site photo`}
    >
      <div className="dashboard-photo-card__media">
        {data?.thumb ? (
          <img
            src={data.thumb}
            alt={`${competitor.name} corporate image`}
            loading="lazy"
          />
        ) : (
          <div
            className={`dashboard-photo-card__placeholder${
              loading ? " is-loading" : ""
            }`}
            aria-hidden="true"
          >
            {competitor.name.slice(0, 2).toUpperCase()}
          </div>
        )}
      </div>
      <div className="dashboard-photo-card__meta">
        <div className="dashboard-photo-card__name">{competitor.name}</div>
        <div className="dashboard-photo-card__location">
          {competitor.city} · {competitor.country}
        </div>
        <ul className="dashboard-photo-card__tags">
          {competitor.therapyAreas.map((area) => (
            <li key={area} className="dashboard-photo-card__tag">
              {area}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

export default CompetitorPhotoCard;
