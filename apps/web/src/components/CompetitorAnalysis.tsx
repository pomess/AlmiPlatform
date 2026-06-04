import { useEffect, useState } from "react";

export type CompetitorIntel = {
  company: string;
  slug: string;
  lastFullResearch: string;
  lastLightweightUpdate: string | null;
  meta: {
    hq: string;
    localOffice: string;
    ticker: string;
    marketCap: string;
    employees: string;
    logoUrl?: string;
  };
  overview: {
    summary: string;
    keyStrengths: string[];
    threatLevel: "high" | "moderate" | "low";
    threatRationale: string;
  };
  financials: {
    quarter: string;
    revenue: string;
    revenueGrowth: string;
    coreEps?: string;
    coreEpsGrowth?: string;
    segments: { name: string; revenue: string; growth: string; pctOfTotal?: number }[];
    guidance: string;
    topDrugs?: { name: string; revenue: string }[];
  };
  pipeline: {
    drug: string;
    target: string;
    indication: string;
    phase: string;
    partner: string | null;
    revenue: string | null;
    notes: string;
  }[];
  dermRelevance: {
    program: string;
    trial: string;
    phase: string;
    mechanism: string;
    threatLevel: string;
    notes: string;
  }[];
  catalysts: {
    event: string;
    timeline: string;
    significance: "high" | "medium";
    detail: string;
  }[];
  updates: {
    timestamp: string;
    source: string;
    entries: {
      type: string;
      title: string;
      detail: string;
      affectedDrug?: string;
    }[];
  }[];
};

type Tab = "overview" | "pipeline" | "financials" | "derm" | "catalysts";

const intelCache: Record<string, CompetitorIntel> = {};

async function loadIntel(slug: string): Promise<CompetitorIntel | null> {
  if (intelCache[slug]) return intelCache[slug];
  try {
    const res = await fetch(`/competitor-intel/${slug}.json`);
    if (!res.ok) return null;
    const data: CompetitorIntel = await res.json();
    intelCache[slug] = data;
    return data;
  } catch {
    return null;
  }
}

