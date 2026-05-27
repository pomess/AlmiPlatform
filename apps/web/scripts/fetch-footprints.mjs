/**
 * Offline script — queries Nominatim for competitor site polygons and saves
 * the result as a static JSON that the hologram layer loads at runtime.
 *
 * Usage:  node apps/web/scripts/fetch-footprints.mjs
 *
 * Nominatim rate-limit: 1 req/s with a User-Agent. The script sleeps between
 * calls. For competitors Nominatim can't resolve, procedural fallback shapes
 * (L-shapes, T-shapes, tower+annex) are generated deterministically.
 */

import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = resolve(__dirname, "../src/data/footprints.json");

const COMPETITORS = [
  { name: "Sanofi", lat: 41.4087, lng: 2.2174, query: "Sanofi+Barcelona+Spain" },
  { name: "Novartis", lat: 41.3981834, lng: 2.1806575, query: "Novartis+Barcelona+Spain" },
  { name: "LEO Pharma", lat: 41.4710, lng: 2.0879, query: "LEO+Pharma+Sant+Cugat" },
  { name: "AbbVie", lat: 40.4769, lng: -3.6792, query: "AbbVie+Madrid+Spain" },
  { name: "Pfizer", lat: 40.5366, lng: -3.6307, query: "Pfizer+Alcobendas+Spain" },
  { name: "Eli Lilly", lat: 40.5398, lng: -3.6359, query: "Eli+Lilly+Alcobendas" },
  { name: "Johnson & Johnson", lat: 40.4574, lng: -3.6105, query: "Johnson+Johnson+Madrid" },
  { name: "UCB", lat: 40.4419, lng: -3.6809, query: "UCB+Pharma+Madrid" },
  { name: "Galderma", lat: 40.4360, lng: -3.6784, query: "Galderma+Madrid" },
  { name: "Incyte", lat: 40.4279, lng: -3.7032, query: "Incyte+Madrid" },
  { name: "Roche", lat: 41.4924849, lng: 2.0582393, query: "Roche+Sant+Cugat" },
  { name: "Merck", lat: 40.4361, lng: -3.6755, query: "Merck+Madrid+Spain" },
  { name: "GSK", lat: 40.6056, lng: -3.7113, query: "GSK+Tres+Cantos" },
  { name: "Bayer", lat: 41.3696066, lng: 2.0777182, query: "Bayer+Sant+Joan+Despi" },
  { name: "Boehringer Ingelheim", lat: 41.4760, lng: 2.0723, query: "Boehringer+Ingelheim+Sant+Cugat" },
  { name: "AstraZeneca", lat: 41.3840812, lng: 2.1505114, query: "AstraZeneca+Barcelona+Spain" },
];

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function projectRing(coords, anchorLat, anchorLng) {
  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const ring = [];
  for (const [lon, lat] of coords) {
    const x = (lon - anchorLng) * 111320 * cosLat;
    const y = (lat - anchorLat) * 111320;
    ring.push({ x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 });
  }
  // Trim repeated last point
  if (ring.length > 1) {
    const a = ring[0], b = ring[ring.length - 1];
    if (Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5) ring.pop();
  }
  return ring;
}

// Seeded PRNG from competitor name — stable across runs.
function seedHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function proceduralFootprint(name) {
  const h = seedHash(name);
  const variant = h % 4;
  const height = 25 + (h % 40);

  if (variant === 0) {
    // L-shape
    const w = 30 + (h % 20), d = 20 + (h % 15);
    return [{
      ringMeters: [
        { x: 0, y: 0 }, { x: w, y: 0 }, { x: w, y: d * 0.5 },
        { x: w * 0.5, y: d * 0.5 }, { x: w * 0.5, y: d }, { x: 0, y: d },
      ],
      heightM: height,
    }];
  } else if (variant === 1) {
    // T-shape
    const w = 40 + (h % 20), d = 25 + (h % 15);
    return [{
      ringMeters: [
        { x: 0, y: d * 0.6 }, { x: w * 0.3, y: d * 0.6 },
        { x: w * 0.3, y: 0 }, { x: w * 0.7, y: 0 },
        { x: w * 0.7, y: d * 0.6 }, { x: w, y: d * 0.6 },
        { x: w, y: d }, { x: 0, y: d },
      ],
      heightM: height,
    }];
  } else if (variant === 2) {
    // Tower + annex (two buildings)
    const tw = 18 + (h % 10), td = 18 + (h % 10);
    const aw = 35 + (h % 15), ad = 15 + (h % 10);
    return [
      { ringMeters: [{ x: 0, y: 0 }, { x: tw, y: 0 }, { x: tw, y: td }, { x: 0, y: td }], heightM: height + 20 },
      { ringMeters: [{ x: tw + 5, y: 0 }, { x: tw + 5 + aw, y: 0 }, { x: tw + 5 + aw, y: ad }, { x: tw + 5, y: ad }], heightM: height * 0.6 },
    ];
  } else {
    // U-shape
    const w = 45 + (h % 20), d = 30 + (h % 15);
    const wing = w * 0.25;
    return [{
      ringMeters: [
        { x: 0, y: 0 }, { x: wing, y: 0 }, { x: wing, y: d * 0.6 },
        { x: w - wing, y: d * 0.6 }, { x: w - wing, y: 0 }, { x: w, y: 0 },
        { x: w, y: d }, { x: 0, y: d },
      ],
      heightM: height,
    }];
  }
}

async function fetchNominatim(comp) {
  const url = `https://nominatim.openstreetmap.org/search?q=${comp.query}&format=json&polygon_geojson=1&limit=1`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Disease360/1.0 (footprint-prebake)" },
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (!data.length || !data[0].geojson) return null;

  const geo = data[0].geojson;
  if (geo.type !== "Polygon" || !geo.coordinates || !geo.coordinates[0]) return null;

  const ring = projectRing(geo.coordinates[0], comp.lat, comp.lng);
  if (ring.length < 3) return null;

  // Estimate height from area (larger campus = taller main building heuristic)
  const area = Math.abs(ring.reduce((sum, p, i) => {
    const j = (i + 1) % ring.length;
    return sum + (ring[j].x + p.x) * (ring[j].y - p.y);
  }, 0) / 2);
  const heightM = Math.max(20, Math.min(60, 15 + Math.sqrt(area) * 0.3));

  return [{ ringMeters: ring, heightM: Math.round(heightM) }];
}

async function main() {
  const result = {};
  let nominatimHits = 0;

  for (const comp of COMPETITORS) {
    process.stdout.write(`${comp.name}... `);
    const footprints = await fetchNominatim(comp);
    if (footprints) {
      result[comp.name] = footprints;
      nominatimHits++;
      console.log(`OK (${footprints[0].ringMeters.length} pts)`);
    } else {
      result[comp.name] = proceduralFootprint(comp.name);
      console.log(`fallback (procedural)`);
    }
    await sleep(1100);
  }

  writeFileSync(OUT_PATH, JSON.stringify(result, null, 2));
  console.log(`\nDone: ${nominatimHits}/${COMPETITORS.length} from Nominatim, rest procedural.`);
  console.log(`Written to ${OUT_PATH}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
