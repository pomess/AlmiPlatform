import { useState } from "react";

type Tab = "overview" | "pipeline" | "financials" | "derm" | "catalysts";

const PIPELINE_DATA = [
  { drug: "Enhertu", target: "HER2", indication: "Breast / Lung / Gastric", phase: "Approved", partner: "Daiichi Sankyo", revenue: "$4.0B+", notes: "Expanding into early-stage breast (DB-09, DB-11) and lung (DESTINY-Lung04/06)" },
  { drug: "Imfinzi", target: "PD-L1", indication: "NSCLC / SCLC / HCC / BTC", phase: "Approved", partner: "—", revenue: "$4.7B+", notes: "PACIFIC backbone. Expanding into earlier stages (PACIFIC-9, VOLGA, AVANZAR)" },
  { drug: "Tagrisso", target: "EGFR", indication: "NSCLC", phase: "Approved", partner: "—", revenue: "$5.4B+", notes: "Adjuvant standard-of-care. LAURA + FLAURA2 cement dominance" },
  { drug: "Tezspire", target: "TSLP", indication: "Asthma / CRSwNP / EoE / COPD", phase: "Approved + LCM", partner: "Amgen", revenue: "$1.2B+", notes: "WAYPOINT positive for nasal polyps. CROSSING (EoE) and EMBARK/JOURNEY (COPD) in Ph III" },
  { drug: "Fasenra", target: "IL-5Rα", indication: "Asthma / EGPA / BP / AD / CSU", phase: "Approved + LCM", partner: "—", revenue: "$1.2B+", notes: "Expanding into dermatology: FJORD (BP, Ph III), HILLIER (AD, Ph II), ARROYO (CSU, Ph II)" },
  { drug: "Breztri", target: "ICS/LAMA/LABA", indication: "COPD / Asthma", phase: "Approved + LCM", partner: "—", revenue: "$1.4B+", notes: "Triple inhaler. KALOS/LOGOS trials expanding into asthma" },
  { drug: "Datroway", target: "TROP2-ADC", indication: "TNBC / NSCLC", phase: "Approved", partner: "Daiichi Sankyo", revenue: "Launch", notes: "TROPION-Breast02: doubled PFS vs chemo in 1L TNBC. Filing in lung cancer" },
  { drug: "Tozorakimab", target: "IL-33", indication: "COPD", phase: "Phase III", partner: "—", revenue: "—", notes: "LUNA program (4 trials). First biologic to work across eosinophil levels in COPD" },
  { drug: "Baxdrostat", target: "Ald. Synthase", indication: "Resistant HTN", phase: "Phase III (PDUFA Q2 2026)", partner: "CinCor (acq.)", revenue: "—", notes: "First aldosterone synthase inhibitor. Unmet need: ~10M patients globally" },
  { drug: "Camizestrant", target: "SERD (oral)", indication: "HR+ Breast Cancer", phase: "Phase III", partner: "—", revenue: "—", notes: "SERENA-4 adjuvant readout H2 2026. Could replace tamoxifen" },
  { drug: "Wainua (eplontersen)", target: "TTR (ASO)", indication: "ATTR-CM", phase: "Phase III", partner: "Ionis", revenue: "—", notes: "CardioTransform positive. Convenient SC dosing vs competitors" },
  { drug: "Saphnelo", target: "IFNAR1", indication: "SLE", phase: "Approved + expanding", partner: "—", revenue: "$0.4B+", notes: "First targeted biologic for lupus to gain broad adoption" },
];

