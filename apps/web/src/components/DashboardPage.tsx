import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DashboardActivity } from "./DashboardActivity";
import { DashboardNewsPanel } from "./DashboardNewsPanel";
import { useVoiceTurn } from "../hooks/useVoiceTurn";

const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const ROUTE_SOURCE_ID = "kairos-route";
const ROUTE_GLOW_LAYER_ID = "kairos-route-glow";
const ROUTE_LINE_LAYER_ID = "kairos-route-line";

// The dashboard map's resting pitch — used both at construction time and as
// the target the route flyover restores to when finalising, so the camera
// never lands flat-on after a route. Keep these two in sync.
const DASHBOARD_REST_PITCH = 45;

const EMPTY_ROUTE: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

// One-time install of the route source + two-pass line layers (a soft outer
// glow and a crisp inner stroke) on top of whatever basemap MapLibre rendered.
// Idempotent so a hot-reload that keeps the map alive doesn't crash on a
// duplicate source ID.
function installRouteLayer(map: maplibregl.Map): void {
  if (map.getSource(ROUTE_SOURCE_ID)) return;
  map.addSource(ROUTE_SOURCE_ID, { type: "geojson", data: EMPTY_ROUTE });
  map.addLayer({
    id: ROUTE_GLOW_LAYER_ID,
    type: "line",
    source: ROUTE_SOURCE_ID,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#7a9cd9",
      "line-width": 8,
      "line-opacity": 0.25,
      "line-blur": 6,
    },
  });
  map.addLayer({
    id: ROUTE_LINE_LAYER_ID,
    type: "line",
    source: ROUTE_SOURCE_ID,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#a8bfe7",
      "line-width": 2.5,
      "line-opacity": 0.95,
    },
  });
}

type RoutePinKind = "start" | "end";

function makeRouteMarker(kind: RoutePinKind): maplibregl.Marker {
  const el = document.createElement("div");
  el.className = `dashboard-route-pin dashboard-route-pin--${kind}`;
  const label = kind === "start" ? "ORIGIN" : "DEST";
  el.innerHTML = `
    <svg viewBox="0 0 140 56" width="140" height="56" xmlns="http://www.w3.org/2000/svg">
      <circle cx="10" cy="46" r="2.5" class="route-pin-anchor" />
      <circle cx="10" cy="46" r="5.5" class="route-pin-ring" />
      <path d="M 10 46 L 30 28 L 132 28" class="route-pin-line" />
      <path d="M 132 28 L 132 22" class="route-pin-tick" />
      <text x="34" y="23" class="route-pin-label">${label}</text>
    </svg>
  `;
  return new maplibregl.Marker({
    element: el,
    anchor: "bottom-left",
    offset: [-10, 10],
  });
}

// Cumulative-time chip that rides the polyline tip during the flyover and
// settles on the destination once the route is fully drawn. Returns the
// marker plus a `setText(label)` updater so the per-frame loop can mutate
// the inline text without rebuilding the SVG.
interface EtaChip {
  marker: maplibregl.Marker;
  setText: (label: string) => void;
}

function makeEtaChip(initial: string): EtaChip {
  const el = document.createElement("div");
  el.className = "dashboard-eta-chip";
  // Chip sits BELOW its geographic anchor with a thin stem pointing up
  // to the line tip. The route start/end pins extend UP-and-RIGHT from
  // the same anchor (anchor: bottom-left), so by extending the chip
  // DOWN-RIGHT we get unconditional non-overlap: even when the tip
  // coincides with the origin or destination marker, the chip is in
  // a different half-plane vertically.
  el.innerHTML = `
    <svg viewBox="0 0 96 36" width="96" height="36" xmlns="http://www.w3.org/2000/svg">
      <path d="M 8 0 L 8 9" class="eta-chip-stem" />
      <rect x="1" y="9" width="94" height="22" rx="4" ry="4" class="eta-chip-bg" />
      <text x="10" y="24" class="eta-chip-prefix">ETA</text>
      <text x="86" y="24" text-anchor="end" class="eta-chip-value">${initial}</text>
    </svg>
  `;
  const value = el.querySelector(".eta-chip-value") as SVGTextElement | null;
  const marker = new maplibregl.Marker({
    element: el,
    // top-left anchor + (-8, 0) offset puts the SVG's (8, 0) point --
    // the stem head -- exactly on the geographic anchor.
    anchor: "top-left",
    offset: [-8, 0],
  });
  return {
    marker,
    setText: (label: string) => {
      if (value) value.textContent = label;
    },
  };
}

