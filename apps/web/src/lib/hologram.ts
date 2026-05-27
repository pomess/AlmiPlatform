// Cyan wireframe building hologram rendered as a MapLibre custom 3D layer.
// Footprints come from OpenStreetMap Overpass; missing data falls back to a
// generic 60×40×80 m box so every competitor renders something. The layer
// stays attached for the life of the map; show()/hide() swap geometry in
// place to avoid GL context churn.
import maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Competitor } from "./pharma";
import { COMPETITORS } from "./pharma";

const LAYER_ID = "competitor-hologram";
const HOLOGRAM_COLOR = 0x7be3ff;
const FALLBACK_FOOTPRINT_M = { width: 60, depth: 40, height: 80 };
const SEARCH_RADIUS_M = 200;

type OsmNode = { type: "node"; id: number; lat: number; lon: number };
type OsmWay = {
  type: "way";
  id: number;
  geometry?: { lat: number; lon: number }[];
  tags?: Record<string, string>;
};
type OsmRelation = {
  type: "relation";
  id: number;
  members?: { type: string; role: string; geometry?: { lat: number; lon: number }[] }[];
  tags?: Record<string, string>;
};
type OsmElement = OsmNode | OsmWay | OsmRelation;

type Footprint = {
  ringMeters: { x: number; y: number }[]; // local meters around anchor
  heightM: number;
};

const footprintCache = new Map<string, Footprint[]>();

export type HologramController = {
  show(c: Competitor): Promise<void>;
  hide(): void;
  dispose(): void;
};

export function attachHologramLayer(map: maplibregl.Map): HologramController {
  let renderer: THREE.WebGLRenderer | null = null;
  const scene = new THREE.Scene();
  const camera = new THREE.Camera();
  const root = new THREE.Group();
  scene.add(root);

  let anchor: { lng: number; lat: number } | null = null;
  let visible = false;
  let startMs = performance.now();
  // Tracks the latest show() so an in-flight Overpass response from a
  // previous click doesn't paint over a newer hologram if the user
  // ping-pongs between competitors faster than Overpass replies.
  let showToken = 0;

  const customLayer: maplibregl.CustomLayerInterface = {
    id: LAYER_ID,
    type: "custom",
    renderingMode: "3d",
    onAdd(_m, gl) {
      renderer = new THREE.WebGLRenderer({
        canvas: map.getCanvas(),
        context: gl as WebGL2RenderingContext,
        antialias: true,
      });
      renderer.autoClear = false;
    },
    render(_gl, args) {
      if (!renderer || !visible || !anchor) return;
      const matrix = extractProjectionMatrix(args);
      if (!matrix) return;

      const merc = maplibregl.MercatorCoordinate.fromLngLat(
        [anchor.lng, anchor.lat],
        0,
      );
      const scale = merc.meterInMercatorCoordinateUnits();

      // Geometry is authored in meters with X=east, Y=north, Z=up.
      // The (-scale on Y) flip converts to MapLibre's Mercator (Y grows
      // south). Scale on X and Z stays positive so width and height read
      // correctly.
      const m = new THREE.Matrix4().fromArray(matrix as number[]);
      const l = new THREE.Matrix4()
        .makeTranslation(merc.x, merc.y, merc.z)
        .scale(new THREE.Vector3(scale, -scale, scale));
      camera.projectionMatrix = m.multiply(l);

      const t = (performance.now() - startMs) / 1000;
      // The buildings stay put — orbit comes from the camera bearing
      // (driven from outside via map.setBearing) so the hologram reads
      // as anchored to the ground, not as a spinning model.

      // Drive the scanline shader uniform on every fill material under
      // the cluster.
      root.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.isMesh) {
          const mat = mesh.material as THREE.ShaderMaterial | undefined;
          if (mat && (mat as THREE.ShaderMaterial).uniforms?.uTime) {
            (mat as THREE.ShaderMaterial).uniforms.uTime.value = t;
          }
        }
      });

      renderer.resetState();
      renderer.render(scene, camera);
      map.triggerRepaint();
    },
  };

  function ensureLayer() {
    if (!map.getLayer(LAYER_ID)) {
      map.addLayer(customLayer);
    }
  }

  // Paint the cluster of buildings into the scene root. Extracted so
  // show() can call it twice — once with a fallback box for an instant
  // response, and again with real OSM footprints when the network
  // resolves.
  function paintFootprints(list: Footprint[]) {
    clearGroup(root);
    for (const fp of list) {
      const meshes = buildBuildingMeshes(fp);
      meshes.forEach((mesh) => root.add(mesh));
    }
    map.triggerRepaint();
  }

  async function show(c: Competitor) {
    const myToken = ++showToken;
    anchor = { lng: c.lng, lat: c.lat };
    startMs = performance.now();
    ensureLayer();
    visible = true;

    try {
      const footprints = await loadFootprints(c);
      if (myToken !== showToken) return;
      if (footprints.length) {
        paintFootprints(footprints);
      } else {
        paintFootprints([fallbackFootprint()]);
      }
    } catch {
      // Network/Overpass error — show fallback so something renders.
      if (myToken !== showToken) return;
      paintFootprints([fallbackFootprint()]);
    }
    map.triggerRepaint();
  }

  function hide() {
    showToken++; // invalidate any in-flight show()
    visible = false;
    clearGroup(root);
    anchor = null;
    map.triggerRepaint();
  }

  function dispose() {
    showToken++;
    visible = false;
    clearGroup(root);
    if (map.getLayer(LAYER_ID)) {
      map.removeLayer(LAYER_ID);
    }
    renderer?.dispose();
    renderer = null;
  }

  // Preload all competitor footprints in the background so clicks are instant.
  for (const comp of COMPETITORS) {
    loadFootprints(comp).catch(() => {});
  }

  return { show, hide, dispose };
}

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

