// Bullseye — radial competitive intelligence visualization
// for Atopic Dermatitis (AD), Hidradenitis Suppurativa (HS), and Psoriasis (PSO).
import { useCallback, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

type Indication = "AD" | "HS" | "PSO";
type Phase = "Approved" | "Phase III" | "Phase II" | "Phase I" | "Preclinical";
type Route = "SC" | "IV" | "Oral" | "Topical";
type Modality = "mAb" | "Small molecule" | "Nanobody" | "Affibody" | "Bispecific";

type Drug = {
  brand: string;
  inn: string;
  company: string;
  target: string;
  modality: Modality;
  indication: Indication;
  status: Phase;
  firstApproval: string;
  route: Route;
  notes: string;
  phaseYears?: Partial<Record<Phase, string>>;
};

const DRUGS: Drug[] = [
  // ===================== Atopic Dermatitis =====================
  // --- Approved ---
  { brand: "Dupixent", inn: "dupilumab", company: "Sanofi / Regeneron", target: "IL-4Rα", modality: "mAb", indication: "AD", status: "Approved", firstApproval: "2017", route: "SC", notes: "Category-defining biologic. Broad label down to infants.", phaseYears: { Preclinical: "2008", "Phase I": "2010", "Phase II": "2012", "Phase III": "2014", Approved: "2017" } },
  { brand: "Ebglyss", inn: "lebrikizumab", company: "Almirall / Eli Lilly", target: "IL-13", modality: "mAb", indication: "AD", status: "Approved", firstApproval: "2024", route: "SC", notes: "Almirall holds EU rights. Q4 maintenance dosing positioning.", phaseYears: { Preclinical: "2014", "Phase I": "2016", "Phase II": "2018", "Phase III": "2021", Approved: "2024" } },
  { brand: "Adbry", inn: "tralokinumab", company: "LEO Pharma", target: "IL-13", modality: "mAb", indication: "AD", status: "Approved", firstApproval: "2021", route: "SC", notes: "First IL-13 selective biologic for AD.", phaseYears: { Preclinical: "2011", "Phase I": "2013", "Phase II": "2015", "Phase III": "2018", Approved: "2021" } },
  { brand: "Nemluvio", inn: "nemolizumab", company: "Galderma", target: "IL-31RA", modality: "mAb", indication: "AD", status: "Approved", firstApproval: "2024", route: "SC", notes: "Itch-first mechanism. Also approved in prurigo nodularis.", phaseYears: { Preclinical: "2013", "Phase I": "2015", "Phase II": "2017", "Phase III": "2021", Approved: "2024" } },
  { brand: "Rinvoq", inn: "upadacitinib", company: "AbbVie", target: "JAK1", modality: "Small molecule", indication: "AD", status: "Approved", firstApproval: "2022", route: "Oral", notes: "Oral JAK1. Boxed warning constrains first-line use.", phaseYears: { Preclinical: "2013", "Phase I": "2015", "Phase II": "2017", "Phase III": "2019", Approved: "2022" } },
  { brand: "Cibinqo", inn: "abrocitinib", company: "Pfizer", target: "JAK1", modality: "Small molecule", indication: "AD", status: "Approved", firstApproval: "2022", route: "Oral", notes: "Oral JAK1. Same class warnings as Rinvoq.", phaseYears: { Preclinical: "2014", "Phase I": "2016", "Phase II": "2018", "Phase III": "2020", Approved: "2022" } },
  // --- Phase III ---
  { brand: "Rocatinlimab", inn: "rocatinlimab", company: "Pfizer", target: "OX40", modality: "mAb", indication: "AD", status: "Phase III", firstApproval: "—", route: "SC", notes: "Anti-OX40. Targets T-cell co-stimulation. Phase III ROCKET program.", phaseYears: { Preclinical: "2016", "Phase I": "2018", "Phase II": "2020", "Phase III": "2023" } },
  { brand: "Amlitelimab", inn: "amlitelimab", company: "Sanofi", target: "OX40L", modality: "mAb", indication: "AD", status: "Phase III", firstApproval: "—", route: "SC", notes: "Anti-OX40 ligand. Non-depleting. COAST Phase III ongoing.", phaseYears: { Preclinical: "2017", "Phase I": "2019", "Phase II": "2021", "Phase III": "2024" } },
  { brand: "CM310", inn: "CM310", company: "Keymed Biosciences", target: "IL-4Rα", modality: "mAb", indication: "AD", status: "Phase III", firstApproval: "—", route: "SC", notes: "Chinese dupilumab competitor. Phase III in China.", phaseYears: { Preclinical: "2017", "Phase I": "2019", "Phase II": "2021", "Phase III": "2023" } },
  { brand: "Baricitinib", inn: "baricitinib", company: "Eli Lilly", target: "JAK1/2", modality: "Small molecule", indication: "AD", status: "Phase III", firstApproval: "—", route: "Oral", notes: "Olumiant label expansion. EU approved for AD, US not pursued.", phaseYears: { Preclinical: "2010", "Phase I": "2012", "Phase II": "2017", "Phase III": "2019" } },
  // --- Phase II ---
  { brand: "Rademikibart", inn: "rademikibart", company: "Hengrui", target: "IL-4Rα", modality: "mAb", indication: "AD", status: "Phase II", firstApproval: "—", route: "SC", notes: "Chinese IL-4Rα antibody. Phase II dose-finding.", phaseYears: { Preclinical: "2018", "Phase I": "2020", "Phase II": "2022" } },
  { brand: "NM26", inn: "NM26", company: "Harbour BioMed", target: "IL-4Rα/IL-31", modality: "Bispecific", indication: "AD", status: "Phase II", firstApproval: "—", route: "SC", notes: "Bispecific antibody. Dual IL-4Rα + IL-31 blockade.", phaseYears: { Preclinical: "2019", "Phase I": "2021", "Phase II": "2023" } },
  { brand: "CBP-201", inn: "CBP-201", company: "Connect Biopharma", target: "IL-4Rα", modality: "mAb", indication: "AD", status: "Phase II", firstApproval: "—", route: "SC", notes: "Anti-IL-4Rα. Phase II data positive vs placebo.", phaseYears: { Preclinical: "2017", "Phase I": "2019", "Phase II": "2021" } },
  { brand: "Tapinarof", inn: "tapinarof", company: "Dermavant", target: "AhR", modality: "Small molecule", indication: "AD", status: "Phase II", firstApproval: "—", route: "Topical", notes: "AhR agonist. Topical non-steroidal. Approved for psoriasis.", phaseYears: { Preclinical: "2015", "Phase I": "2017", "Phase II": "2022" } },
  { brand: "Bermekimab", inn: "bermekimab", company: "Janssen", target: "IL-1α", modality: "mAb", indication: "AD", status: "Phase II", firstApproval: "—", route: "SC", notes: "Anti-IL-1α. Novel upstream target in AD inflammation.", phaseYears: { Preclinical: "2014", "Phase I": "2017", "Phase II": "2021" } },
  // --- Phase I ---
  { brand: "SAR443765", inn: "SAR443765", company: "Sanofi", target: "IL-4Rα/IL-13", modality: "Bispecific", indication: "AD", status: "Phase I", firstApproval: "—", route: "SC", notes: "Next-gen bispecific. Could supersede dupilumab.", phaseYears: { Preclinical: "2020", "Phase I": "2023" } },
  { brand: "ABBV-0222", inn: "ABBV-0222", company: "AbbVie", target: "IL-13", modality: "mAb", indication: "AD", status: "Phase I", firstApproval: "—", route: "SC", notes: "AbbVie backup to upadacitinib in biologics.", phaseYears: { Preclinical: "2021", "Phase I": "2024" } },
  { brand: "MRT-6160", inn: "MRT-6160", company: "MiRTx Therapeutics", target: "miR-155", modality: "Small molecule", indication: "AD", status: "Phase I", firstApproval: "—", route: "SC", notes: "microRNA inhibitor. Novel mechanism of action.", phaseYears: { Preclinical: "2020", "Phase I": "2024" } },
  // --- Preclinical ---
  { brand: "RG7880", inn: "RG7880", company: "Roche", target: "TSLP", modality: "mAb", indication: "AD", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Anti-TSLP for atopic disease. Early discovery stage.", phaseYears: { Preclinical: "2023" } },
  { brand: "PRV-015", inn: "PRV-015", company: "Provention Bio", target: "IL-15", modality: "mAb", indication: "AD", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Anti-IL-15. IND-enabling for atopic indications.", phaseYears: { Preclinical: "2024" } },

  // ===================== Hidradenitis Suppurativa =====================
  // --- Approved ---
  { brand: "Humira", inn: "adalimumab", company: "AbbVie", target: "TNF-α", modality: "mAb", indication: "HS", status: "Approved", firstApproval: "2015", route: "SC", notes: "First and long-time only approved HS biologic. Biosimilars now active.", phaseYears: { Preclinical: "2001", "Phase I": "2003", "Phase II": "2010", "Phase III": "2013", Approved: "2015" } },
  { brand: "Cosentyx", inn: "secukinumab", company: "Novartis", target: "IL-17A", modality: "mAb", indication: "HS", status: "Approved", firstApproval: "2023", route: "SC", notes: "Second-ever HS biologic. Expanded label vs Humira.", phaseYears: { Preclinical: "2010", "Phase I": "2013", "Phase II": "2018", "Phase III": "2020", Approved: "2023" } },
  { brand: "Bimzelx", inn: "bimekizumab", company: "UCB", target: "IL-17A/F", modality: "mAb", indication: "HS", status: "Approved", firstApproval: "2024", route: "SC", notes: "Dual IL-17A/F inhibition. Strong HiSCR75 signal.", phaseYears: { Preclinical: "2012", "Phase I": "2015", "Phase II": "2019", "Phase III": "2021", Approved: "2024" } },
  // --- Phase III ---
  { brand: "Sonelokimab", inn: "sonelokimab", company: "MoonLake", target: "IL-17A/F", modality: "Nanobody", indication: "HS", status: "Phase III", firstApproval: "—", route: "SC", notes: "Trimeric nanobody. VELA Phase III readouts watched closely.", phaseYears: { Preclinical: "2016", "Phase I": "2019", "Phase II": "2021", "Phase III": "2024" } },
  { brand: "Povorcitinib", inn: "povorcitinib", company: "Incyte", target: "JAK1", modality: "Small molecule", indication: "HS", status: "Phase III", firstApproval: "—", route: "Oral", notes: "Oral JAK1 in HS — would be first oral systemic if approved.", phaseYears: { Preclinical: "2017", "Phase I": "2019", "Phase II": "2021", "Phase III": "2024" } },
  { brand: "Eltrekibart", inn: "eltrekibart", company: "AbbVie", target: "IL-1RAcP", modality: "mAb", indication: "HS", status: "Phase III", firstApproval: "—", route: "SC", notes: "Anti-IL-1 receptor accessory protein. Broad IL-1 blockade.", phaseYears: { Preclinical: "2016", "Phase I": "2018", "Phase II": "2021", "Phase III": "2024" } },
  { brand: "Izokibep", inn: "izokibep", company: "Acelyrin", target: "IL-17A", modality: "Affibody", indication: "HS", status: "Phase III", firstApproval: "—", route: "SC", notes: "Small-format IL-17A inhibitor. Moved to Phase III from IIb.", phaseYears: { Preclinical: "2016", "Phase I": "2018", "Phase II": "2020", "Phase III": "2024" } },
  // --- Phase II ---
  { brand: "Spesolimab", inn: "spesolimab", company: "Boehringer", target: "IL-36R", modality: "mAb", indication: "HS", status: "Phase II", firstApproval: "—", route: "IV", notes: "Anti-IL-36 receptor. Approved for GPP flares; HS Phase II.", phaseYears: { Preclinical: "2013", "Phase I": "2016", "Phase II": "2023" } },
  { brand: "Ordesekimab", inn: "ordesekimab", company: "Novartis", target: "IL-17A/F", modality: "Nanobody", indication: "HS", status: "Phase II", firstApproval: "—", route: "SC", notes: "Follow-on IL-17 nanobody. Differentiation from Cosentyx.", phaseYears: { Preclinical: "2018", "Phase I": "2021", "Phase II": "2024" } },
  { brand: "Ruxolitinib", inn: "ruxolitinib", company: "Incyte", target: "JAK1/2", modality: "Small molecule", indication: "HS", status: "Phase II", firstApproval: "—", route: "Topical", notes: "Topical JAK. Opzelura label expansion study for mild HS.", phaseYears: { Preclinical: "2012", "Phase I": "2015", "Phase II": "2023" } },
  { brand: "LY3471851", inn: "LY3471851", company: "Eli Lilly", target: "IL-17A/F", modality: "Bispecific", indication: "HS", status: "Phase II", firstApproval: "—", route: "SC", notes: "Bispecific IL-17A/F. Lilly entry into HS pipeline.", phaseYears: { Preclinical: "2019", "Phase I": "2022", "Phase II": "2024" } },
  // --- Phase I ---
  { brand: "CALY-002", inn: "CALY-002", company: "Calendula Biotech", target: "Treg", modality: "Small molecule", indication: "HS", status: "Phase I", firstApproval: "—", route: "SC", notes: "Regulatory T-cell modulator. Novel immunomodulatory approach.", phaseYears: { Preclinical: "2021", "Phase I": "2024" } },
  { brand: "PF-07038124", inn: "PF-07038124", company: "Pfizer", target: "TYK2/JAK1", modality: "Small molecule", indication: "HS", status: "Phase I", firstApproval: "—", route: "Topical", notes: "Dual TYK2/JAK1 topical. Systemic-free JAK inhibition.", phaseYears: { Preclinical: "2020", "Phase I": "2023" } },
  { brand: "SAR444656", inn: "SAR444656", company: "Sanofi", target: "IL-17A/F", modality: "Bispecific", indication: "HS", status: "Phase I", firstApproval: "—", route: "SC", notes: "Next-gen bispecific for inflammatory skin disease.", phaseYears: { Preclinical: "2021", "Phase I": "2024" } },
  // --- Preclinical ---
  { brand: "BMS-986340", inn: "BMS-986340", company: "Bristol Myers Squibb", target: "IL-13/TSLP", modality: "Bispecific", indication: "HS", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Dual-target bispecific. Early IND-enabling studies.", phaseYears: { Preclinical: "2024" } },
  { brand: "REGN-7257", inn: "REGN-7257", company: "Regeneron", target: "IL-1β", modality: "mAb", indication: "HS", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Anti-IL-1β. Precision approach to HS inflammation.", phaseYears: { Preclinical: "2023" } },

  // ===================== Psoriasis =====================
  // --- Approved ---
  { brand: "Ilumetri", inn: "tildrakizumab", company: "Almirall / Sun Pharma", target: "IL-23p19", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2018", route: "SC", notes: "Almirall holds EU rights. Anti-IL-23p19. Q12W maintenance.", phaseYears: { Preclinical: "2009", "Phase I": "2011", "Phase II": "2014", "Phase III": "2016", Approved: "2018" } },
  { brand: "Skyrizi", inn: "risankizumab", company: "AbbVie", target: "IL-23p19", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2019", route: "SC", notes: "Best-in-class IL-23. PASI 100 rates ~60%. Expanding into PsA, IBD.", phaseYears: { Preclinical: "2010", "Phase I": "2013", "Phase II": "2015", "Phase III": "2017", Approved: "2019" } },
  { brand: "Tremfya", inn: "guselkumab", company: "Janssen", target: "IL-23p19", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2017", route: "SC", notes: "First-in-class selective IL-23p19. Durable PASI response.", phaseYears: { Preclinical: "2009", "Phase I": "2012", "Phase II": "2014", "Phase III": "2016", Approved: "2017" } },
  { brand: "Cosentyx", inn: "secukinumab", company: "Novartis", target: "IL-17A", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2015", route: "SC", notes: "First IL-17A inhibitor. Broad label across PsO, PsA, axSpA.", phaseYears: { Preclinical: "2006", "Phase I": "2008", "Phase II": "2011", "Phase III": "2013", Approved: "2015" } },
  { brand: "Taltz", inn: "ixekizumab", company: "Eli Lilly", target: "IL-17A", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2016", route: "SC", notes: "High-affinity IL-17A. Rapid onset within 1 week.", phaseYears: { Preclinical: "2007", "Phase I": "2009", "Phase II": "2012", "Phase III": "2014", Approved: "2016" } },
  { brand: "Bimzelx", inn: "bimekizumab", company: "UCB", target: "IL-17A/F", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2023", route: "SC", notes: "Dual IL-17A/F. Highest PASI 100 rates in head-to-head trials.", phaseYears: { Preclinical: "2012", "Phase I": "2015", "Phase II": "2017", "Phase III": "2020", Approved: "2023" } },
  { brand: "Stelara", inn: "ustekinumab", company: "Janssen", target: "IL-12/23", modality: "mAb", indication: "PSO", status: "Approved", firstApproval: "2009", route: "SC", notes: "Anti-IL-12/23 p40. Workhorse biologic. Biosimilars entering.", phaseYears: { Preclinical: "2001", "Phase I": "2004", "Phase II": "2005", "Phase III": "2007", Approved: "2009" } },
  { brand: "Sotyktu", inn: "deucravacitinib", company: "Bristol Myers Squibb", target: "TYK2", modality: "Small molecule", indication: "PSO", status: "Approved", firstApproval: "2022", route: "Oral", notes: "First oral TYK2 inhibitor. Avoids JAK1/2/3 side effects.", phaseYears: { Preclinical: "2015", "Phase I": "2017", "Phase II": "2019", "Phase III": "2020", Approved: "2022" } },
  // --- Phase III ---
  { brand: "Tapinarof", inn: "tapinarof", company: "Dermavant", target: "AhR", modality: "Small molecule", indication: "PSO", status: "Approved", firstApproval: "2022", route: "Topical", notes: "Topical AhR agonist. Non-steroidal. Once-daily cream.", phaseYears: { Preclinical: "2014", "Phase I": "2016", "Phase II": "2018", "Phase III": "2020", Approved: "2022" } },
  { brand: "JNJ-2113", inn: "JNJ-2113", company: "Janssen", target: "IL-23p19", modality: "Small molecule", indication: "PSO", status: "Phase III", firstApproval: "—", route: "Oral", notes: "Oral peptide IL-23 blocker. Game-changer if approved — oral biologic-like efficacy.", phaseYears: { Preclinical: "2018", "Phase I": "2020", "Phase II": "2022", "Phase III": "2024" } },
  { brand: "Zasocitinib", inn: "zasocitinib", company: "Nimbus / Takeda", target: "TYK2", modality: "Small molecule", indication: "PSO", status: "Phase III", firstApproval: "—", route: "Oral", notes: "Allosteric TYK2 inhibitor. Taken from Nimbus for $6B.", phaseYears: { Preclinical: "2018", "Phase I": "2021", "Phase II": "2023", "Phase III": "2025" } },
  { brand: "Sonelokimab", inn: "sonelokimab", company: "MoonLake", target: "IL-17A/F", modality: "Nanobody", indication: "PSO", status: "Phase III", firstApproval: "—", route: "SC", notes: "Trimeric nanobody. High PASI 90/100 in Phase IIb.", phaseYears: { Preclinical: "2016", "Phase I": "2018", "Phase II": "2020", "Phase III": "2023" } },
  // --- Phase II ---
  { brand: "DC-806", inn: "DC-806", company: "Bristol Myers Squibb", target: "TYK2", modality: "Small molecule", indication: "PSO", status: "Phase II", firstApproval: "—", route: "Oral", notes: "Next-gen oral TYK2 after Sotyktu. Improved potency.", phaseYears: { Preclinical: "2019", "Phase I": "2022", "Phase II": "2024" } },
  { brand: "ESK-001", inn: "ESK-001", company: "Protagonist", target: "IL-17A", modality: "Small molecule", indication: "PSO", status: "Phase II", firstApproval: "—", route: "Oral", notes: "Oral cyclic peptide IL-17A inhibitor. Oral biologic concept.", phaseYears: { Preclinical: "2019", "Phase I": "2021", "Phase II": "2024" } },
  { brand: "Izokibep", inn: "izokibep", company: "Acelyrin", target: "IL-17A", modality: "Affibody", indication: "PSO", status: "Phase II", firstApproval: "—", route: "SC", notes: "Small-format IL-17A. Also in PsA study.", phaseYears: { Preclinical: "2016", "Phase I": "2018", "Phase II": "2022" } },
  // --- Phase I ---
  { brand: "NIM-1324", inn: "NIM-1324", company: "Nimbus", target: "TYK2", modality: "Small molecule", indication: "PSO", status: "Phase I", firstApproval: "—", route: "Oral", notes: "Third-gen TYK2 candidate. Retained after Takeda deal.", phaseYears: { Preclinical: "2022", "Phase I": "2025" } },
  { brand: "ABT-503", inn: "ABT-503", company: "AbbVie", target: "IL-23/IL-17", modality: "Bispecific", indication: "PSO", status: "Phase I", firstApproval: "—", route: "SC", notes: "Bispecific dual IL-23 + IL-17 blockade in one molecule.", phaseYears: { Preclinical: "2021", "Phase I": "2024" } },
  // --- Preclinical ---
  { brand: "COVA-322", inn: "COVA-322", company: "Covagen / Janssen", target: "TNF/IL-17A", modality: "Bispecific", indication: "PSO", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Bispecific Fynomer. TNF + IL-17A dual targeting.", phaseYears: { Preclinical: "2023" } },
  { brand: "PRV-300", inn: "PRV-300", company: "Provention Bio", target: "IL-15", modality: "mAb", indication: "PSO", status: "Preclinical", firstApproval: "—", route: "SC", notes: "Anti-IL-15. Targets tissue-resident memory T-cells.", phaseYears: { Preclinical: "2024" } },
];

const PHASES: Phase[] = ["Preclinical", "Phase I", "Phase II", "Phase III", "Approved"];
const PHASE_RADII = [0.86, 0.7, 0.54, 0.4, 0.26];

// Dots go in the BAND between rings, not on the ring line
// Bands: Approved = center..0.26, PhIII = 0.26..0.4, PhII = 0.4..0.54, PhI = 0.54..0.7, Preclin = 0.7..0.86
const PHASE_DOT_RADII = [0.78, 0.62, 0.47, 0.33, 0.18];

const MODALITY_COLORS: Record<Modality, string> = {
  "mAb": "#4a9eff",
  "Small molecule": "#ef5350",
  "Nanobody": "#66bb6a",
  "Affibody": "#fdd835",
  "Bispecific": "#ab47bc",
};

function polarToXY(angleDeg: number, radius: number, cx = 50, cy = 50) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
}

export function BullseyePage() {
  const [indication, setIndication] = useState<Indication>("AD");
  const [selected, setSelected] = useState<Drug | null>(
    DRUGS.find((d) => d.brand === "Ebglyss") ?? null,
  );
  const [snapshotYear, setSnapshotYear] = useState<number | null>(null);

  // Zoom and pan move the full chart stage together: SVG, background, labels.
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0 });
  const panOrigin = useRef({ x: 0, y: 0 });

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.min(4, Math.max(1, z - e.deltaY * 0.002)));
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    panStart.current = { x: e.clientX, y: e.clientY };
    panOrigin.current = { ...pan };
  }, [pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning) return;
    setPan({
      x: panOrigin.current.x + e.clientX - panStart.current.x,
      y: panOrigin.current.y + e.clientY - panStart.current.y,
    });
  }, [isPanning]);

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);
  const hasViewOffset = zoom !== 1 || pan.x !== 0 || pan.y !== 0;

  const filtered = useMemo(
    () => DRUGS.filter((d) => d.indication === indication),
    [indication],
  );

  // For timeline slider: resolve where a drug was at a given year.
  const getPhaseAtYear = useCallback((drug: Drug, year: number): Phase | null => {
    let latest: Phase | null = null;
    for (const p of PHASES) {
      const entered = parseInt(drug.phaseYears?.[p] ?? "9999");
      if (entered <= year) latest = p;
    }
    return latest;
  }, []);

  const companies = useMemo(() => {
    const set = new Set<string>();
    filtered.forEach((d) => set.add(d.company));
    return Array.from(set).sort();
  }, [filtered]);

  const indicationLabel: Record<Indication, string> = {
    AD: "Atopic Dermatitis",
    HS: "Hidradenitis Suppurativa",
    PSO: "Psoriasis",
  };

  // Reserve a wedge at the top for phase labels ("cheese cut")
  const LABEL_WEDGE = 40; // degrees reserved
  const ARC_START = -90 + LABEL_WEDGE / 2; // companies start after the wedge
  const ARC_SPAN = 360 - LABEL_WEDGE; // remaining arc for companies

  const dots = useMemo(() => {
    const angleStep = ARC_SPAN / companies.length;
    const companyAngles: Record<string, number> = {};
    companies.forEach((c, i) => {
      companyAngles[c] = ARC_START + (i + 0.5) * angleStep;
    });

    const groups: Record<string, Drug[]> = {};
    filtered.forEach((d) => {
      const effectivePhase = snapshotYear ? getPhaseAtYear(d, snapshotYear) : d.status;
      if (!effectivePhase) return;
      const key = `${d.company}__${effectivePhase}`;
      if (!groups[key]) groups[key] = [];
      groups[key].push(d);
    });

    return filtered.map((d) => {
      const effectivePhase = snapshotYear ? getPhaseAtYear(d, snapshotYear) : d.status;
      if (!effectivePhase) return null;

      const phaseIdx = PHASES.indexOf(effectivePhase);
      const radius = phaseIdx >= 0 ? PHASE_DOT_RADII[phaseIdx] : 0.78;
      const baseAngle = companyAngles[d.company] ?? 0;

      const key = `${d.company}__${effectivePhase}`;
      const siblings = groups[key] || [];
      const idx = siblings.indexOf(d);
      const count = siblings.length;
      const aStep = ARC_SPAN / companies.length;
      const spread = count > 1 ? Math.min(aStep * 0.6, count * 5) : 0;
      const offset = count > 1 ? (idx - (count - 1) / 2) * (spread / count) : 0;
      const radiusJitter = count > 2 ? (idx % 2 === 0 ? 0.03 : -0.03) : 0;
      const finalRadius = (radius + radiusJitter) * 50;
      const angle = baseAngle + offset;

      const pos = polarToXY(angle, finalRadius);
      return { drug: d, ...pos, angle };
    }).filter(Boolean) as { drug: Drug; x: number; y: number; angle: number }[];
  }, [filtered, companies, snapshotYear, getPhaseAtYear]);

  return (
    <div className="bullseye-page page">
      <div className={`bullseye-layout${selected ? " has-sidebar" : ""}`}>
        <div className="bullseye-main">
          <div className="page-head">
            <span className="eyebrow">COMPETITIVE INTELLIGENCE · ALMIRALL</span>
            <h1>Bullseye</h1>
          </div>

          <div className="bullseye-controls">
            <div className="filter-seg">
              {(["AD", "HS", "PSO"] as Indication[]).map((id) => (
                <button
                  key={id}
                  className={indication === id ? "active" : ""}
                  onClick={() => { setIndication(id); setSelected(null); }}
                >
                  {indicationLabel[id]}
                  <span className="ct">{
                    snapshotYear
                      ? DRUGS.filter((d) => d.indication === id && getPhaseAtYear(d, snapshotYear)).length
                      : DRUGS.filter((d) => d.indication === id).length
                  }</span>
                </button>
              ))}
            </div>
            <div className="bull-legend">
              {(Object.entries(MODALITY_COLORS) as [Modality, string][]).map(([mod, color]) => (
                <span className="leg-item" key={mod}>
                  <i className="leg-dot" style={{ background: color }} />
                  {mod}
                </span>
              ))}
            </div>
          </div>

          <div
            className={`bull-chart-wrap${isPanning ? " is-panning" : ""}`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            {hasViewOffset && (
              <button
                className="bull-zoom-reset"
                onMouseDown={(e) => e.stopPropagation()}
                onClick={resetView}
              >
                Reset
              </button>
            )}
            <div
              className="bull-chart-stage"
              style={{
                "--bull-zoom": zoom,
                "--bull-pan-x": `${pan.x}px`,
                "--bull-pan-y": `${pan.y}px`,
              } as CSSProperties}
              onWheel={handleWheel}
            >
              <div className="bull-chart-bg" />
              <svg
                viewBox="0 0 100 100"
                className="bull-svg"
                onClick={(e) => {
                  const t = e.target as SVGElement;
                  if (!t.closest(".bull-dot-group")) setSelected(null);
                }}
              >
                {/* Sector dividers */}
                {companies.map((_, i) => {
                  const angleStep = ARC_SPAN / companies.length;
                  const angle = ARC_START + i * angleStep;
                  const inner = polarToXY(angle, 8);
                  const outer = polarToXY(angle, 46);
                  return (
                    <line
                      key={`sec-${i}`}
                      x1={inner.x} y1={inner.y}
                      x2={outer.x} y2={outer.y}
                      className="bull-sector-line"
                    />
                  );
                })}

                {/* Concentric rings */}
                {PHASE_RADII.map((r, i) => (
                  <circle key={i} cx="50" cy="50" r={r * 50} className="bull-ring" />
                ))}

                {/* Phase labels in the reserved wedge at top */}
                {PHASES.map((phase, i) => {
                  const r = PHASE_RADII[i] * 50;
                  const pos = polarToXY(-90, r);
                  return (
                    <text key={phase} x={pos.x} y={pos.y + 1.2} className="bull-phase-label">
                      {phase}
                    </text>
                  );
                })}

                {/* Wedge boundary lines */}
                <line
                  x1={polarToXY(ARC_START, 8).x} y1={polarToXY(ARC_START, 8).y}
                  x2={polarToXY(ARC_START, 46).x} y2={polarToXY(ARC_START, 46).y}
                  className="bull-wedge-line"
                />
                <line
                  x1={polarToXY(-90 - LABEL_WEDGE / 2, 8).x} y1={polarToXY(-90 - LABEL_WEDGE / 2, 8).y}
                  x2={polarToXY(-90 - LABEL_WEDGE / 2, 46).x} y2={polarToXY(-90 - LABEL_WEDGE / 2, 46).y}
                  className="bull-wedge-line"
                />

                {/* Drug dots with inline labels */}
                {dots.map(({ drug, x, y }) => {
                  const isSelected = selected?.brand === drug.brand;
                  const isAlmirall = drug.company.toLowerCase().includes("almirall");
                  const labelX = x + 2;
                  const labelY = y + 0.5;
                  return (
                    <g
                      key={drug.brand + drug.inn}
                      className="bull-dot-group"
                      onClick={(e) => { e.stopPropagation(); setSelected(drug); }}
                    >
                      {isAlmirall && (
                        <circle cx={x} cy={y} r="2.6" className="bull-dot-halo" />
                      )}
                      {isSelected && (
                        <circle cx={x} cy={y} r="3" className="bull-dot-pulse" />
                      )}
                      <circle
                        cx={x} cy={y}
                        r={isSelected ? "1.6" : "1.2"}
                        className={`bull-dot${isSelected ? " active" : ""}${isAlmirall ? " almirall" : ""}`}
                        style={{ fill: MODALITY_COLORS[drug.modality], transition: "cx 500ms ease, cy 500ms ease, opacity 400ms ease" }}
                      />
                      <text x={labelX} y={labelY} className={`bull-dot-label${isSelected ? " active" : ""}`}>
                        {drug.brand.length > 12 ? drug.brand.slice(0, 10) + "…" : drug.brand}
                      </text>
                    </g>
                  );
                })}
              </svg>

              {/* Company labels as HTML (always horizontal) */}
              <div className="bull-company-labels">
                {companies.map((comp, i) => {
                  const angleStep = ARC_SPAN / companies.length;
                  const angle = ARC_START + (i + 0.5) * angleStep;
                  const pos = polarToXY(angle, 50);
                  const left = `${pos.x}%`;
                  const top = `${pos.y}%`;
                  return (
                    <span
                      key={comp}
                      className="bull-comp-label"
                      style={{ left, top }}
                    >
                      {comp.length > 20 ? comp.slice(0, 18) + "…" : comp}
                    </span>
                  );
                })}
              </div>

              {/* Center label */}
              <div className="bull-center-label">
                <span className="bull-center-title">{indication}</span>
                <span className="bull-center-sub">{indicationLabel[indication]}</span>
              </div>
            </div>
          </div>

          {/* Timeline slider */}
          <div className="bull-timeline-slider">
            <label className="bull-tl-slider-label">
              {snapshotYear ? snapshotYear : "Live"}
            </label>
            <input
              type="range"
              min={2001}
              max={2026}
              step={1}
              value={snapshotYear ?? 2026}
              onChange={(e) => {
                const v = parseInt(e.target.value);
                setSnapshotYear(v >= 2026 ? null : v);
              }}
              className="bull-tl-range"
            />
            <div className="bull-tl-ticks">
              <span>2001</span>
              <span>2008</span>
              <span>2015</span>
              <span>2022</span>
              <span>Live</span>
            </div>
            <span className="bull-tl-action-slot">
              <button
                className="bull-tl-live-btn"
                onClick={() => setSnapshotYear(null)}
                disabled={!snapshotYear}
                aria-hidden={!snapshotYear}
              >
                Back to Live
              </button>
            </span>
          </div>
        </div>

        {/* Sidebar */}
        {selected && (
          <aside className="bull-sidebar">
            <div className="bull-sb-head">
              <button className="bull-sb-close" onClick={() => setSelected(null)} aria-label="Close">×</button>
              <div className="bull-sb-dot-preview" style={{ background: MODALITY_COLORS[selected.modality] }} />
              <h2>{selected.brand}</h2>
              <p className="bull-sb-inn">{selected.inn}</p>
            </div>

            <dl className="bull-sb-meta">
              <div className="bull-sb-row">
                <dt>Target</dt>
                <dd><span className="bull-sb-tag accent">{selected.target}</span></dd>
              </div>
              <div className="bull-sb-row">
                <dt>Mechanism</dt>
                <dd>{selected.modality}</dd>
              </div>
              <div className="bull-sb-row">
                <dt>Active Org.</dt>
                <dd>{selected.company}</dd>
              </div>
              <div className="bull-sb-row">
                <dt>Indication</dt>
                <dd>{indicationLabel[selected.indication]}</dd>
              </div>
              <div className="bull-sb-row">
                <dt>Route</dt>
                <dd><span className="bull-sb-tag">{selected.route}</span></dd>
              </div>
              <div className="bull-sb-row">
                <dt>Highest Phase</dt>
                <dd>
                  <span className={"status-pill phase-" + selected.status.replace(/\s+/g, "-")}>
                    {selected.status}
                  </span>
                </dd>
              </div>
              {selected.firstApproval !== "—" && (
                <div className="bull-sb-row">
                  <dt>First Approval</dt>
                  <dd>{selected.firstApproval}</dd>
                </div>
              )}
            </dl>

            <div className="bull-sb-notes">
              <h4>Notes</h4>
              <p>{selected.notes}</p>
            </div>

            <div className="bull-sb-timeline">
              <h4>Development Timeline</h4>
              <div className="bull-tl">
                {PHASES.map((phase) => {
                  const isCurrent = phase === selected.status;
                  const phaseIdx = PHASES.indexOf(phase);
                  const currentIdx = PHASES.indexOf(selected.status);
                  const isPast = phaseIdx < currentIdx;
                  const year = selected.phaseYears?.[phase];
                  const isFuture = phaseIdx > currentIdx;
                  return (
                    <div key={phase} className={`bull-tl-step${isCurrent ? " current" : ""}${isPast ? " past" : ""}${isFuture ? " future" : ""}`}>
                      <div className="bull-tl-marker" />
                      <span className="bull-tl-label">{phase}</span>
                      {year && <span className="bull-tl-year">{year}</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