// "ETA-at-this-point" formatter for the LIVE flyover -- shows seconds so
// the ticking value is readable while the line crawls forward.
//   < 60 s  -> "Ns"
//   < 60 min-> "Mm Ss"
//   >= 1 h  -> "Hh Mm"  (drop seconds; minutes carry the precision)
function formatEtaPrecise(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  if (total < 3_600) {
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}m ${s.toString().padStart(2, "0")}s`;
  }
  const h = Math.floor(total / 3_600);
  const m = Math.round((total % 3_600) / 60);
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

// "Settled total ETA" formatter for once the chip lands on DEST -- minutes
// only, per user request ("once it gets to the destination leave only
// the minutes").
//   < 1 min -> "<1 min"
//   < 60 min-> "N min"
//   >= 1 h  -> "Hh" or "Hh Mm"
function formatEtaShort(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "<1 min";
  const total = Math.round(seconds);
  if (total < 60) return "<1 min";
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  return rem === 0 ? `${hours}h` : `${hours}h ${rem}m`;
}

// Walk every coordinate in a GeoJSON geometry and return [[minLng,minLat],
// [maxLng,maxLat]] bounds. ORS returns a Feature with LineString geometry,
// but we accept Multi* shapes too in case ORS ever returns one.
function bboxFromFeature(
  feature: GeoJSON.Feature,
): [[number, number], [number, number]] | null {
  const coords = collectPositions(feature.geometry);
  if (coords.length === 0) return null;
  let minLng = coords[0][0];
  let minLat = coords[0][1];
  let maxLng = minLng;
  let maxLat = minLat;
  for (const [lng, lat] of coords) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

function collectPositions(geom: GeoJSON.Geometry): GeoJSON.Position[] {
  switch (geom.type) {
    case "Point":
      return [geom.coordinates];
    case "MultiPoint":
    case "LineString":
      return geom.coordinates;
    case "MultiLineString":
    case "Polygon":
      return geom.coordinates.flat();
    case "MultiPolygon":
      return geom.coordinates.flat(2);
    case "GeometryCollection":
      return geom.geometries.flatMap(collectPositions);
    default:
      return [];
  }
}

// ---------------------------------------------------------------------------
// Route flyover animation
// ---------------------------------------------------------------------------
// When `show_route` returns we don't dump the whole polyline + zoom out.
// Instead we cinematically extend the line vertex-by-vertex while the camera
// jumps along the head with a tight zoom and a bearing taken from a small
// look-ahead window. After the last frame we ease back to a top-down view of
// the entire route so the user can read the full path. Cancellable so a new
// route call (or `clear_map`) instantly aborts the in-flight animation.

type LngLat = [number, number];

function extractLineCoords(feature: GeoJSON.Feature): LngLat[] {
  const g = feature.geometry;
  if (!g) return [];
  if (g.type === "LineString") return g.coordinates as LngLat[];
  if (g.type === "MultiLineString") {
    return (g.coordinates as LngLat[][]).flat();
  }
  return [];
}

// Chaikin corner-cutting: each iteration replaces every interior vertex with
// two new vertices at 1/4 and 3/4 along its adjacent segments, yielding a
// rounded path. Endpoints are preserved exactly so origin/destination markers
// still line up. Two iterations is the sweet spot — sharp ORS street-corner
// 90° turns become smooth curves the camera can flow through, but the route
// still visibly hugs the road network. More iterations would cut so deep
// the polyline would visibly leave the streets.
function chaikinSmooth(coords: LngLat[], iterations = 2): LngLat[] {
  let out = coords;
  for (let it = 0; it < iterations; it += 1) {
    if (out.length < 3) break;
    const next: LngLat[] = [out[0]];
    for (let i = 0; i < out.length - 1; i += 1) {
      const a = out[i];
      const b = out[i + 1];
      next.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25]);
      next.push([a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
    }
    next.push(out[out.length - 1]);
    out = next;
  }
  return out;
}

// Resample a polyline to roughly uniform `step` metres between samples, so
// indexing by distance becomes plain division and animation velocity stays
// constant under a parametric `t`. Endpoints are always kept; intermediate
// vertices are interpolated linearly inside the segment they fall on.
function resampleUniform(coords: LngLat[], step: number): LngLat[] {
  if (coords.length < 2 || step <= 0) return coords.slice();
  const out: LngLat[] = [coords[0]];
  let need = step; // distance still to walk before planting the next sample
  for (let i = 1; i < coords.length; i += 1) {
    const a = coords[i - 1];
    const b = coords[i];
    let segLen = haversineMeters(a, b);
    if (segLen === 0) continue;
    let consumed = 0;
    while (segLen - consumed >= need) {
      consumed += need;
      const t = consumed / segLen;
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      need = step;
    }
    need -= segLen - consumed;
  }
  const tail = coords[coords.length - 1];
  const last = out[out.length - 1];
  if (last[0] !== tail[0] || last[1] !== tail[1]) out.push(tail);
  return out;
}

// Per-segment bearings for a sample list. Length = samples.length - 1.
function segmentBearings(samples: LngLat[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < samples.length - 1; i += 1) {
    out.push(bearingBetween(samples[i], samples[i + 1]));
  }
  return out;
}

// Circular-aware Gaussian smoothing: rotate each bearing onto the unit
// circle, blur the cos/sin arrays, then atan2 back. Treating bearings as
// scalars and blurring directly would corrupt anything near the 0/360
// wrap (e.g. samples of 358° and 2° would average to 180° instead of 0°).
// `sigma` is in samples — at our 8 m sample step, sigma=6 covers ~96 m,
// which smooths a single street corner without bleeding multi-block
// direction changes.
function smoothBearingsCircular(bearings: number[], sigma: number): number[] {
  const n = bearings.length;
  if (n === 0) return [];
  const cosArr = bearings.map((b) => Math.cos((b * Math.PI) / 180));
  const sinArr = bearings.map((b) => Math.sin((b * Math.PI) / 180));
  const radius = Math.max(1, Math.ceil(sigma * 3));
  const kernel: number[] = [];
  for (let k = -radius; k <= radius; k += 1) {
    kernel.push(Math.exp(-(k * k) / (2 * sigma * sigma)));
  }
  const out = new Array<number>(n);
  for (let i = 0; i < n; i += 1) {
    let cs = 0;
    let ss = 0;
    let wTotal = 0;
    for (let k = -radius; k <= radius; k += 1) {
      const j = i + k;
      if (j < 0 || j >= n) continue;
      const w = kernel[k + radius];
      cs += cosArr[j] * w;
      ss += sinArr[j] * w;
      wTotal += w;
    }
    if (wTotal > 0) {
      cs /= wTotal;
      ss /= wTotal;
    }
    out[i] = ((Math.atan2(ss, cs) * 180) / Math.PI + 360) % 360;
  }
  return out;
}

function haversineMeters(a: LngLat, b: LngLat): number {
  const R = 6_371_000;
  const phi1 = (a[1] * Math.PI) / 180;
  const phi2 = (b[1] * Math.PI) / 180;
  const dPhi = ((b[1] - a[1]) * Math.PI) / 180;
  const dLam = ((b[0] - a[0]) * Math.PI) / 180;
  const h =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLam / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function bearingBetween(a: LngLat, b: LngLat): number {
  const phi1 = (a[1] * Math.PI) / 180;
  const phi2 = (b[1] * Math.PI) / 180;
  const dLam = ((b[0] - a[0]) * Math.PI) / 180;
  const y = Math.sin(dLam) * Math.cos(phi2);
  const x =
    Math.cos(phi1) * Math.sin(phi2) -
    Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLam);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

// Cumulative metres-along-route at each vertex. `out[i]` = total length
// from coords[0] to coords[i]. Used for distance-keyed lookups on
// non-uniform polylines (e.g. raw ORS coords) where the index is not a
// useful proxy for distance.
function cumulativeDistances(coords: LngLat[]): number[] {
  const out = new Array<number>(coords.length);
  out[0] = 0;
  for (let i = 1; i < coords.length; i += 1) {
    out[i] = out[i - 1] + haversineMeters(coords[i - 1], coords[i]);
  }
  return out;
}

// Find the position on a polyline at a given cumulative distance. Returns
// `{ idx, point }` where `idx` is the index of the vertex immediately
// before the target distance (so the caller can slice `coords.slice(0,
// idx + 1)` and append `point` to render the in-progress line). Binary
// search on `cum` keeps this O(log n) per frame even on long routes.
function pointAtDistance(
  coords: LngLat[],
  cum: number[],
  dist: number,
): { idx: number; point: LngLat } {
  if (coords.length === 0) return { idx: 0, point: [0, 0] };
  if (coords.length === 1) return { idx: 0, point: coords[0] };
  const total = cum[cum.length - 1];
  if (dist <= 0) return { idx: 0, point: coords[0] };
  if (dist >= total) {
    return { idx: coords.length - 1, point: coords[coords.length - 1] };
  }
  let lo = 0;
  let hi = coords.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >>> 1;
    if (cum[mid] <= dist) lo = mid;
    else hi = mid;
  }
  const segLen = cum[hi] - cum[lo];
  const t = segLen > 0 ? (dist - cum[lo]) / segLen : 0;
  return {
    idx: lo,
    point: [
      coords[lo][0] + (coords[hi][0] - coords[lo][0]) * t,
      coords[lo][1] + (coords[hi][1] - coords[lo][1]) * t,
    ],
  };
}

// Sinusoidal in/out — peaks at ~1.57× average velocity vs cubic's 3×, so the
// camera's traversal speed stays close to constant through the middle of the
// flight instead of "rushing" the centre and lingering at the edges. Drives
// the per-frame progress through the polyline samples.
function easeInOutSine(t: number): number {
  return 0.5 - 0.5 * Math.cos(Math.PI * t);
}

// Quintic ease-out — fast take-off, very soft landing. Used for the entry
// transition so the camera glides into the close-pitched flight setup with
// near-zero residual velocity, eliminating the snap-into-position feel and
// matching the per-frame loop's near-zero starting velocity.
function easeOutQuint(t: number): number {
  return 1 - (1 - t) ** 5;
}

// Hermite smoothstep: t * t * (3 - 2t). Used to soften linear interpolation
// across each ~8 m sample interval so velocity (and bearing rate-of-change)
// has no derivative discontinuities at sample boundaries — the camera flows
// across crossings instead of nicking them.
function smoothstep(t: number): number {
  return t * t * (3 - 2 * t);
}

// Shortest-arc lerp for compass bearings. Plain linear interpolation breaks
// across the 0/360 wrap (a turn from 350° to 10° would otherwise sweep the
// long way around).
function lerpBearing(prev: number, next: number, alpha: number): number {
  let delta = ((next - prev + 540) % 360) - 180;
  return (prev + delta * alpha + 360) % 360;
}

// Pick a "cinematic" camera profile tuned to the route's length. Short city
// hops fly tight and pitched; longer cross-country routes pull back so the
// camera doesn't have to traverse half a continent at street level.
//
// The profile returns a START / MID / END triple for both zoom and pitch so
// the per-frame loop can interpolate along a bell-shaped sin(pi*t) curve:
// the camera lands close to the origin, eases out to the wider mid-flight
// altitude, and zooms back in for the destination. The endpoint→mid delta
// grows with route length, so a 5 km hop is nearly flat (start ≈ mid ≈ end)
// while a 1,000 km cross-region run does an obvious pull-back through the
// middle that's wide enough to take in the regional context.
function flightCameraForRoute(totalMeters: number): {
  zoomStart: number;
  zoomMid: number;
  zoomEnd: number;
  pitchStart: number;
  pitchMid: number;
  pitchEnd: number;
  durationMs: number;
} {
  const km = totalMeters / 1000;
  // Endpoint zoom = the "close-up" altitude the entry transition lands on
  // and the destination zooms back into. Roughly the previous single-zoom
  // tuning, with the >50 km tier split into 50–300 km and >300 km so a
  // Barcelona→Galicia (~1,100 km) run gets its own band.
  // Mid zoom = the pulled-back cruise altitude. The endpoint→mid delta
  // grows with distance: short hops barely dip (no information gained by
  // pulling back from a tight hop), long routes drop several stops.
  // maxZoom on the map is 18, so the tightest tier (17) keeps 1 stop of
  // headroom even for the start frame of the entry transition.
  let zoomStart: number;
  let zoomMid: number;
  let pitchStart: number;
  let pitchMid: number;
  if (km <= 2) {
    zoomStart = 17;
    zoomMid = 16.5;
    pitchStart = 65;
    pitchMid = 63;
  } else if (km <= 10) {
    zoomStart = 16;
    zoomMid = 14.5;
    pitchStart = 62;
    pitchMid = 58;
  } else if (km <= 50) {
    zoomStart = 14;
    zoomMid = 11.5;
    pitchStart = 60;
    pitchMid = 55;
  } else if (km <= 300) {
    zoomStart = 12;
    zoomMid = 9.5;
    pitchStart = 58;
    pitchMid = 52;
  } else {
    zoomStart = 11;
    zoomMid = 7.5;
    pitchStart = 56;
    pitchMid = 50;
  }
  const zoomEnd = zoomStart;
  const pitchEnd = pitchStart;
  // Duration: keep the previous km×900 (clamped 11–22 s) curve up to 300 km
  // so the live ETA chip ticking and voice cadence the rest of the UX is
  // tuned against don't shift, then add a modest overflow ramp that takes
  // 300 km routes from 22 s up to ~30 s by 800 km, saturated past that.
  // Replaces the old hard 22 s cap so very long routes (Barcelona→Galicia
  // and similar) breathe a bit more without pinning the user in front of
  // a 45 s flyover.
  const baseDurationMs = Math.min(22_000, Math.max(11_000, km * 900));
  let durationMs: number;
  if (km <= 300) {
    durationMs = baseDurationMs;
  } else {
    const overflow = Math.min(km - 300, 500); // saturate at +500 km (= 800 km)
    durationMs = 22_000 + (overflow / 500) * 8_000;
  }
  return {
    zoomStart,
    zoomMid,
    zoomEnd,
    pitchStart,
    pitchMid,
    pitchEnd,
    durationMs,
  };
}

interface FlyoverOptions {
  map: maplibregl.Map;
  source: maplibregl.GeoJSONSource;
  feature: GeoJSON.Feature;
  bbox: [[number, number], [number, number]] | null;
  // Total trip duration in seconds, from the routing service. Used to
  // derive the "time-to-here" telemetry that rides the polyline tip.
  // Optional so the flyover still works for routes without a duration
  // (e.g. straight-line fallbacks).
  totalDurationS?: number;
  onDone?: () => void;
  // Per-frame callback giving the live tip position and the proportional
  // "ETA at this point" derived from the current displayed distance ratio.
  // The DashboardPage uses this to drive the floating ETA chip.
  onTipUpdate?: (lng: number, lat: number, etaSeconds: number) => void;
}

// Sample step for uniform resampling, in metres. 8 m strikes a balance: dense
// enough that linear interpolation between samples is imperceptibly smooth at
// our flight zooms, sparse enough that even a 100 km route only generates ~12k
// samples (a few ms of preprocessing).
const ROUTE_SAMPLE_STEP_M = 8;
// Chaikin corner-cutting iterations applied before resampling. Six rounds
// drive the polyline to glassy-curve territory: even diagonal one-way grids
// lose every visible angle. The route does deviate from the street network
// a little more than at lower iteration counts, but at the flight
// pitch/zoom this is invisible while the smoothness payoff is dramatic.
const ROUTE_CHAIKIN_ITERATIONS = 6;
// Gaussian sigma in samples for the bearings field. With an 8 m sample step,
// σ=60 means each sample's bearing is averaged over a ±180-sample window
// (~1.4 km). This is wide enough that an entire sequence of close turns
// (e.g. a multi-block zigzag through a dense urban grid) smears into a
// single lazy arc the camera glides through as one continuous sweep
// instead of as a series of discrete rotations.
const ROUTE_BEARING_SIGMA = 60;
// How far ahead of the camera (in metres along the route) to read the target
// bearing. The cinematic-camera trick: instead of pointing where we ARE,
// we point where we'll BE in ~450 m. Combined with the EMA below, rotation
// is fully decoupled from corner-arrival -- by the time the camera
// physically reaches a turn, the bearing has already been chasing the
// post-corner heading for several seconds, so the rotation is essentially
// complete. Lookahead = 0 made the camera react to corners; this makes it
// anticipate them well in advance.
const ROUTE_BEARING_LOOKAHEAD_M = 450;
// Entry transition duration. Long enough that a wide-zoom city view eases
// into a tight pitched flight setup without ever feeling like a snap.
const ROUTE_ENTRY_DURATION_MS = 3_000;
// Time constant for the per-frame exponential moving average on the camera
// bearing during flight. ~3τ ≈ 4.5 s for a 95 % bearing transition, so any
// turn -- no matter how fast the camera is racing through the polyline --
// is guaranteed to spread its rotation across ~4-5 s of wall-clock
// animation. Combined with `ROUTE_BEARING_LOOKAHEAD_M`, the rotation
// starts well before the corner and finishes well into the post-corner
// straight, so the camera obviously sweeps through corners rather than
// pivoting on them. Deliberately exaggerated -- this should be visibly
// different from the previous τ=0.85 tuning.
const ROUTE_BEARING_EMA_TAU_S = 1.5;
// Time constant for the per-frame exponential moving average on the camera
// POSITION. The bearing EMA above smooths *rotation*; without this one,
// the camera's centre still snaps along the polyline corners, which
// reads as "abrupt at every turn" no matter how silky the rotation is.
// ~3τ ≈ 1.2 s of wall-clock smoothing on position. Tuned just high
// enough that 90° street corners get visibly rounded into arcs of
// ~10-20 m radius, but low enough that the camera doesn't visibly lag
// behind the polyline tip on long straight stretches.
const ROUTE_POS_EMA_TAU_S = 0.4;

// Returns a cancel function. Calling it stops the animation in place; the
// caller is responsible for whatever cleanup makes sense (we leave the map
// where it is so a new route can take over without a jarring snap).
function startRouteFlyover(opts: FlyoverOptions): () => void {
  const { map, source, feature, bbox, onDone, onTipUpdate, totalDurationS } =
    opts;
  const rawCoords = extractLineCoords(feature);

  // The route polyline shown on the map is the RAW ORS geometry --
  // street-accurate, never moved off the road network. The camera, in
  // contrast, flies along a SEPARATE heavily-smoothed path that's
  // never rendered. This decoupling is the whole point: previously
  // we Chaikin'd the visible line so the camera would have something
  // smooth to follow, but that visibly took the line off the streets
  // AND still left the camera locked to the polyline geometry, which
  // reads as snappy at every corner.
  //
  // Now:
  //   - displayCoords  = rawCoords                       (rendered as-is)
  //   - cameraSamples  = Chaikin x N + uniform resample  (camera-only,
  //                                                       never drawn)
  //   - bearings       = Gaussian-smoothed bearings on cameraSamples
  //   - per frame: position EMA on top of cameraSamples lookup, plus
  //     the existing bearing EMA + lookahead.
  const displayCoords = rawCoords;
  const cameraSamples =
    rawCoords.length >= 2
      ? resampleUniform(
          chaikinSmooth(rawCoords, ROUTE_CHAIKIN_ITERATIONS),
          ROUTE_SAMPLE_STEP_M,
        )
      : rawCoords;
  const renderedFeature: GeoJSON.Feature = {
    type: "Feature",
    properties: feature.properties ?? {},
    geometry: { type: "LineString", coordinates: displayCoords },
  };

  const finalize = (): void => {
    source.setData(renderedFeature);
    if (bbox) {
      const camera = map.cameraForBounds(bbox, {
        padding: { top: 120, right: 120, bottom: 160, left: 120 },
        maxZoom: 12,
      });
      if (camera) {
        map.easeTo({
          center: camera.center,
          zoom: camera.zoom ?? map.getZoom(),
          // Restore the dashboard's resting pitch (not 0 / top-down) so the
          // map keeps the same isometric feel it had before the route.
          pitch: DASHBOARD_REST_PITCH,
          bearing: 0,
          duration: 2_000,
          essential: true,
        });
      }
    }
    onDone?.();
  };

  if (cameraSamples.length < 2 || displayCoords.length < 2) {
    finalize();
    return () => {};
  }

  const bearings = smoothBearingsCircular(
    segmentBearings(cameraSamples),
    ROUTE_BEARING_SIGMA,
  );
  // Two cumulative-distance arrays, one per polyline. Each parametric
  // progress `t` (0..1) maps to its own absolute distance on each
  // polyline so the visible tip and the camera position advance at the
  // same fractional progress, even though the two polylines have
  // different total lengths and different vertex counts.
  const displayCum = cumulativeDistances(displayCoords);
  const cameraCum = cumulativeDistances(cameraSamples);
  const displayTotal = displayCum[displayCum.length - 1] || 0;
  const cameraTotal = cameraCum[cameraCum.length - 1] || 0;
  const {
    zoomStart,
    zoomMid,
    zoomEnd,
    pitchStart,
    pitchMid,
    pitchEnd,
    durationMs,
  } = flightCameraForRoute(cameraTotal);
  // Lookahead in samples. The camera reads its target bearing from this
  // many samples ahead of its current position so it leans into corners
  // before reaching them.
  const lookaheadSamples = Math.max(
    1,
    Math.round(ROUTE_BEARING_LOOKAHEAD_M / ROUTE_SAMPLE_STEP_M),
  );
  // Bias the very first frames so the camera starts already pointed
  // somewhat down-route -- otherwise the lookahead would have it
  // rotating in the very first instant of flight, which negates the
  // entry transition.
  const initialBearing =
    bearings[Math.min(bearings.length - 1, lookaheadSamples)] ?? bearings[0] ?? 0;

  // Empty start state — only the origin point is visible until the camera
  // lands and the per-frame loop begins extending the polyline.
  source.setData({
    type: "Feature",
    properties: {},
    geometry: { type: "LineString", coordinates: [displayCoords[0]] },
  });

  // Entry: easeTo (not flyTo) for direct interpolation of all four camera
  // params. flyTo's parabolic zoom-out-then-zoom-in arc looks great for
  // cross-globe leaps but feels jolty for a city-scale move. easeOutQuint
  // is fast take-off and very soft landing — leaves the camera with near-
  // zero residual velocity exactly as the per-frame loop kicks off (which
  // also starts at near-zero velocity under easeInOutSine), so there is no
  // visible velocity discontinuity at the hand-off.
  //
  // We land at zoomStart/pitchStart (the close-up "endpoint" altitude),
  // not the cruise altitude — the per-frame loop then pulls back along a
  // sin(pi*t) curve toward zoomMid and zooms back into zoomEnd at the
  // destination. Landing at the cruise altitude here would create a
  // visible zoom-out kink at the hand-off, since the loop's first frame
  // already sin(0) = 0 (== zoomStart).
  map.easeTo({
    center: cameraSamples[0],
    zoom: zoomStart,
    pitch: pitchStart,
    bearing: initialBearing,
    duration: ROUTE_ENTRY_DURATION_MS,
    easing: easeOutQuint,
    essential: true,
  });

  let cancelled = false;
  let rafId = 0;
  let safetyTimer = 0;
  let startedAt = 0;
  let lastFrameAt = 0;
  let displayedBearing = initialBearing;
  // Position EMA state. Initialised to the entry-target so the very
  // first frame has zero EMA error to chase -- otherwise the camera
  // would briefly slide from its current location toward the route
  // start as the EMA caught up.
  let displayedCenter: LngLat = [cameraSamples[0][0], cameraSamples[0][1]];
  let started = false;

  const tick = (now: number): void => {
    if (cancelled) return;
    if (!startedAt) {
      startedAt = now;
      lastFrameAt = now;
    }
    const raw = Math.min(1, (now - startedAt) / durationMs);
    const t = easeInOutSine(raw);

    // ----------------------------------------------------------------
    // Visible polyline tip on the RAW street-following coords. Driven
    // by the same `t` as the camera so they stay synchronised.
    // ----------------------------------------------------------------
    const displayDist = t * displayTotal;
    const { idx: tipIdx, point: tipPos } = pointAtDistance(
      displayCoords,
      displayCum,
      displayDist,
    );
    const sliced = displayCoords.slice(0, tipIdx + 1);
    sliced.push(tipPos);
    source.setData({
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: sliced },
    });

    // Telemetry: emit the live tip position and the proportional ETA at
    // that point. We use the visible polyline's distance ratio rather
    // than parametric `t` so the chip's number stays honest with the
    // length of line the user actually sees painted, regardless of any
    // future easing curve added on top of `t`.
    if (onTipUpdate && totalDurationS && displayTotal > 0) {
      const etaSec = (displayDist / displayTotal) * totalDurationS;
      onTipUpdate(tipPos[0], tipPos[1], etaSec);
    }

    // ----------------------------------------------------------------
    // Camera target on the SMOOTH (Chaikin-x6 + uniform-resampled)
    // path. Uniform spacing means we can index by float divisions
    // straight off the cumulative-total ratio, no binary search.
    // ----------------------------------------------------------------
    const cameraIdxFloat = (t * cameraTotal) / ROUTE_SAMPLE_STEP_M;
    const lo = Math.min(cameraSamples.length - 2, Math.floor(cameraIdxFloat));
    const hi = lo + 1;
    // smoothstep across the sub-sample interval removes the C0 derivative
    // discontinuity at sample crossings — without it, position and bearing
    // velocities have a tiny kink every ~8 m of route.
    const frac = smoothstep(cameraIdxFloat - lo);
    const targetCenter: LngLat = [
      cameraSamples[lo][0] + (cameraSamples[hi][0] - cameraSamples[lo][0]) * frac,
      cameraSamples[lo][1] + (cameraSamples[hi][1] - cameraSamples[lo][1]) * frac,
    ];

    // ----------------------------------------------------------------
    // Target bearing from the Gaussian-smoothed bearing field, read
    // `lookaheadSamples` ahead. Camera "anticipates" the corner.
    // ----------------------------------------------------------------
    const bIdx = Math.min(bearings.length - 1, lo + lookaheadSamples);
    const bIdxNext = Math.min(bearings.length - 1, lo + lookaheadSamples + 1);
    const targetBearing = lerpBearing(bearings[bIdx], bearings[bIdxNext], frac);

    // ----------------------------------------------------------------
    // Temporal exponential moving averages on BOTH position and
    // bearing. Per-frame alpha derived from elapsed wall-clock time
    // so the time constant τ holds even when frame intervals are
    // uneven (vsync hiccups, GC pauses):
    //     alpha = 1 - exp(-dt/τ)
    //
    // The position EMA (the new piece) is what actually fixes the
    // "abrupt at corners" feel. Without it, the camera centre snapped
    // along the polyline, so even a perfectly silky bearing rotation
    // happened on top of a jerky position track.
    // ----------------------------------------------------------------
    const dt = Math.max(0, (now - lastFrameAt) / 1000);
    lastFrameAt = now;
    const alphaB = 1 - Math.exp(-dt / ROUTE_BEARING_EMA_TAU_S);
    const alphaP = 1 - Math.exp(-dt / ROUTE_POS_EMA_TAU_S);
    displayedBearing = lerpBearing(displayedBearing, targetBearing, alphaB);
    displayedCenter = [
      displayedCenter[0] + (targetCenter[0] - displayedCenter[0]) * alphaP,
      displayedCenter[1] + (targetCenter[1] - displayedCenter[1]) * alphaP,
    ];

    // ----------------------------------------------------------------
    // Time-varying zoom/pitch along a sin(pi*t) bell curve so the
    // camera lands close at the origin, eases out to the wider mid-
    // flight altitude, and zooms back in at the destination. We
    // interpolate piecewise (start→mid for t ≤ 0.5, mid→end for
    // t > 0.5) using sin(pi*t) as the mix factor, which is 0 at the
    // endpoints, 1 at the midpoint, and has zero derivative at all
    // three -- so there's no velocity discontinuity at the entry
    // hand-off (camera is "vertically still" at t=0), no kink at the
    // mid-flight peak, and no snap into the finalize easeTo at t=1.
    // ----------------------------------------------------------------
    const cinematicMix = Math.sin(Math.PI * t);
    const zoomNow =
      t <= 0.5
        ? zoomStart + (zoomMid - zoomStart) * cinematicMix
        : zoomEnd + (zoomMid - zoomEnd) * cinematicMix;
    const pitchNow =
      t <= 0.5
        ? pitchStart + (pitchMid - pitchStart) * cinematicMix
        : pitchEnd + (pitchMid - pitchEnd) * cinematicMix;

    map.jumpTo({
      center: displayedCenter,
      zoom: zoomNow,
      pitch: pitchNow,
      bearing: displayedBearing,
    });

    if (raw < 1) {
      rafId = requestAnimationFrame(tick);
    } else {
      finalize();
    }
  };

  // Wait for the entry easeTo to settle before kicking off the per-frame
  // loop, otherwise the polyline marches off into empty space while the
  // camera is still mid-flight. `moveend` fires the moment the entry's
  // last easing tick completes; the safety timer is a belt-and-braces
  // fallback if the user grabs the camera mid-entry and cancels it.
  const startTick = (): void => {
    if (started || cancelled) return;
    started = true;
    rafId = requestAnimationFrame(tick);
  };
  map.once("moveend", startTick);
  safetyTimer = window.setTimeout(
    startTick,
    ROUTE_ENTRY_DURATION_MS + 1_000,
  );

  return () => {
    cancelled = true;
    if (rafId) cancelAnimationFrame(rafId);
    if (safetyTimer) window.clearTimeout(safetyTimer);
    map.off("moveend", startTick);
  };
}