export function CompetitorAnalysis({ slug, onClose }: { slug: string; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<CompetitorIntel | null>(intelCache[slug] ?? null);
  const [loading, setLoading] = useState(!intelCache[slug]);
  const [updating, setUpdating] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<string | null>(null);

  useEffect(() => {
    if (intelCache[slug]) {
      setData(intelCache[slug]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    loadIntel(slug).then((d) => {
      if (cancelled) return;
      setData(d);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [slug]);

  useEffect(() => {
    if (!data) return;
    const lastUpdate = data.lastLightweightUpdate;
    if (!lastUpdate || Date.now() - new Date(lastUpdate).getTime() > 24 * 60 * 60 * 1000) {
      const sessionKey = `competitor-update-${slug}`;
      if (sessionStorage.getItem(sessionKey)) return;
      triggerUpdate();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, slug]);

  function triggerUpdate() {
    setUpdating(true);
    setUpdateStatus("Searching for updates…");
    fetch("/api/harness/competitor-update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company: data?.company ?? slug }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((update) => {
        if (update.entries && update.entries.length > 0 && data) {
          const newData = { ...data, updates: [...data.updates, update], lastLightweightUpdate: update.timestamp };
          intelCache[slug] = newData;
          setData(newData);
          setUpdateStatus(`${update.entries.length} update(s) found`);
        } else {
          setUpdateStatus("No new updates");
        }
        sessionStorage.setItem(`competitor-update-${slug}`, "1");
      })
      .catch(() => {
        setUpdateStatus(null);
      })
      .finally(() => {
        setUpdating(false);
        setTimeout(() => setUpdateStatus(null), 2500);
      });
  }

  if (loading) {
    return (
      <div className="az-analysis">
        <div className="az-analysis-loading">
          <div className="az-spinner" />
          <span>Loading analysis…</span>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="az-analysis">
        <div className="az-analysis-loading">
          <span>No analysis available for this competitor yet.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="az-analysis">
      <nav className="az-analysis-tabs">
        {([
          ["overview", "Overview"],
          ["pipeline", "Pipeline"],
          ["financials", "Financials"],
          ["derm", "Derm Relevance"],
          ["catalysts", "2026 Catalysts"],
        ] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
        {(updating || updateStatus) && (
          <span className={`az-update-badge${updating ? " is-loading" : ""}`}>
            {updating && <span className="az-spinner-sm" />}
            <span>{updateStatus}</span>
          </span>
        )}
        <button className="az-tabs-close" onClick={onClose} aria-label="Close analysis">
          ×
        </button>
      </nav>

      <div className="az-analysis-body">
        {tab === "overview" && <OverviewTab data={data} />}
        {tab === "pipeline" && <PipelineTab data={data} />}
        {tab === "financials" && <FinancialsTab data={data} />}
        {tab === "derm" && <DermTab data={data} />}
        {tab === "catalysts" && <CatalystsTab data={data} />}
      </div>

      <footer className="az-analysis-footer">
        <span className="az-analysis-source">
          Sources: SEC filings {data.financials.quarter} · Pipeline page · PubMed / BioMCP · ClinicalTrials.gov
        </span>
        <span className="az-analysis-updated">
          Researched: {new Date(data.lastFullResearch).toLocaleDateString()}
        </span>
      </footer>
    </div>
  );
}

function OverviewTab({ data }: { data: CompetitorIntel }) {
  const segs = data.financials.segments;
  return (
    <div className="az-tab-content">
      <div className="az-kpi-grid">
        <div className="az-kpi-card">
          <span className="az-kpi-label">{data.financials.quarter} Revenue</span>
          <span className="az-kpi-value">{data.financials.revenue}</span>
          <span className="az-kpi-delta positive">{data.financials.revenueGrowth}</span>
        </div>
        {segs.slice(0, 2).map((s) => (
          <div className="az-kpi-card" key={s.name}>
            <span className="az-kpi-label">{s.name}</span>
            <span className="az-kpi-value">{s.revenue}</span>
            <span className="az-kpi-delta positive">{s.growth}</span>
          </div>
        ))}
        <div className="az-kpi-card">
          <span className="az-kpi-label">FY Guidance</span>
          <span className="az-kpi-value" style={{ fontSize: 15 }}>{data.financials.guidance.split(";")[0]}</span>
          <span className="az-kpi-delta neutral">Revenue</span>
        </div>
      </div>

      <section className="az-section">
        <h3>Strategic Position</h3>
        <p>{data.overview.summary}</p>
        <p><strong>Key strengths:</strong> {data.overview.keyStrengths.join(" · ")}</p>
      </section>

      {segs.length > 0 && (
        <section className="az-section">
          <h3>Therapy Area Mix ({data.financials.quarter})</h3>
          <div className="az-bar-chart">
            {segs.map((s) => (
              <div className="az-bar-row" key={s.name}>
                <span className="az-bar-label">{s.name}</span>
                <div className="az-bar-track">
                  <div className="az-bar-fill az-bar-onc" style={{ width: `${s.pctOfTotal ?? 25}%` }} />
                </div>
                <span className="az-bar-val">{s.revenue} ({s.pctOfTotal ?? "—"}%)</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="az-section">
        <h3>Almirall Competitive Context</h3>
        <p>{data.overview.threatRationale}</p>
        <div className="az-threat-badge">
          <span className={`az-threat-indicator ${data.overview.threatLevel}`} />
          <span>Competitive Threat to Almirall: <strong>{data.overview.threatLevel.charAt(0).toUpperCase() + data.overview.threatLevel.slice(1)}</strong></span>
        </div>
      </section>

      {data.updates.length > 0 && (
        <section className="az-section">
          <h3>Recent Updates</h3>
          <ul className="az-notes-list">
            {data.updates.flatMap((u) => u.entries).slice(0, 5).map((e, i) => (
              <li key={i}><strong>{e.title}:</strong> {e.detail}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function PipelineTab({ data }: { data: CompetitorIntel }) {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>Key Programs ({data.pipeline.length})</h3>
        <div className="az-pipeline-table-wrap">
          <table className="az-pipeline-table">
            <thead>
              <tr>
                <th>Drug</th>
                <th>Target</th>
                <th>Indication</th>
                <th>Phase</th>
                <th>Partner</th>
                <th>Revenue</th>
              </tr>
            </thead>
            <tbody>
              {data.pipeline.map((row) => (
                <tr key={row.drug}>
                  <td className="az-drug-name">{row.drug}</td>
                  <td><span className="az-target-chip">{row.target}</span></td>
                  <td>{row.indication}</td>
                  <td><span className={`az-phase-badge ${phaseClass(row.phase)}`}>{row.phase}</span></td>
                  <td className="az-partner">{row.partner ?? "—"}</td>
                  <td className="az-revenue">{row.revenue ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="az-section">
        <h3>Pipeline Notes</h3>
        <ul className="az-notes-list">
          {data.pipeline.filter(d => d.notes).map((d) => (
            <li key={d.drug}><strong>{d.drug}:</strong> {d.notes}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function FinancialsTab({ data }: { data: CompetitorIntel }) {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>{data.financials.quarter} Key Metrics</h3>
        <div className="az-metrics-grid">
          <div className="az-metric-card">
            <span className="az-metric-label">Revenue</span>
            <span className="az-metric-value">{data.financials.revenue}</span>
            <span className="az-metric-change">{data.financials.revenueGrowth}</span>
          </div>
          {data.financials.coreEps && (
            <div className="az-metric-card">
              <span className="az-metric-label">Core EPS</span>
              <span className="az-metric-value">{data.financials.coreEps}</span>
              <span className="az-metric-change">{data.financials.coreEpsGrowth}</span>
            </div>
          )}
          {data.financials.segments.map((s) => (
            <div className="az-metric-card" key={s.name}>
              <span className="az-metric-label">{s.name}</span>
              <span className="az-metric-value">{s.revenue}</span>
              <span className="az-metric-change">{s.growth}</span>
            </div>
          ))}
          <div className="az-metric-card">
            <span className="az-metric-label">Employees</span>
            <span className="az-metric-value">{data.meta.employees}</span>
            <span className="az-metric-change">Global</span>
          </div>
        </div>
      </section>

      {data.financials.topDrugs && data.financials.topDrugs.length > 0 && (
        <section className="az-section">
          <h3>Revenue by Drug (Run-Rate)</h3>
          <div className="az-bar-chart">
            {data.financials.topDrugs.map((d, i) => {
              const maxRev = parseFloat(data.financials.topDrugs![0].revenue.replace(/[^0-9.]/g, ""));
              const thisRev = parseFloat(d.revenue.replace(/[^0-9.]/g, ""));
              const pct = maxRev > 0 ? (thisRev / maxRev) * 100 : 25;
              return (
                <div className="az-bar-row" key={d.name}>
                  <span className="az-bar-label">{d.name}</span>
                  <div className="az-bar-track">
                    <div className="az-bar-fill az-bar-onc" style={{ width: `${pct}%`, opacity: 1 - i * 0.06 }} />
                  </div>
                  <span className="az-bar-val">{d.revenue}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="az-section">
        <h3>Guidance & Outlook</h3>
        <div className="az-guidance-cards">
          <div className="az-guidance-card">
            <span className="az-guidance-title">Guidance</span>
            <span className="az-guidance-value">{data.financials.guidance}</span>
          </div>
          <div className="az-guidance-card">
            <span className="az-guidance-title">Market Cap</span>
            <span className="az-guidance-value">{data.meta.marketCap}</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function DermTab({ data }: { data: CompetitorIntel }) {
  if (data.dermRelevance.length === 0) {
    return (
      <div className="az-tab-content">
        <section className="az-section">
          <h3>Dermatology Relevance</h3>
          <p>No active dermatology programs identified for this competitor in Almirall's competitive space (AD, PSO, HS).</p>
        </section>
      </div>
    );
  }

  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>Derm-Adjacent Programs</h3>
        <div className="az-pipeline-table-wrap">
          <table className="az-pipeline-table az-derm-table">
            <thead>
              <tr>
                <th>Program</th>
                <th>Trial</th>
                <th>Phase</th>
                <th>Mechanism</th>
                <th>Threat</th>
              </tr>
            </thead>
            <tbody>
              {data.dermRelevance.map((row) => (
                <tr key={row.trial}>
                  <td className="az-drug-name">{row.program}</td>
                  <td><span className="az-target-chip">{row.trial}</span></td>
                  <td><span className={`az-phase-badge ${phaseClass(row.phase)}`}>{row.phase}</span></td>
                  <td>{row.mechanism}</td>
                  <td><span className={`az-threat-chip ${row.threatLevel}`}>{row.threatLevel}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="az-section">
        <h3>Notes</h3>
        <ul className="az-notes-list">
          {data.dermRelevance.map((d) => (
            <li key={d.trial}><strong>{d.program}:</strong> {d.notes}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function CatalystsTab({ data }: { data: CompetitorIntel }) {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>2026 Pipeline Catalysts</h3>
        <div className="az-catalysts-list">
          {data.catalysts.map((c, i) => (
            <div className={`az-catalyst-row ${c.significance}`} key={i}>
              <div className="az-catalyst-timeline">
                <span className="az-catalyst-dot" />
                <span className="az-catalyst-time">{c.timeline}</span>
              </div>
              <div className="az-catalyst-content">
                <span className="az-catalyst-event">{c.event}</span>
                <span className="az-catalyst-detail">{c.detail}</span>
              </div>
              <span className={`az-significance-badge ${c.significance}`}>
                {c.significance}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function phaseClass(phase: string): string {
  if (phase.includes("Approved")) return "approved";
  if (phase.includes("III")) return "phase3";
  if (phase.includes("II")) return "phase2";
  if (phase.includes("I")) return "phase1";
  return "preclinical";
}

export default CompetitorAnalysis;
