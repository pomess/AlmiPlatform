import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { COMPETITORS, type Competitor } from "../lib/pharma";
import { fetchWikipediaSummary } from "../lib/wikipediaPhoto";
import { AstraZenecaAnalysis } from "./AstraZenecaAnalysis";

type Props = {
  selectedCompetitor: string | null;
  analysisExpanded?: boolean;
  onExpandAnalysis?: () => void;
  onCollapseAnalysis?: () => void;
};

type Loaded = {
  thumb: string | null;
  pageUrl: string | null;
};

export function CompetitorPhotoCard({
  selectedCompetitor,
  analysisExpanded = false,
  onExpandAnalysis,
  onCollapseAnalysis,
}: Props) {
  const [data, setData] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);

  const competitor: Competitor | null = selectedCompetitor
    ? COMPETITORS.find((c) => c.name === selectedCompetitor) ?? null
    : null;

  const hasAnalysis = selectedCompetitor === "AstraZeneca";

  useEffect(() => {
    if (!competitor) {
      setData(null);
      return;
    }
    if (competitor.photoUrl) {
      setLoading(false);
      setData({ thumb: competitor.photoUrl, pageUrl: null });
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
    <>
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
              className={`dashboard-photo-card__placeholder${loading ? " is-loading" : ""}`}
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
        {hasAnalysis && (
          <button
            type="button"
            className="dashboard-photo-card__expand-btn"
            onClick={onExpandAnalysis}
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path
                d="M3 9v4h4M13 7V3H9M3 13l4.5-4.5M13 3L8.5 7.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Deep Analysis
          </button>
        )}
      </aside>

      {analysisExpanded && hasAnalysis && createPortal(
        <>
          <div
            className="az-expanded-backdrop"
            onClick={onCollapseAnalysis}
          />
          <div className="az-expanded-container">
            <aside className="dashboard-photo-card az-expanded-card">
              <div className="dashboard-photo-card__media">
                {data?.thumb ? (
                  <img
                    src={data.thumb}
                    alt={`${competitor.name} corporate image`}
                    loading="lazy"
                  />
                ) : (
                  <div className="dashboard-photo-card__placeholder" aria-hidden="true">
                    {competitor.name.slice(0, 2).toUpperCase()}
                  </div>
                )}
              </div>
              <div className="az-expanded-meta">
                <img
                  className="az-brand-logo"
                  src="/competitors/astrazeneca-logo.png"
                  alt="AstraZeneca"
                />
                <div className="az-expanded-meta__text">
                  <div className="az-expanded-meta__name">AstraZeneca</div>
                  <div className="az-expanded-meta__sub">
                    <span className="az-expanded-meta__location">BARCELONA · SPAIN</span>
                    <span className="az-expanded-meta__ticker">LSE: AZN · ~$300B Market Cap</span>
                  </div>
                </div>
              </div>
            </aside>
            <div className="az-expanded-analysis">
              <AstraZenecaAnalysis onClose={() => onCollapseAnalysis?.()} />
            </div>
          </div>
        </>,
        document.body,
      )}
    </>
  );
}

export default CompetitorPhotoCard;
