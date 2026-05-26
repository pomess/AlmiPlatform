// Read-only MapLibre globe for the landing page. Mirrors the live
// dashboard globe (same style, same projection, same pin set) but with
// every interaction disabled and a slow rotating drift so it reads as a
// product preview, not a controllable map.
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  ALMIRALL_HQ,
  COMPETITORS,
  makeAlmirallMarker,
  makeCompetitorMarker,
} from "../lib/pharma";

const STYLE_URL =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// Camera framing: tilted, looking at Spain from above the Atlantic so
// the user sees the top of the globe with Madrid and Barcelona well in
// frame. Pitch dialed in for the "tilted globe" feel from the brief.
const CAMERA = {
  center: [ALMIRALL_HQ.lng - 2, ALMIRALL_HQ.lat - 1] as [number, number],
  // Tight enough that the planet fills the canvas (no dark square
  // corners) but loose enough that Iberia + the rest of Europe stay in
  // frame at the tilted view.
  zoom: 2.6,
  pitch: 60,
  // North-up when the globe sits at the viewport's vertical centre.
  // The per-frame loop adds scroll-coupled bearing on top of this base.
  bearing: 0,
};

// Scroll-driven bearing. Target bearing is proportional to the globe's
// vertical offset from the viewport's vertical centre, so the planet
// reads as upright (north up, bearing = 0) exactly when it sits in the
// middle of the screen. Scrolling past tilts it the other way; scrolling
// toward it leans it in. Tuning aim: a "graceful sweep" of ~30° across
// a single screen of scroll.
const SCROLL_DEG_PER_PX = 0.04;
const MAX_TARGET_BEARING = 90;
// Time constant (seconds) for the bearing EMA. ~3τ ≈ 0.9 s for a 95%
// transition; tight enough that the globe responds to scroll, loose
// enough that nothing snaps.
const BEARING_TAU_S = 0.3;

export function LandingGlobeMock() {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    let cancelled = false;
    let rafId = 0;
    let lastFrame = 0;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const map = new maplibregl.Map({
      container: hostRef.current,
      style: STYLE_URL,
      center: CAMERA.center,
      zoom: CAMERA.zoom,
      pitch: CAMERA.pitch,
      bearing: CAMERA.bearing,
      // Lock everything: this is a poster, not a map.
      interactive: false,
      attributionControl: false,
    });
    mapRef.current = map;

    // Scroll-coupled bearing. Each frame measures how far the globe's
    // centre is from the viewport's vertical centre and maps that
    // offset to a target bearing — so the globe reads as exactly
    // north-up (bearing = 0) the moment it sits in the middle of the
    // screen. Above the centre line the target is positive (clockwise
    // tilt); below, negative. The rendered bearing chases the target
    // through an EMA so even a fast wheel flick reads as a sweep.
    function computeOffsetFromViewportCenter(): number {
      const host = hostRef.current;
      if (!host) return 0;
      const rect = host.getBoundingClientRect();
      const globeCenterY = rect.top + rect.height / 2;
      const viewportCenterY = window.innerHeight / 2;
      // Positive when the globe is above the centre line (page scrolled
      // past it), negative when it's still below.
      return viewportCenterY - globeCenterY;
    }

    map.on("load", () => {
      if (cancelled) return;
      map.setProjection({ type: "globe" });
      // Belt-and-braces: force a resize once the host's final dimensions
      // are known. Without this, MapLibre sometimes locks in to the
      // host's pre-layout size (e.g. 0×0 or a tiny initial box) and
      // never grows even after the parent flex container settles.
      map.resize();

      // Drop the same pin set the dashboard uses.
      makeAlmirallMarker()
        .setLngLat([ALMIRALL_HQ.lng, ALMIRALL_HQ.lat])
        .addTo(map);
      COMPETITORS.forEach((c) =>
        makeCompetitorMarker(c).setLngLat([c.lng, c.lat]).addTo(map),
      );

      if (reduceMotion) return;

      // Per-frame loop: read the globe's offset from viewport centre,
      // convert to a target bearing, then EMA toward it so transitions
      // are continuous no matter how fast the user scrolls.
      let displayedBearing = map.getBearing();
      const tick = (now: number) => {
        if (cancelled) return;
        if (!lastFrame) lastFrame = now;
        const dt = (now - lastFrame) / 1000;
        lastFrame = now;
        const offset = computeOffsetFromViewportCenter();
        const rawTarget = CAMERA.bearing + offset * SCROLL_DEG_PER_PX;
        const target = Math.max(
          -MAX_TARGET_BEARING,
          Math.min(MAX_TARGET_BEARING, rawTarget),
        );
        const alpha = 1 - Math.exp(-dt / BEARING_TAU_S);
        const delta = ((target - displayedBearing + 540) % 360) - 180;
        displayedBearing = (displayedBearing + delta * alpha + 360) % 360;
        const wrapped =
          displayedBearing > 180 ? displayedBearing - 360 : displayedBearing;
        map.setBearing(wrapped);
        rafId = requestAnimationFrame(tick);
      };
      rafId = requestAnimationFrame(tick);
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

    // Track host resizes so the canvas stays in sync with any layout
    // changes after mount (font load, viewport resize, etc.).
    const resizeObserver = new ResizeObserver(() => {
      if (!cancelled) map.resize();
    });
    if (hostRef.current) resizeObserver.observe(hostRef.current);

    return () => {
      cancelled = true;
      resizeObserver.disconnect();
      if (rafId) cancelAnimationFrame(rafId);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return <div ref={hostRef} className="landing-globe-mock" aria-hidden="true" />;
}