const DERM_RELEVANCE = [
  { program: "Fasenra in Atopic Dermatitis", trial: "HILLIER", phase: "Phase II", mechanism: "Anti-IL-5Rα (eosinophil depletion)", threat: "Medium", notes: "Different MOA from Ebglyss (IL-13). Targets eosinophil-high AD subset. If positive, Phase III by 2027" },
  { program: "Fasenra in Bullous Pemphigoid", trial: "FJORD", phase: "Phase III", mechanism: "Anti-IL-5Rα", threat: "Low (different indication)", notes: "Adjacent derm space — AZ building a dermatology-from-eosinophils franchise" },
  { program: "Fasenra in Chronic Spontaneous Urticaria", trial: "ARROYO", phase: "Phase II", mechanism: "Anti-IL-5Rα", threat: "Low", notes: "CSU is adjacent but distinct from Almirall's AD/PSO focus" },
  { program: "Tezspire in Eosinophilic Esophagitis", trial: "CROSSING", phase: "Phase III", mechanism: "Anti-TSLP", threat: "Low (GI-focused)", notes: "Not derm, but signals AZ ambition to expand anti-TSLP broadly into Type 2 inflammation" },
  { program: "Saphnelo in SLE", trial: "TULIP / AZALEA", phase: "Approved", mechanism: "Anti-IFNAR1", threat: "Low", notes: "Lupus-adjacent skin manifestations. Distinct from Almirall's competitive space" },
];

const FINANCIAL_METRICS = [
  { label: "Q1 2026 Revenue", value: "$15.3B", change: "+8% CER" },
  { label: "Oncology Revenue", value: "$6.8B", change: "+16% CER" },
  { label: "Resp & Immunology", value: "$2.3B", change: "+7% CER" },
  { label: "Core EPS", value: "$2.58", change: "+5% CER" },
  { label: "Core Op. Profit Growth", value: "12%", change: "vs Q1 2025" },
  { label: "R&D Spend (% Rev)", value: "23%", change: "$3.5B" },
  { label: "Net Debt", value: "$25.9B", change: "+$2.5B in Q1" },
  { label: "Employees", value: "~96,100", change: "Global" },
];

const CATALYSTS_2026 = [
  { event: "Baxdrostat PDUFA", timeline: "Q2 2026", significance: "high", detail: "First aldosterone synthase inhibitor approval — large hypertension market" },
  { event: "Datroway TNBC approval", timeline: "Q2 2026", significance: "high", detail: "TROPION-Breast02 data supports 1L mTNBC filing" },
  { event: "Camizestrant SERENA-4", timeline: "H2 2026", significance: "high", detail: "Adjuvant breast cancer readout — could define next-gen endocrine therapy" },
  { event: "Enhertu DB-05/DB-11 adjuvant", timeline: "2026", significance: "high", detail: "Moving HER2 ADC into early breast cancer" },
  { event: "Tozorakimab LUNA full data", timeline: "2026", significance: "high", detail: "First biologic for COPD independent of eosinophils" },
  { event: "Imfinzi VOLGA (bladder)", timeline: "2026", significance: "medium", detail: "Neo-adjuvant IO combo in muscle-invasive bladder cancer" },
  { event: "Imfinzi PACIFIC-9", timeline: "2026", significance: "medium", detail: "Next-gen IO combo in unresectable Stage III NSCLC" },
  { event: "Wainua CardioTransform", timeline: "2026", significance: "medium", detail: "Full data presentation at medical meeting; filing expected" },
  { event: "Fasenra FJORD (BP)", timeline: "2026–2027", significance: "medium", detail: "Phase III readout in bullous pemphigoid (derm-relevant)" },
  { event: "Ultomiris IgAN accelerated filing", timeline: "2026", significance: "medium", detail: "Week 34 proteinuria data supports filing" },
];

export function AstraZenecaAnalysis({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("overview");

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
        <button className="az-tabs-close" onClick={onClose} aria-label="Close analysis">
          ×
        </button>
      </nav>

      <div className="az-analysis-body">
        {tab === "overview" && <OverviewTab />}
        {tab === "pipeline" && <PipelineTab />}
        {tab === "financials" && <FinancialsTab />}
        {tab === "derm" && <DermTab />}
        {tab === "catalysts" && <CatalystsTab />}
      </div>

      <footer className="az-analysis-footer">
        <span className="az-analysis-source">
          Sources: SEC filings Q1 2026 · AstraZeneca Pipeline (Apr 2026) · PubMed / BioMCP · ClinicalTrials.gov
        </span>
        <span className="az-analysis-updated">Updated: Jun 2026</span>
      </footer>
    </div>
  );
}

