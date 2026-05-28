/**
 * Fetches real building footprints from the OSM main API for every competitor
 * and saves them as a static JSON backup. Unlike Overpass, the main OSM API
 * is reachable from this machine.
 *
 * Usage:  node apps/web/scripts/fetch-overpass-backup.mjs
 * Output: apps/web/src/data/footprints.json
 */

import { writeFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = resolve(__dirname, "../src/data/footprints.json");

const SEARCH_RADIUS_M = 200;
const BBOX_DEG = 0.002; // ~200m in each direction

const COMPETITORS = [
  { name: "Sanofi", lat: 41.4087, lng: 2.2174 },
  { name: "Novartis", lat: 41.3981834, lng: 2.1806575 },
  { name: "LEO Pharma", lat: 41.4710, lng: 2.0879 },
  { name: "AbbVie", lat: 40.4769, lng: -3.6792 },
  { name: "Pfizer", lat: 40.5366, lng: -3.6307 },
  { name: "Eli Lilly", lat: 40.5398, lng: -3.6359 },
  { name: "Johnson & Johnson", lat: 40.4574, lng: -3.6105 },
  { name: "UCB", lat: 40.4419, lng: -3.6809 },
  { name: "Galderma", lat: 40.4360, lng: -3.6784 },
  { name: "Incyte", lat: 40.4279, lng: -3.7032 },
  { name: "Roche", lat: 41.4924849, lng: 2.0582393 },
  { name: "Merck", lat: 40.4361, lng: -3.6755 },
  { name: "GSK", lat: 40.6056, lng: -3.7113 },
  { name: "Bayer", lat: 41.3696066, lng: 2.0777182 },
  { name: "Boehringer Ingelheim", lat: 41.4760, lng: 2.0723 },
  { name: "AstraZeneca", lat: 41.3840812, lng: 2.1505114 },
];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function projectRing(nodeMap, nodeIds, anchorLat, anchorLng) {
  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const ring = [];
  for (const id of nodeIds) {
    const node = nodeMap.get(id);
    if (!node) continue;
    const x = (node.lon - anchorLng) * 111320 * cosLat;
    const y = (node.lat - anchorLat) * 111320;
    ring.push({ x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 });
  }
  if (ring.length > 1) {
    const a = ring[0], b = ring[ring.length - 1];
    if (Math.abs(a.x - b.x) < 0.01 && Math.abs(a.y - b.y) < 0.01) ring.pop();
  }
  return ring;
}

function parseHeight(tags) {
  if (!tags) return 30;
  const h = tags["height"] || tags["building:height"];
  if (h) { const n = parseFloat(h); if (Number.isFinite(n) && n > 0) return n; }
  const levels = tags["building:levels"];
  if (levels) { const n = parseFloat(levels); if (Number.isFinite(n) && n > 0) return n * 3.5; }
  return 30;
}

function pointInRing(ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i].x, yi = ring[i].y;
    const xj = ring[j].x, yj = ring[j].y;
    if ((yi > 0) !== (yj > 0) && 0 < (xj - xi) * (0 - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function ringArea(ring) {
  let area = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    area += (ring[j].x + ring[i].x) * (ring[j].y - ring[i].y);
  }
  return Math.abs(area) / 2;
}

function ringCentroidDist(ring) {
  let cx = 0, cy = 0;
  for (const p of ring) { cx += p.x; cy += p.y; }
  cx /= ring.length; cy /= ring.length;
  return Math.hypot(cx, cy);
}

function pickTargetBuilding(footprints) {
  if (footprints.length <= 1) return footprints;
  // For static baked data, keep all buildings up to a reasonable campus size.
  // Dense urban areas (>15 buildings) get filtered to the nearest cluster.
  if (footprints.length <= 15) return footprints;
  const containing = footprints.filter(fp => pointInRing(fp.ringMeters));
  if (containing.length >= 1) return containing;
  const sorted = [...footprints].sort((a, b) => ringCentroidDist(a.ringMeters) - ringCentroidDist(b.ringMeters));
  return sorted.slice(0, 8);
}

async function fetchBuildings(comp) {
  const bbox = [
    comp.lng - BBOX_DEG,
    comp.lat - BBOX_DEG,
    comp.lng + BBOX_DEG,
    comp.lat + BBOX_DEG,
  ].join(",");

  const url = "https://api.openstreetmap.org/api/0.6/map.json?bbox=" + bbox;
  const res = await fetch(url, {
    headers: { "User-Agent": "Disease360/1.0 (building-backup)" },
  });
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();

  // Build a node lookup for resolving way geometry
  const nodeMap = new Map();
  for (const el of data.elements) {
    if (el.type === "node") nodeMap.set(el.id, el);
  }

  const out = [];
  for (const el of data.elements) {
    if (el.type === "way" && el.tags && el.tags.building && el.nodes && el.nodes.length >= 3) {
      const ring = projectRing(nodeMap, el.nodes, comp.lat, comp.lng);
      if (ring.length >= 3) {
        out.push({ ringMeters: ring, heightM: parseHeight(el.tags) });
      }
    }
  }

  return pickTargetBuilding(out);
}

async function main() {
  const result = {};
  let success = 0;

  for (const comp of COMPETITORS) {
    process.stdout.write(comp.name + "... ");
    try {
      const footprints = await fetchBuildings(comp);
      if (footprints.length) {
        result[comp.name] = footprints;
        success++;
        console.log("OK (" + footprints.length + " building(s))");
      } else {
        console.log("no buildings found");
      }
    } catch (e) {
      console.log("FAILED: " + e.message);
    }
    await sleep(1500); // OSM API rate limit: 1 req/s
  }

  writeFileSync(OUT_PATH, JSON.stringify(result, null, 2));
  console.log("\nDone: " + success + "/" + COMPETITORS.length + " fetched.");
  console.log("Written to " + OUT_PATH);
}

main().catch(e => { console.error(e); process.exit(1); });
