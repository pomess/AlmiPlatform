// Shared pharma-landscape data + marker factory used by both the live
// dashboard globe and the landing-page mock globe. Keeping a single
// source of truth means renaming a competitor or moving a coordinate
// updates both surfaces in one place.
import maplibregl from "maplibre-gl";

export const ALMIRALL_HQ = {
  // HQ building fronting Ronda del General Mitre, 151 (Sant Gervasi, 08022).
  // Point sits inside the front building's footprint (OSM way 809175709) so the
  // hologram + camera centre on it rather than the block set back behind it.
  lat: 41.40353,
  lng: 2.13819,
  name: "Almirall",
  city: "Barcelona, Spain",
} as const;

// The home pin's anchor dot is placed at the building's south-west (bottom-left
// on a north-up view) corner so it reads clear of the translucent hologram
// volume rather than being buried in its centre.
export const ALMIRALL_PIN = {
  lat: 41.40335,
  lng: 2.13789,
} as const;

export type Competitor = {
  name: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
  // Curated cover image served from /public/competitors/. Drop a JPG/PNG
  // there with the matching filename and the photo card will pick it up.
  // Falls back to Wikipedia when null. Vite serves /public at the site
  // root, so "/competitors/sanofi.jpg" maps to
  // apps/web/public/competitors/sanofi.jpg.
  photoUrl: string | null;
  // Wikipedia article title used as a fallback when photoUrl is null.
  // Disambiguated where needed because plain "Merck" / "UCB" resolve to
  // disambig pages.
  wikipedia: string;
  // Curated therapy-area shorthand for the photo card. Two or three
  // entries each — picked for the Spain-relevant pipeline so the card
  // reads as competitive-intel, not corporate boilerplate.
  therapyAreas: string[];
};

export const COMPETITORS: Competitor[] = [
  { name: "Sanofi", city: "Barcelona", country: "Spain", lat: 41.4366649, lng: 2.1807982,
    photoUrl: "/competitors/sanofi.jpg", wikipedia: "Sanofi", therapyAreas: ["Immunology", "Vaccines", "Rare disease"] },
  { name: "Novartis", city: "Barcelona", country: "Spain", lat: 41.3981834, lng: 2.1806575,
    photoUrl: "/competitors/novartis.jpg", wikipedia: "Novartis", therapyAreas: ["Cardiovascular", "Oncology", "Immunology"] },
  { name: "LEO Pharma", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4710, lng: 2.0879,
    photoUrl: null, wikipedia: "LEO Pharma", therapyAreas: ["Dermatology", "Thrombosis"] },
  { name: "AbbVie", city: "Madrid", country: "Spain", lat: 40.4769, lng: -3.6792,
    photoUrl: null, wikipedia: "AbbVie", therapyAreas: ["Immunology", "Oncology", "Aesthetics"] },
  { name: "Pfizer", city: "Alcobendas", country: "Spain", lat: 40.5366, lng: -3.6307,
    photoUrl: null, wikipedia: "Pfizer", therapyAreas: ["Vaccines", "Oncology", "Inflammation"] },
  { name: "Eli Lilly", city: "Alcobendas", country: "Spain", lat: 40.5398, lng: -3.6359,
    photoUrl: null, wikipedia: "Eli Lilly and Company", therapyAreas: ["Diabetes", "Oncology", "Immunology"] },
  { name: "Johnson & Johnson", city: "Madrid", country: "Spain", lat: 40.4574, lng: -3.6105,
    photoUrl: null, wikipedia: "Johnson & Johnson", therapyAreas: ["Immunology", "Oncology", "Neuroscience"] },
  { name: "UCB", city: "Madrid", country: "Spain", lat: 40.4419, lng: -3.6809,
    photoUrl: null, wikipedia: "UCB (company)", therapyAreas: ["Immunology", "Neurology", "Bone"] },
  { name: "Galderma", city: "Madrid", country: "Spain", lat: 40.4360, lng: -3.6784,
    photoUrl: null, wikipedia: "Galderma", therapyAreas: ["Dermatology", "Aesthetics"] },
  { name: "Incyte", city: "Madrid", country: "Spain", lat: 40.4279, lng: -3.7032,
    photoUrl: null, wikipedia: "Incyte", therapyAreas: ["Oncology", "Dermatology", "MPN"] },
  { name: "Roche", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4924849, lng: 2.0582393,
    photoUrl: "/competitors/roche.jpg", wikipedia: "Hoffmann-La Roche", therapyAreas: ["Oncology", "Immunology", "Ophthalmology"] },
  { name: "Merck", city: "Madrid", country: "Spain", lat: 40.4361, lng: -3.6755,
    photoUrl: null, wikipedia: "Merck Group", therapyAreas: ["Oncology", "Neurology", "Fertility"] },
  { name: "GSK", city: "Tres Cantos", country: "Spain", lat: 40.6056, lng: -3.7113,
    photoUrl: null, wikipedia: "GSK plc", therapyAreas: ["Vaccines", "HIV", "Respiratory"] },
  { name: "Bayer", city: "Sant Joan Despí", country: "Spain", lat: 41.3696066, lng: 2.0777182,
    photoUrl: "/competitors/bayer.jpg", wikipedia: "Bayer", therapyAreas: ["Cardiovascular", "Oncology", "Women's health"] },
  { name: "Boehringer Ingelheim", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4760, lng: 2.0723,
    photoUrl: null, wikipedia: "Boehringer Ingelheim", therapyAreas: ["Cardiometabolic", "Oncology", "Respiratory"] },
  { name: "AstraZeneca", city: "Barcelona", country: "Spain", lat: 41.3840812, lng: 2.1505114,
    photoUrl: "/competitors/astrazeneca.jpg", wikipedia: "AstraZeneca", therapyAreas: ["Oncology", "Cardiorenal", "Respiratory"] },
];