function OverviewTab() {
  return (
    <div className="az-tab-content">
      <div className="az-kpi-grid">
        <div className="az-kpi-card">
          <span className="az-kpi-label">Q1 2026 Revenue</span>
          <span className="az-kpi-value">$15.3B</span>
          <span className="az-kpi-delta positive">+8% CER</span>
        </div>
        <div className="az-kpi-card">
          <span className="az-kpi-label">Oncology</span>
          <span className="az-kpi-value">$6.8B</span>
          <span className="az-kpi-delta positive">+16%</span>
        </div>
        <div className="az-kpi-card">
          <span className="az-kpi-label">Resp & Immuno</span>
          <span className="az-kpi-value">$2.3B</span>
          <span className="az-kpi-delta positive">+7%</span>
        </div>
        <div className="az-kpi-card">
          <span className="az-kpi-label">FY 2026 Guidance</span>
          <span className="az-kpi-value">Mid-High SG</span>
          <span className="az-kpi-delta neutral">Revenue CER</span>
        </div>
      </div>

      <section className="az-section">
        <h3>Strategic Position</h3>
        <p>
          AstraZeneca is in the midst of a <strong>catalyst-rich period</strong>, with four positive Phase III
          readouts in Q1 2026 alone (tozorakimab, eplontersen, efzimfotase alfa, Ultomiris in IgAN).
          The company's 2030 ambition targets $80B+ revenue, driven by its oncology ADC franchise
          (Enhertu/Datroway with Daiichi Sankyo), respiratory biologics expansion, and new modalities.
        </p>
        <p>
          <strong>Key strengths:</strong> Category-defining ADC platform with Daiichi Sankyo · Tezspire/Fasenra
          biologics expanding across Type 2 inflammation · First-mover in aldosterone synthase (Baxdrostat) ·
          14 regulatory approvals in Q1 alone.
        </p>
      </section>

      <section className="az-section">
        <h3>Therapy Area Mix (Q1 2026)</h3>
        <div className="az-bar-chart">
          <div className="az-bar-row">
            <span className="az-bar-label">Oncology</span>
            <div className="az-bar-track">
              <div className="az-bar-fill az-bar-onc" style={{ width: "55%" }} />
            </div>
            <span className="az-bar-val">$6.8B (55%)</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Resp & Immuno</span>
            <div className="az-bar-track">
              <div className="az-bar-fill az-bar-resp" style={{ width: "19%" }} />
            </div>
            <span className="az-bar-val">$2.3B (19%)</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Rare Disease</span>
            <div className="az-bar-track">
              <div className="az-bar-fill az-bar-rare" style={{ width: "15%" }} />
            </div>
            <span className="az-bar-val">$1.9B (15%)</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">CV/Renal/Metab</span>
            <div className="az-bar-track">
              <div className="az-bar-fill az-bar-cvrm" style={{ width: "11%" }} />
            </div>
            <span className="az-bar-val">$1.3B (11%)</span>
          </div>
        </div>
      </section>

      <section className="az-section">
        <h3>Almirall Competitive Context</h3>
        <p>
          AstraZeneca is <strong>not a direct competitor</strong> in Almirall's core AD/PSO space today,
          but is building a dermatology-from-immunology approach via <strong>Fasenra</strong> (benralizumab)
          in atopic dermatitis (HILLIER, Phase II) and bullous pemphigoid (FJORD, Phase III).
          Their anti-TSLP (Tezspire) mechanism is adjacent to the IL-4Rα/IL-13 axis where Ebglyss competes.
        </p>
        <div className="az-threat-badge">
          <span className="az-threat-indicator moderate" />
          <span>Competitive Threat to Almirall: <strong>Moderate (watch Fasenra derm expansion)</strong></span>
        </div>
      </section>
    </div>
  );
}