function buildBuildingMeshes(fp: Footprint): THREE.Object3D[] {
  const shape = new THREE.Shape();
  const ring = fp.ringMeters;
  shape.moveTo(ring[0].x, ring[0].y);
  for (let i = 1; i < ring.length; i++) {
    shape.lineTo(ring[i].x, ring[i].y);
  }
  shape.closePath();

  const geom = new THREE.ExtrudeGeometry(shape, {
    depth: fp.heightM,
    bevelEnabled: false,
  });
  geom.computeVertexNormals();

  // ── Hologram volume ────────────────────────────────────────────────
  // Translucent body with: vertical gradient, Fresnel rim glow, sweeping
  // scanline, fine horizontal stripes, subtle vertical noise streaks,
  // and a soft top-edge bloom so the silhouette reads as a beam-projected
  // volumetric instead of a flat wireframe box.
  const fillMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color(HOLOGRAM_COLOR) },
      uRim:   { value: new THREE.Color(0xb8f4ff) },
      uHeight: { value: fp.heightM },
    },
    vertexShader: `
      varying vec3 vLocal;
      varying vec3 vNormal;
      varying vec3 vViewDir;
      void main() {
        vLocal = position;
        vNormal = normalize(normalMatrix * normal);
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vViewDir = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      uniform float uTime;
      uniform vec3 uColor;
      uniform vec3 uRim;
      uniform float uHeight;
      varying vec3 vLocal;
      varying vec3 vNormal;
      varying vec3 vViewDir;

      float hash(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
      }

      void main() {
        // Fresnel: hot at grazing angles, cool head-on.
        float fres = pow(1.0 - max(dot(normalize(vNormal), normalize(vViewDir)), 0.0), 2.2);

        // Vertical falloff — brighter at top, softer at base.
        float hN = clamp(vLocal.z / max(uHeight, 1.0), 0.0, 1.0);
        float vGrad = mix(0.18, 0.55, hN);

        // Sweeping scanline (slow).
        float t = mod(uTime * 0.18, 1.0);
        float scanY = t * uHeight;
        float band = exp(-pow((vLocal.z - scanY) / max(uHeight * 0.035, 1.2), 2.0));

        // Fine horizontal interference stripes (CRT-ish).
        float stripes = 0.5 + 0.5 * sin(vLocal.z * 1.6 - uTime * 1.2);
        stripes = pow(stripes, 6.0) * 0.18;

        // Vertical noise streaks (data-rain feel).
        float streak = hash(vec2(floor(vLocal.x * 0.6 + vLocal.y * 0.6), 0.0));
        float streakLine = step(0.985, streak) * (0.4 + 0.6 * sin(uTime * 4.0 + streak * 30.0));

        // Top edge bloom.
        float topGlow = smoothstep(0.85, 1.0, hN) * 0.45;

        float alpha = 0.10 + vGrad * 0.18 + band * 0.65 + fres * 0.55 + topGlow + stripes + streakLine * 0.25;
        vec3 col = mix(uColor, uRim, fres * 0.7 + topGlow * 0.5);
        col += band * 0.6;
        col += streakLine * 0.4;

        gl_FragColor = vec4(col, clamp(alpha, 0.0, 0.95));
      }
    `,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });
  const fill = new THREE.Mesh(geom, fillMaterial);

  // ── Crisp neon wireframe ────────────────────────────────────────────
  const edges = new THREE.EdgesGeometry(geom, 1);
  const lineMaterial = new THREE.LineBasicMaterial({
    color: HOLOGRAM_COLOR,
    transparent: true,
    opacity: 1.0,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const wire = new THREE.LineSegments(edges, lineMaterial);

  // Thicker, dimmer wireframe shell for a "bloom" double-stroke.
  const wireGlow = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({
      color: 0xc6f4ff,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  wireGlow.scale.set(1.015, 1.015, 1.005);

  // ── Outline of footprint on ground (bright) ─────────────────────────
  const baseGeom = new THREE.BufferGeometry().setFromPoints(
    ring.map((p) => new THREE.Vector3(p.x, p.y, 0.5)),
  );
  const base = new THREE.LineLoop(
    baseGeom,
    new THREE.LineBasicMaterial({
      color: HOLOGRAM_COLOR,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );

  return [fill, wireGlow, wire, base];
}

function clearGroup(g: THREE.Group) {
  while (g.children.length) {
    const child = g.children.pop() as THREE.Object3D;
    g.remove(child);
    disposeObject(child);
  }
}

function disposeObject(obj: THREE.Object3D) {
  const anyObj = obj as THREE.Mesh | THREE.LineSegments | THREE.LineLoop;
  const geom = (anyObj as { geometry?: THREE.BufferGeometry }).geometry;
  geom?.dispose();
  const mat = (anyObj as { material?: THREE.Material | THREE.Material[] }).material;
  if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
  else mat?.dispose();
}

// ---------------------------------------------------------------------------
// Overpass fetch + footprint conversion
// ---------------------------------------------------------------------------

async function loadFootprints(c: Competitor): Promise<Footprint[]> {
  const cached = footprintCache.get(c.name);
  if (cached) return cached;

  const query = `[out:json][timeout:10];(way["building"](around:${SEARCH_RADIUS_M},${c.lat},${c.lng});relation["building"](around:${SEARCH_RADIUS_M},${c.lat},${c.lng}););out body geom;`;
  const res = await fetch("https://overpass-api.de/api/interpreter", {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=UTF-8" },
    body: query,
  });
  if (!res.ok) throw new Error(`overpass ${res.status}`);
  const data = (await res.json()) as { elements?: OsmElement[] };
  const elements = data.elements ?? [];

  const out: Footprint[] = [];
  for (const el of elements) {
    if (el.type === "way" && el.geometry && el.geometry.length >= 3) {
      const ring = projectRing(el.geometry, c.lat, c.lng);
      out.push({ ringMeters: ring, heightM: parseHeight(el.tags) });
    } else if (el.type === "relation" && el.members) {
      // For a multipolygon, take the first outer ring with geometry —
      // good enough for hologram silhouette.
      const outer = el.members.find(
        (m) => m.role === "outer" && m.geometry && m.geometry.length >= 3,
      );
      if (outer && outer.geometry) {
        const ring = projectRing(outer.geometry, c.lat, c.lng);
        out.push({ ringMeters: ring, heightM: parseHeight(el.tags) });
      }
    }
  }

  const selected = pickTargetBuilding(out);
  footprintCache.set(c.name, selected);
  return selected;
}

function projectRing(
  geom: { lat: number; lon: number }[],
  anchorLat: number,
  anchorLng: number,
): { x: number; y: number }[] {
  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const ring: { x: number; y: number }[] = [];
  for (const p of geom) {
    const x = (p.lon - anchorLng) * 111320 * cosLat;
    const y = (p.lat - anchorLat) * 111320;
    ring.push({ x, y });
  }
  // OSM ways often repeat the first node as the last; trim it so
  // THREE.Shape doesn't emit a zero-length segment.
  if (ring.length > 1) {
    const a = ring[0];
    const b = ring[ring.length - 1];
    if (Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6) {
      ring.pop();
    }
  }
  return ring;
}

function parseHeight(tags: Record<string, string> | undefined): number {
  if (!tags) return 30;
  const h = tags["height"] ?? tags["building:height"];
  if (h) {
    const n = parseFloat(h);
    if (Number.isFinite(n) && n > 0) return n;
  }
  const levels = tags["building:levels"];
  if (levels) {
    const n = parseFloat(levels);
    if (Number.isFinite(n) && n > 0) return n * 3.5;
  }
  return 30;
}

function fallbackFootprint(): Footprint {
  const w = FALLBACK_FOOTPRINT_M.width / 2;
  const d = FALLBACK_FOOTPRINT_M.depth / 2;
  return {
    ringMeters: [
      { x: -w, y: -d },
      { x: w, y: -d },
      { x: w, y: d },
      { x: -w, y: d },
    ],
    heightM: FALLBACK_FOOTPRINT_M.height,
  };
}

// ---------------------------------------------------------------------------
// Building selection — pick the single target building from Overpass results
// ---------------------------------------------------------------------------

function pointInRing(ring: { x: number; y: number }[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i].x, yi = ring[i].y;
    const xj = ring[j].x, yj = ring[j].y;
    if ((yi > 0) !== (yj > 0) && 0 < (xj - xi) * (0 - yi) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function ringArea(ring: { x: number; y: number }[]): number {
  let area = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    area += (ring[j].x + ring[i].x) * (ring[j].y - ring[i].y);
  }
  return Math.abs(area) / 2;
}

function ringCentroidDist(ring: { x: number; y: number }[]): number {
  let cx = 0, cy = 0;
  for (const p of ring) { cx += p.x; cy += p.y; }
  cx /= ring.length;
  cy /= ring.length;
  return Math.hypot(cx, cy);
}

function pickTargetBuilding(footprints: Footprint[]): Footprint[] {
  if (footprints.length <= 1) return footprints;

  // Campus heuristic: few buildings in the radius means a business park —
  // show them all. Dense urban (many results) means we're in a city block
  // and should isolate the single target building.
  const CAMPUS_THRESHOLD = 6;
  if (footprints.length <= CAMPUS_THRESHOLD) return footprints;

  const containing = footprints.filter((fp) => pointInRing(fp.ringMeters));
  if (containing.length === 1) return containing;
  if (containing.length > 1) {
    containing.sort((a, b) => ringArea(a.ringMeters) - ringArea(b.ringMeters));
    return [containing[0]];
  }

  // None contains the origin — pick the nearest by centroid distance.
  const sorted = [...footprints].sort(
    (a, b) => ringCentroidDist(a.ringMeters) - ringCentroidDist(b.ringMeters),
  );
  return [sorted[0]];
}

// ---------------------------------------------------------------------------
// MapLibre matrix shape compatibility
// ---------------------------------------------------------------------------
// MapLibre v5's custom-layer render callback passes an args object whose
// `defaultProjectionData.mainMatrix` is the MVP matrix; older versions
// passed the matrix directly. Accept either.
function extractProjectionMatrix(args: unknown): ArrayLike<number> | null {
  if (Array.isArray(args)) return args as number[];
  if (args && typeof args === "object") {
    const a = args as {
      defaultProjectionData?: { mainMatrix?: ArrayLike<number> };
      projectionMatrix?: ArrayLike<number>;
    };
    if (a.defaultProjectionData?.mainMatrix) return a.defaultProjectionData.mainMatrix;
    if (a.projectionMatrix) return a.projectionMatrix;
  }
  return null;
}
