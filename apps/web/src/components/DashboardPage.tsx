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

// Almirall global HQ — Ronda General Mitre 151, Barcelona.
const ALMIRALL_HQ: { lat: number; lng: number; name: string; city: string } = {
  lat: 41.4039,
  lng: 2.1374,
  name: "Almirall",
  city: "Barcelona, Spain",
};

// Competitor headquarters on the Bullseye landscape. Where the company
// has a Spanish subsidiary the coords point to its Madrid/Barcelona office;
// otherwise the global HQ. All render as red pins so Almirall (mint) reads
// as the home position at every zoom — country, region, world.
type Competitor = {
  name: string;
  city: string;
  country: string;
  lat: number;
  lng: number;
};

const COMPETITORS: Competitor[] = [
  // ---- Spain ----
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

function makePharmaMarker(
  name: string,
  city: string,
  variant: "home" | "rival",
): maplibregl.Marker {
  const label = `${name.toUpperCase()} · ${city.toUpperCase()}`;
  // Width scales with label length so longer names (Johnson & Johnson) don't
  // get clipped. The SVG viewBox grows in step with the rendered width.
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

function makeCompetitorMarker(c: Competitor): maplibregl.Marker {
  return makePharmaMarker(c.name, c.city, "rival");
}

function makeAlmirallMarker(): maplibregl.Marker {
  return makePharmaMarker(ALMIRALL_HQ.name, "Barcelona", "home");
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
  const homeMarkerRef = useRef<maplibregl.Marker | null>(null);
  const competitorMarkersRef = useRef<maplibregl.Marker[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [silentTextTurns, setSilentTextTurns] = useState<boolean>(() =>
    readComposerSilent(),
  );

  useEffect(() => {
    if (!hostRef.current) return;
    let cancelled = false;

    const map = new maplibregl.Map({
      container: hostRef.current,
      style: STYLE_URL,
      // Boot already framed on Almirall HQ so the entry flyTo is a short
      // slide, not a globe-to-city plunge. Start one zoom step out from
      // the destination so there's still a perceptible move on load.
      center: [ALMIRALL_HQ.lng, ALMIRALL_HQ.lat],
      zoom: 9,
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
      installPharmaPins();
      flyHome();
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

    // Drop Almirall HQ + competitor pins on the globe. The competitor
    // markers stay visible at every zoom so the user can pull out to
    // Spain / Europe / world and still see the field at a glance.
    function installPharmaPins() {
      if (cancelled) return;
      coordsRef.current = { lat: ALMIRALL_HQ.lat, lon: ALMIRALL_HQ.lng };
      homeMarkerRef.current = makeAlmirallMarker()
        .setLngLat([ALMIRALL_HQ.lng, ALMIRALL_HQ.lat])
        .addTo(map);
      competitorMarkersRef.current = COMPETITORS.map((c) =>
        makeCompetitorMarker(c).setLngLat([c.lng, c.lat]).addTo(map),
      );
      setStatus(`${COMPETITORS.length} competitor sites tracked`);
    }

    // Cinematic entry: same flyTo curve the GPS flow used, but anchored on
    // Almirall's Barcelona HQ. The user can zoom out to see the rest of
    // the field afterwards.
    function flyHome() {
      if (cancelled) return;
      map.flyTo({
        center: [ALMIRALL_HQ.lng, ALMIRALL_HQ.lat],
        zoom: 12,
        speed: 0.6,
        curve: 1.4,
        essential: true,
      });
    }

    return () => {
      cancelled = true;
      homeMarkerRef.current?.remove();
      homeMarkerRef.current = null;
      competitorMarkersRef.current.forEach((m) => m.remove());
      competitorMarkersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  function recenter() {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({
      center: [ALMIRALL_HQ.lng, ALMIRALL_HQ.lat],
      zoom: 12,
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

      // Routing (`show_route`) and the companion `clear_map` were removed
      // for the Almirall pivot — pharma competitive intel doesn't need
      // turn-by-turn driving directions on the dashboard map. The helper
      // machinery above (route flyover, ETA chip, smoothed bearings) is
      // left in place but unwired.

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
      <button
        type="button"
        className="dashboard-recenter"
        onClick={recenter}
        aria-label="Recenter on Almirall HQ"
        title="Recenter on Almirall HQ"
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