function PipelineTab() {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>Key Programs ({PIPELINE_DATA.length})</h3>
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
              {PIPELINE_DATA.map((row) => (
                <tr key={row.drug}>
                  <td className="az-drug-name">{row.drug}</td>
                  <td><span className="az-target-chip">{row.target}</span></td>
                  <td>{row.indication}</td>
                  <td><span className={`az-phase-badge ${phaseClass(row.phase)}`}>{row.phase}</span></td>
                  <td className="az-partner">{row.partner}</td>
                  <td className="az-revenue">{row.revenue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="az-section">
        <h3>Pipeline Highlights</h3>
        <ul className="az-notes-list">
          {PIPELINE_DATA.filter(d => d.notes).map((d) => (
            <li key={d.drug}>
              <strong>{d.drug}:</strong> {d.notes}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function FinancialsTab() {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>Q1 2026 Key Metrics</h3>
        <div className="az-metrics-grid">
          {FINANCIAL_METRICS.map((m) => (
            <div className="az-metric-card" key={m.label}>
              <span className="az-metric-label">{m.label}</span>
              <span className="az-metric-value">{m.value}</span>
              <span className="az-metric-change">{m.change}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="az-section">
        <h3>Revenue Breakdown by Drug (Top Franchises, FY 2025 Run-Rate)</h3>
        <div className="az-bar-chart">
          <div className="az-bar-row">
            <span className="az-bar-label">Tagrisso</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-onc" style={{ width: "100%" }} /></div>
            <span className="az-bar-val">$5.4B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Imfinzi</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-onc" style={{ width: "87%" }} /></div>
            <span className="az-bar-val">$4.7B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Enhertu</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-onc" style={{ width: "74%" }} /></div>
            <span className="az-bar-val">$4.0B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Ultomiris</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-rare" style={{ width: "48%" }} /></div>
            <span className="az-bar-val">$2.6B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Farxiga</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-cvrm" style={{ width: "42%" }} /></div>
            <span className="az-bar-val">$2.3B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Breztri</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-resp" style={{ width: "26%" }} /></div>
            <span className="az-bar-val">$1.4B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Tezspire</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-resp" style={{ width: "22%" }} /></div>
            <span className="az-bar-val">$1.2B</span>
          </div>
          <div className="az-bar-row">
            <span className="az-bar-label">Fasenra</span>
            <div className="az-bar-track"><div className="az-bar-fill az-bar-resp" style={{ width: "22%" }} /></div>
            <span className="az-bar-val">$1.2B</span>
          </div>
        </div>
      </section>

      <section className="az-section">
        <h3>Guidance & Outlook</h3>
        <div className="az-guidance-cards">
          <div className="az-guidance-card">
            <span className="az-guidance-title">FY 2026 Revenue</span>
            <span className="az-guidance-value">Mid-to-high single-digit growth (CER)</span>
          </div>
          <div className="az-guidance-card">
            <span className="az-guidance-title">FY 2026 Core EPS</span>
            <span className="az-guidance-value">Low double-digit growth (CER)</span>
          </div>
          <div className="az-guidance-card">
            <span className="az-guidance-title">2030 Ambition</span>
            <span className="az-guidance-value">$80B+ revenue target</span>
          </div>
          <div className="az-guidance-card">
            <span className="az-guidance-title">Near-term NME value</span>
            <span className="az-guidance-value">&gt;$10B risk-adjusted peak revenue from catalysts</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function DermTab() {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>AstraZeneca's Dermatology Relevance to Almirall</h3>
        <p>
          AZ doesn't compete head-on in AD (Ebglyss' space) or PSO (Ilumetri) today, but is building
          a <strong>dermatology-from-eosinophils</strong> thesis via Fasenra expansion. The key question:
          can an eosinophil-depleting mechanism (IL-5Rα) carve out a niche in AD where IL-13 (Ebglyss)
          and IL-4Rα (Dupixent) dominate?
        </p>
      </section>

      <section className="az-section">
        <h3>Active Derm-Adjacent Programs</h3>
        <div className="az-pipeline-table-wrap">
          <table className="az-pipeline-table az-derm-table">
            <thead>
              <tr>
                <th>Program</th>
                <th>Trial</th>
                <th>Phase</th>
                <th>Mechanism</th>
                <th>Threat Level</th>
              </tr>
            </thead>
            <tbody>
              {DERM_RELEVANCE.map((row) => (
                <tr key={row.trial}>
                  <td className="az-drug-name">{row.program}</td>
                  <td><span className="az-target-chip">{row.trial}</span></td>
                  <td><span className={`az-phase-badge ${phaseClass(row.phase)}`}>{row.phase}</span></td>
                  <td>{row.mechanism}</td>
                  <td>
                    <span className={`az-threat-chip ${row.threat.toLowerCase().split(" ")[0]}`}>
                      {row.threat}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="az-section">
        <h3>Competitive Assessment</h3>
        <div className="az-assessment-cards">
          <div className="az-assess-card">
            <span className="az-assess-icon">⚡</span>
            <h4>Near-term (2026)</h4>
            <p>No direct threat. Fasenra AD trial (HILLIER) is only Phase II. AZ not competing for AD/PSO commercial market.</p>
          </div>
          <div className="az-assess-card">
            <span className="az-assess-icon">👁️</span>
            <h4>Medium-term (2027–2028)</h4>
            <p>Watch HILLIER readout. If positive, AZ could enter Phase III in AD with a distinct MOA (eosinophil depletion vs IL-13 blockade). Would compete for the biologic-refractory or eosinophil-high subset.</p>
          </div>
          <div className="az-assess-card">
            <span className="az-assess-icon">🎯</span>
            <h4>Strategic Angle</h4>
            <p>AZ's real strength is platform synergy: same molecule (Fasenra) across asthma → EGPA → BP → AD → CSU. If even 2 of these succeed, Fasenra becomes a cross-specialty franchise competitor.</p>
          </div>
        </div>
      </section>

      <section className="az-section">
        <h3>Notes from Literature (BioMCP)</h3>
        <ul className="az-notes-list">
          <li><strong>Eosinophil depletion in AD:</strong> Benralizumab near-completely depletes eosinophils via ADCC, unlike mepolizumab which only blocks recruitment. Small case series show benefit in eosinophil-high AD, but Phase II will be the first RCT-level evidence.</li>
          <li><strong>IL-5Rα vs IL-13 positioning:</strong> These are non-overlapping mechanisms. Ebglyss blocks IL-13 signaling (downstream Th2); Fasenra depletes eosinophils (effector cells). A sequencing strategy could emerge.</li>
          <li><strong>BP is AZ's fastest derm play:</strong> FJORD is Phase III now — bullous pemphigoid is an unmet need with no approved biologics. Approval expected 2027–2028.</li>
        </ul>
      </section>
    </div>
  );
}

function CatalystsTab() {
  return (
    <div className="az-tab-content">
      <section className="az-section">
        <h3>2026 Pipeline Catalysts</h3>
        <p>
          AstraZeneca described 2026 as a "catalyst-rich period" with potential first approvals
          of four NMEs and multiple lifecycle expansions. The company targets &gt;$10B in risk-adjusted
          peak revenue from near-term programs.
        </p>
      </section>

      <section className="az-section">
        <div className="az-catalysts-list">
          {CATALYSTS_2026.map((c, i) => (
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

      <section className="az-section">
        <h3>What to Watch (Almirall Lens)</h3>
        <ul className="az-notes-list">
          <li><strong>H2 2026:</strong> HILLIER (Fasenra in AD) readout timing — if positive, AZ enters Almirall's competitive set</li>
          <li><strong>2027:</strong> FJORD (BP) Phase III — first approved biologic in BP would validate AZ's derm-from-immunology thesis</li>
          <li><strong>Strategic:</strong> Any AZ BD/M&A in dermatology would signal escalation into Almirall's core markets</li>
        </ul>
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