// ---------------------------------------------------------------------------
// Bottom-right text composer.
// ---------------------------------------------------------------------------
// A subtle pill-shaped textarea that submits typed prompts through the
// same SSE pipeline as voice. Mainly useful for dev iteration without
// having to hold Space and speak; the visual language matches the mic
// button + recenter glass-pill so it reads as a sibling control.
//
// The composer is purely presentational state -- it owns its own draft
// `value` and forwards completed submissions to `onSubmit`. The dashboard
// passes `voice.submitText(text, { silent })` and a controlled `silent`
// state (persisted to localStorage).
//
// Disabled while a turn is in flight so two prompts can't race; same
// guard the mic button uses.

const COMPOSER_MAX_HEIGHT_PX = 120;

function DashboardComposer({
  onSubmit,
  disabled,
  silent,
  onToggleSilent,
}: {
  onSubmit: (text: string) => void;
  disabled: boolean;
  silent: boolean;
  onToggleSilent: () => void;
}) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow: reset to auto so scrollHeight reflects the natural
  // wrapped content, then clamp up to the cap. Mirrors the Composer
  // pattern in [Chat.tsx]; capped lower here (120px) since this is
  // a slim overlay rather than a full chat surface.
  useEffect(() => {
    const t = taRef.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(COMPOSER_MAX_HEIGHT_PX, t.scrollHeight) + "px";
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
    // Snap height back to single-row immediately so the pill doesn't
    // briefly stay tall after a multi-line submit.
    const t = taRef.current;
    if (t) t.style.height = "auto";
  }

  return (
    <div
      className={`dashboard-composer${disabled ? " is-disabled" : ""}${silent ? " is-silent" : ""}`}
    >
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          } else if (e.key === "Escape") {
            (e.currentTarget as HTMLTextAreaElement).blur();
          }
        }}
        placeholder="ASK KAIROS"
        rows={1}
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
        disabled={disabled}
        aria-label="Type a prompt for Kairos"
      />
      <button
        type="button"
        className="dashboard-composer-speaker"
        onClick={onToggleSilent}
        aria-label={silent ? "Enable assistant voice" : "Mute assistant voice"}
        aria-pressed={!silent}
        title={silent ? "Voice replies muted" : "Voice replies on"}
      >
        {silent ? (
          // Muted speaker (cone + small × on the right).
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path
              d="M4 9v6h3l5 4V5L7 9H4z"
              fill="currentColor"
              fillOpacity="0.55"
            />
            <path
              d="M16 9l5 5M21 9l-5 5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        ) : (
          // Active speaker (cone + concentric arcs).
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M4 9v6h3l5 4V5L7 9H4z" fill="currentColor" />
            <path
              d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
        )}
      </button>
    </div>
  );
}

