// Shared pharma-landscape data + marker factory used by both the live
// dashboard globe and the landing-page mock globe. Keeping a single
// source of truth means renaming a competitor or moving a coordinate
// updates both surfaces in one place.
import maplibregl from "maplibre-gl";

export const ALMIRALL_HQ = {
  lat: 41.4039,
  lng: 2.1374,
  name: "Almirall",
  city: "Barcelona, Spain",
} as const;

export type Competitor = {
  name: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
};

export const COMPETITORS: Competitor[] = [
  { name: "Sanofi", city: "Barcelona", country: "Spain", lat: 41.4087, lng: 2.2174 },
  { name: "Novartis", city: "Barcelona", country: "Spain", lat: 41.4028, lng: 2.1858 },
  { name: "LEO Pharma", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4710, lng: 2.0879 },
  { name: "AbbVie", city: "Madrid", country: "Spain", lat: 40.4769, lng: -3.6792 },
  { name: "Pfizer", city: "Alcobendas", country: "Spain", lat: 40.5366, lng: -3.6307 },
  { name: "Eli Lilly", city: "Alcobendas", country: "Spain", lat: 40.5398, lng: -3.6359 },
  { name: "Johnson & Johnson", city: "Madrid", country: "Spain", lat: 40.4574, lng: -3.6105 },
  { name: "UCB", city: "Madrid", country: "Spain", lat: 40.4419, lng: -3.6809 },
  { name: "Galderma", city: "Madrid", country: "Spain", lat: 40.4360, lng: -3.6784 },
  { name: "Incyte", city: "Madrid", country: "Spain", lat: 40.4279, lng: -3.7032 },
  { name: "Roche", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4685, lng: 2.0846 },
  { name: "Merck", city: "Madrid", country: "Spain", lat: 40.4361, lng: -3.6755 },
  { name: "GSK", city: "Tres Cantos", country: "Spain", lat: 40.6056, lng: -3.7113 },
  { name: "Bayer", city: "Sant Joan Despí", country: "Spain", lat: 41.3676, lng: 2.0563 },
  { name: "Boehringer Ingelheim", city: "Sant Cugat del Vallès", country: "Spain", lat: 41.4760, lng: 2.0723 },
  { name: "AstraZeneca", city: "Madrid", country: "Spain", lat: 40.4530, lng: -3.6877 },
];

export function makePharmaMarker(
  name: string,
  city: string,
  variant: "home" | "rival",
): maplibregl.Marker {
  const label = `${name.toUpperCase()} · ${city.toUpperCase()}`;
  const width = Math.max(180, 70 + label.length * 6.5);
  const el = document.createElement("div");
  el.className = `dashboard-pharma-pin dashboard-pharma-pin--${variant}`;
  el.title = `${name} — ${city}`;
  el.innerHTML = `
    <svg viewBox="0 0 ${width} 80" width="${width}" height="80" xmlns="http://www.w3.org/2000/svg">
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

export function makeAlmirallMarker(): maplibregl.Marker {
  return makePharmaMarker(ALMIRALL_HQ.name, "Barcelona", "home");
}
