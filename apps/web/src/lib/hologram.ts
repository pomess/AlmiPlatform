// Cyan wireframe building hologram rendered as a MapLibre custom 3D layer.
// Footprints are pre-baked from Nominatim (see scripts/fetch-footprints.mjs);
// missing data uses procedural fallback shapes. The layer stays attached for
// the life of the map; show()/hide() swap geometry in place to avoid GL
// context churn.
import maplibregl from "maplibre-gl";
import * as THREE from "three";
import type { Competitor } from "./pharma";
import footprintData from "../data/footprints.json";

const LAYER_ID = "competitor-hologram";
const HOLOGRAM_COLOR = 0x7be3ff;

type Footprint = {
  ringMeters: { x: number; y: number }[];
  heightM: number;
};

// Pre-populate the cache from the static JSON at module load.
const footprintCache = new Map<string, Footprint[]>();
for (const [name, fps] of Object.entries(footprintData)) {
  footprintCache.set(name, fps as Footprint[]);
}

export type HologramController = {
  show(c: Competitor): void;
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

  function paintFootprints(list: Footprint[]) {
    clearGroup(root);
    for (const fp of list) {
      const meshes = buildBuildingMeshes(fp);
      meshes.forEach((mesh) => root.add(mesh));
    }
    map.triggerRepaint();
  }

  function show(c: Competitor) {
    anchor = { lng: c.lng, lat: c.lat };
    startMs = performance.now();
    ensureLayer();
    visible = true;

    const footprints = footprintCache.get(c.name);
    if (footprints && footprints.length) {
      paintFootprints(footprints);
    } else {
      paintFootprints([fallbackFootprint()]);
    }
  }

  function hide() {
    visible = false;
    clearGroup(root);
    anchor = null;
    map.triggerRepaint();
  }

  function dispose() {
    visible = false;
    clearGroup(root);
    if (map.getLayer(LAYER_ID)) {
      map.removeLayer(LAYER_ID);
    }
    renderer?.dispose();
    renderer = null;
  }

  ensureLayer();

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
        float fres = pow(1.0 - max(dot(normalize(vNormal), normalize(vViewDir)), 0.0), 2.2);

        float hN = clamp(vLocal.z / max(uHeight, 1.0), 0.0, 1.0);
        float vGrad = mix(0.18, 0.55, hN);

        float t = mod(uTime * 0.18, 1.0);
        float scanY = t * uHeight;
        float band = exp(-pow((vLocal.z - scanY) / max(uHeight * 0.035, 1.2), 2.0));

        float stripes = 0.5 + 0.5 * sin(vLocal.z * 1.6 - uTime * 1.2);
        stripes = pow(stripes, 6.0) * 0.18;

        float streak = hash(vec2(floor(vLocal.x * 0.6 + vLocal.y * 0.6), 0.0));
        float streakLine = step(0.985, streak) * (0.4 + 0.6 * sin(uTime * 4.0 + streak * 30.0));

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

  const edges = new THREE.EdgesGeometry(geom, 1);
  const lineMaterial = new THREE.LineBasicMaterial({
    color: HOLOGRAM_COLOR,
    transparent: true,
    opacity: 1.0,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const wire = new THREE.LineSegments(edges, lineMaterial);

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

function fallbackFootprint(): Footprint {
  return {
    ringMeters: [
      { x: -30, y: -20 },
      { x: 30, y: -20 },
      { x: 30, y: 20 },
      { x: -30, y: 20 },
    ],
    heightM: 80,
  };
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