const COMPOSER_SILENT_STORAGE_KEY = "kairos.dashboard.composer.silent";

function readComposerSilent(): boolean {
  try {
    return window.localStorage.getItem(COMPOSER_SILENT_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function writeComposerSilent(silent: boolean): void {
  try {
    window.localStorage.setItem(
      COMPOSER_SILENT_STORAGE_KEY,
      silent ? "true" : "false",
    );
  } catch {
    /* ignore quota / privacy errors */
  }
}

export function DashboardPage() {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const coordsRef = useRef<{ lat: number; lon: number } | null>(null);
  const startMarkerRef = useRef<maplibregl.Marker | null>(null);
  const endMarkerRef = useRef<maplibregl.Marker | null>(null);
  const etaChipRef = useRef<EtaChip | null>(null);
  const locusMarkerRef = useRef<maplibregl.Marker | null>(null);
  const cancelFlyoverRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [hasFix, setHasFix] = useState(false);
  const [silentTextTurns, setSilentTextTurns] = useState<boolean>(() =>
    readComposerSilent(),
  );

  useEffect(() => {
    if (!hostRef.current) return;
    let cancelled = false;

    const map = new maplibregl.Map({
      container: hostRef.current,
      style: STYLE_URL,
      center: [0, 20],
      zoom: 1.4,
      pitch: DASHBOARD_REST_PITCH,
      minZoom: 0.8,
      // Bumped from 14 so the route flyover can zoom in to street level
      // (~16) without being clamped mid-animation.
      maxZoom: 18,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: false,
    });
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.on("load", () => {
      map.setProjection({ type: "globe" });
      installRouteLayer(map);
      locate();
    });
    map.on("style.load", () => {
      map.setSky?.({
        "sky-color": "#05070b",
        "horizon-color": "#0a0d14",
        "fog-color": "#05070b",
        "sky-horizon-blend": 0.6,
        "horizon-fog-blend": 0.6,
        "fog-ground-blend": 0.2,
        "atmosphere-blend": 0.5,
      });
    });

    function locate() {
      if (!navigator.geolocation) {
        if (!cancelled) setStatus("LOCATION UNAVAILABLE");
        return;
      }
      if (!cancelled) {
        setLocating(true);
        setStatus(null);
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          if (cancelled) return;
          setLocating(false);
          const { latitude, longitude } = pos.coords;
          coordsRef.current = { lat: latitude, lon: longitude };
          setHasFix(true);
          map.flyTo({
            center: [longitude, latitude],
            zoom: 10,
            speed: 0.6,
            curve: 1.4,
            essential: true,
          });
          const latStr = `${Math.abs(latitude).toFixed(3)}°${latitude >= 0 ? "N" : "S"}`;
          const lonStr = `${Math.abs(longitude).toFixed(3)}°${longitude >= 0 ? "E" : "W"}`;
          const el = document.createElement("div");
          el.className = "dashboard-locus";
          el.innerHTML = `
            <svg viewBox="0 0 220 80" width="220" height="80" xmlns="http://www.w3.org/2000/svg">
              <circle cx="16" cy="64" r="2.5" class="locus-anchor" />
              <circle cx="16" cy="64" r="6" class="locus-ring" />
              <path d="M 16 64 L 44 40 L 210 40" class="locus-line" />
              <path d="M 210 40 L 210 34" class="locus-tick" />
              <text x="48" y="35" class="locus-label">${latStr} · ${lonStr}</text>
            </svg>
          `;
          locusMarkerRef.current = new maplibregl.Marker({
            element: el,
            anchor: "bottom-left",
            offset: [-16, 16],
          })
            .setLngLat([longitude, latitude])
            .addTo(map);
          // If a route is already drawn (rare but possible if geolocation
          // resolves after the user kicks off a route), keep the locus
          // hidden so the freshly-added marker doesn't pop in over the
          // ORIGIN pin.
          if (startMarkerRef.current) {
            locusMarkerRef.current
              .getElement()
              .style.setProperty("display", "none");
          }
        },
        () => {
          if (!cancelled) {
            setLocating(false);
            setStatus("LOCATION UNAVAILABLE");
          }
        },
        { timeout: 8000, maximumAge: 5 * 60 * 1000 },
      );
    }

    return () => {
      cancelled = true;
      cancelFlyoverRef.current?.();
      cancelFlyoverRef.current = null;
      locusMarkerRef.current?.remove();
      locusMarkerRef.current = null;
      startMarkerRef.current?.remove();
      startMarkerRef.current = null;
      endMarkerRef.current?.remove();
      endMarkerRef.current = null;
      etaChipRef.current?.marker.remove();
      etaChipRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  function recenter() {
    const map = mapRef.current;
    const coords = coordsRef.current;
    if (!map || !coords) return;
    map.flyTo({
      center: [coords.lon, coords.lat],
      zoom: 10,
      speed: 0.8,
      curve: 1.4,
      essential: true,
    });
  }

  // ------------------------------------------------------------------
  // Voice (turn-based, routed through the chat agent + fly_to_location)
  // ------------------------------------------------------------------

  const [pttHeld, setPttHeld] = useState(false);

  // Hand the voice hook a getter so each turn can ship the freshest GPS
  // fix to the agent (used as the implicit origin for "how do I get to X"
  // routing). Stable identity keeps the hook from re-binding listeners.
  const getUserLocation = useCallback(() => coordsRef.current, []);

  const voice = useVoiceTurn({
    page: "dashboard",
    pttActive: pttHeld,
    getUserLocation,
    onToolCall: (name, args) => {
      const map = mapRef.current;

      if (name === "fly_to_location") {
        const lat = Number(args.lat);
        const lng = Number(args.lng);
        const zoomArg = Number(args.zoom);
        // Default to a tight city framing (~11) when the model omits one so
        // physical-place questions feel close, not continental.
        const zoom = Number.isFinite(zoomArg) && zoomArg > 0 ? zoomArg : 11;
        const place = typeof args.place === "string" ? args.place : undefined;
        if (!map || !Number.isFinite(lat) || !Number.isFinite(lng)) {
          return { ok: false, error: "invalid coordinates" };
        }
        map.flyTo({
          center: [lng, lat],
          zoom,
          speed: 0.6,
          curve: 1.4,
          essential: true,
        });
        return { ok: true, place: place ?? null, lat, lng, zoom };
      }

      if (name === "show_route") {
        if (!map) return { ok: false, error: "map not ready" };
        const source = map.getSource(ROUTE_SOURCE_ID) as
          | maplibregl.GeoJSONSource
          | undefined;
        if (!source) return { ok: false, error: "route layer not initialised" };
        const feature = args.geojson as GeoJSON.Feature | undefined;
        const from = args.from as { lat: number; lng: number } | undefined;
        const to = args.to as { lat: number; lng: number } | undefined;
        if (!feature || !feature.geometry || !from || !to) {
          return { ok: false, error: "invalid route payload" };
        }
        // Abort any prior flyover so a back-to-back route swap doesn't
        // leave two animation loops fighting over the camera.
        cancelFlyoverRef.current?.();
        cancelFlyoverRef.current = null;

        // Hide the "you are here" locus while a route is being narrated.
        // When origin == user's current location (the common case), the two
        // SVG callouts otherwise stack and become unreadable. Restored on
        // `clear_map`.
        locusMarkerRef.current
          ?.getElement()
          .style.setProperty("display", "none");

        startMarkerRef.current?.remove();
        endMarkerRef.current?.remove();
        etaChipRef.current?.marker.remove();
        startMarkerRef.current = makeRouteMarker("start")
          .setLngLat([from.lng, from.lat])
          .addTo(map);
        endMarkerRef.current = makeRouteMarker("end")
          .setLngLat([to.lng, to.lat])
          .addTo(map);

        // Pull the ORS-reported total duration. The bridge call passes a
        // top-level `summary.duration_s`, but ORS also stamps it onto the
        // feature's properties as `summary.duration` (seconds). Prefer
        // the explicit bridge field; fall back to the feature.
        const summaryArg = (args.summary ?? null) as
          | { duration_s?: number; distance_m?: number }
          | null;
        const featSummary =
          ((feature.properties as Record<string, unknown> | null) ?? null)?.[
            "summary"
          ] as { duration?: number } | undefined;
        const totalDurationS =
          (typeof summaryArg?.duration_s === "number"
            ? summaryArg.duration_s
            : undefined) ??
          (typeof featSummary?.duration === "number"
            ? featSummary.duration
            : undefined);

        // Create the floating ETA chip iff we know the total duration.
        // Otherwise we'd be displaying nothing meaningful, so just skip
        // it rather than render an empty chip.
        let chip: EtaChip | null = null;
        if (totalDurationS && totalDurationS > 0) {
          chip = makeEtaChip("0s");
          chip.marker.setLngLat([from.lng, from.lat]).addTo(map);
          etaChipRef.current = chip;
        } else {
          etaChipRef.current = null;
        }

        const bbox = bboxFromFeature(feature);
        cancelFlyoverRef.current = startRouteFlyover({
          map,
          source,
          feature,
          bbox,
          totalDurationS,
          onTipUpdate: chip
            ? (lng, lat, etaSec) => {
                chip!.marker.setLngLat([lng, lat]);
                // Live phase: show seconds so the ticker is readable.
                chip!.setText(formatEtaPrecise(etaSec));
              }
            : undefined,
          onDone: () => {
            cancelFlyoverRef.current = null;
            // Snap the chip to the destination with the full ETA, so the
            // post-flyover state has the total trip time pinned to DEST.
            if (chip && totalDurationS) {
              chip.marker.setLngLat([to.lng, to.lat]);
              chip.setText(formatEtaShort(totalDurationS));
            }
          },
        });
        return { ok: true };
      }

      if (name === "clear_map") {
        if (!map) return { ok: false, error: "map not ready" };
        cancelFlyoverRef.current?.();
        cancelFlyoverRef.current = null;
        const source = map.getSource(ROUTE_SOURCE_ID) as
          | maplibregl.GeoJSONSource
          | undefined;
        source?.setData(EMPTY_ROUTE);
        startMarkerRef.current?.remove();
        startMarkerRef.current = null;
        endMarkerRef.current?.remove();
        endMarkerRef.current = null;
        etaChipRef.current?.marker.remove();
        etaChipRef.current = null;
        // Bring the "you are here" locus callout back now that the route
        // pins are gone.
        locusMarkerRef.current
          ?.getElement()
          .style.removeProperty("display");
        return { ok: true };
      }

      return { ok: false, error: `unknown tool ${name}` };
    },
  });

  // Keep refs so the global key listeners don't need to re-bind on every
  // state change (which would tear down listeners mid-keypress).
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  // Space = push-to-talk. Capture phase so it beats the browser's default
  // "activate focused button" handling of Space.
  useEffect(() => {
    const isTyping = (target: EventTarget | null) => {
      const el = target as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName;
      return (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        el.isContentEditable
      );
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      if (isTyping(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.repeat) return;
      // Only capture if the mic is actually ready -- otherwise releasing
      // would post an empty turn.
      if (!voiceRef.current.micReady) return;
      setPttHeld(true);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== "Space") return;
      if (isTyping(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      setPttHeld(false);
    };
    const onBlur = () => setPttHeld(false);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  const voiceLabel = (() => {
    if (voice.status === "error") return voice.error ?? "Voice error — click to retry";
    if (!voice.micReady) return "Waiting for microphone…";
    if (pttHeld) return "Listening — release Space";
    if (voice.status === "thinking") return "Thinking…";
    if (voice.status === "speaking") return "Assistant speaking";
    return "Hold Space to speak";
  })();

  const pttBarLabel = (() => {
    if (voice.status === "error") return "VOICE OFFLINE — CHECK MIC";
    if (!voice.micReady) return "MIC NOT READY";
    if (pttHeld) return "LISTENING";
    if (voice.status === "thinking") return "THINKING…";
    if (voice.status === "speaking") return "SPEAKING";
    return "HOLD SPACE TO SPEAK";
  })();

  const micButtonClass = (() => {
    if (voice.status === "error") return "is-error";
    if (pttHeld || voice.status === "capturing") return "is-listening";
    if (voice.status === "thinking") return "is-connecting";
    if (voice.status === "speaking") return "is-speaking";
    return voice.micReady ? "is-armed" : "is-idle";
  })();

  return (
    <div
      className={`dashboard-page${pttHeld ? " ptt-active" : ""}`}
      ref={hostRef}
    >
      <div className="dashboard-eyebrow">
        <span className="eyebrow">DASHBOARD · GLOBAL VIEW</span>
        {status && <span className="status">{status}</span>}
      </div>
      <DashboardNewsPanel />
      <div
        className={`dashboard-ptt-bar${pttHeld ? " is-active" : ""}`}
        role="status"
        aria-live="polite"
      >
        <span className="dot" aria-hidden="true" />
        <span className="label">{pttBarLabel}</span>
      </div>
      <DashboardActivity
        status={voice.status}
        pttHeld={pttHeld}
        transcript={voice.transcript}
        reply={voice.reply}
        toolActivity={voice.toolActivity}
        error={voice.error}
      />
      <div
        className={`dashboard-locating${locating ? " is-active" : ""}`}
        role="status"
        aria-live="polite"
        aria-hidden={!locating}
      >
        <span className="dashboard-locating-dot" aria-hidden="true" />
        <span className="dashboard-locating-label">Locating</span>
      </div>
      <button
        type="button"
        className="dashboard-recenter"
        onClick={recenter}
        disabled={!hasFix}
        aria-label="Recenter to my location"
        title="Recenter to my location"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path
            d="M12 3 L19 20 L12 16.5 L5 20 Z"
            fill="currentColor"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <button
        type="button"
        className={`dashboard-mic ${micButtonClass}`}
        onClick={() => {
          if (voice.status === "thinking" || voice.status === "speaking") {
            voice.cancel();
          }
        }}
        aria-label={voiceLabel}
        aria-pressed={pttHeld}
        title={voiceLabel}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"
            fill="currentColor"
          />
          <path
            d="M5 11a7 7 0 0 0 14 0M12 18v3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <DashboardComposer
        onSubmit={(text) => {
          void voice.submitText(text, { silent: silentTextTurns });
        }}
        disabled={
          voice.status === "thinking" ||
          voice.status === "capturing" ||
          pttHeld
        }
        silent={silentTextTurns}
        onToggleSilent={() => {
          setSilentTextTurns((prev) => {
            const next = !prev;
            writeComposerSilent(next);
            return next;
          });
        }}
      />
    </div>
  );
}