export function makePharmaMarker(
  name: string,
  city: string,
  variant: "home" | "rival",
): maplibregl.Marker {
  const label = `${name.toUpperCase()} · ${city.toUpperCase()}`;
  // Label is 10px mono with 0.14em letter-spacing (~7.4px advance per glyph).
  // The text starts at x=48, so size the SVG to fit the full label plus a
  // right margin; otherwise long names are clipped by the SVG viewport.
  const width = Math.max(200, 56 + label.length * 7.6);
  const el = document.createElement("div");
  el.className = `dashboard-pharma-pin dashboard-pharma-pin--${variant}`;
  el.title = `${name} — ${city}`;
  el.dataset.company = name;
  // The home pin sits on the always-on HQ hologram, anchored at the building's
  // bottom-left corner — so it mirrors: the anchor dot is on the right and the
  // label/leader extend LEFT onto the dark map, clear of the bright hologram.
  // Rival pins keep the default left-anchored dot with the label to the right.
  if (variant === "home") {
    el.innerHTML = `
      <svg viewBox="0 0 ${width} 80" width="${width}" height="80" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="20" width="${width}" height="55" fill="transparent" class="pharma-pin-hit" />
        <circle cx="${width - 16}" cy="64" r="3" class="pharma-pin-anchor" />
        <circle cx="${width - 16}" cy="64" r="7" class="pharma-pin-home-ring" />
        <path d="M ${width - 16} 64 L ${width - 44} 40 L 10 40" class="pharma-pin-line" />
        <path d="M 10 40 L 10 34" class="pharma-pin-tick" />
        <text x="${width - 48}" y="35" text-anchor="end" class="pharma-pin-label">${label}</text>
      </svg>
    `;
    return new maplibregl.Marker({
      element: el,
      anchor: "bottom-right",
      offset: [16, 16],
    });
  }
  el.innerHTML = `
    <svg viewBox="0 0 ${width} 80" width="${width}" height="80" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="20" width="${width}" height="55" fill="transparent" class="pharma-pin-hit" />
      <circle cx="16" cy="64" r="3" class="pharma-pin-anchor" />
      <circle cx="16" cy="64" r="7" class="pharma-pin-home-ring" />
      <path d="M 16 64 L 44 40 L ${width - 10} 40" class="pharma-pin-line" />
      <path d="M ${width - 10} 40 L ${width - 10} 34" class="pharma-pin-tick" />
      <text x="48" y="35" class="pharma-pin-label">${label}</text>
    </svg>
  `;
  return new maplibregl.Marker({
    element: el,
    anchor: "bottom-left",
    offset: [-16, 16],
  });
}

export function makeCompetitorMarker(c: Competitor): maplibregl.Marker {
  return makePharmaMarker(c.name, c.city, "rival");
}

export function makeCompetitorDotMarker(c: Competitor): maplibregl.Marker {
  const el = document.createElement("div");
  el.className = "dashboard-pharma-pin dashboard-pharma-pin--rival dashboard-pharma-pin--dot";
  el.title = `${c.name} — ${c.city}`;
  el.innerHTML = `
    <svg viewBox="-16 -16 32 32" width="32" height="32" overflow="visible" xmlns="http://www.w3.org/2000/svg">
      <circle cx="0" cy="0" r="2" class="pharma-pin-anchor" />
      <circle cx="0" cy="0" r="5" class="pharma-pin-home-ring" />
    </svg>
  `;
  return new maplibregl.Marker({ element: el, anchor: "center" });
}

export function makeAlmirallMarker(): maplibregl.Marker {
  return makePharmaMarker(ALMIRALL_HQ.name, "Barcelona", "home");
}
