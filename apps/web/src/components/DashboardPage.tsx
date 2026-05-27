import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DashboardActivity } from "./DashboardActivity";
import { DashboardNewsPanel } from "./DashboardNewsPanel";
import { useVoiceTurn } from "../hooks/useVoiceTurn";
import {
  ALMIRALL_HQ,
  COMPETITORS,
  makeAlmirallMarker,
  makeCompetitorMarker,
} from "../lib/pharma";
import { attachHologramLayer, type HologramController } from "../lib/hologram";

const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// Match an arbitrary lat/lng (e.g. one the voice agent passed to
// fly_to_location) against the known competitor list, within ~150 m, so
// "fly to Pfizer" lights up the hologram even though the call came in
// through a generic geocoded coordinate.
const COMPETITOR_MATCH_RADIUS_M = 150;
function findCompetitorAt(lat: number, lng: number) {
  const cosLat = Math.cos((lat * Math.PI) / 180);
  for (const c of COMPETITORS) {
    const dx = (c.lng - lng) * 111320 * cosLat;
    const dy = (c.lat - lat) * 111320;
    if (Math.hypot(dx, dy) <= COMPETITOR_MATCH_RADIUS_M) return c;
  }
  return null;
}

const ROUTE_SOURCE_ID = "disease360-route";
const ROUTE_GLOW_LAYER_ID = "disease360-route-glow";
const ROUTE_LINE_LAYER_ID = "disease360-route-line";

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
        placeholder="ASK DISEASE360"
        rows={1}
        spellCheck={false}
        autoCorrect="off"
        autoCapitalize="off"
        disabled={disabled}
        aria-label="Type a prompt for Disease360"
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

const COMPOSER_SILENT_STORAGE_KEY = "disease360.dashboard.composer.silent";

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
  const hologramRef = useRef<HologramController | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [selectedCompetitor, setSelectedCompetitor] = useState<string | null>(null);
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
      hologramRef.current = attachHologramLayer(map);
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
      hologramRef.current?.dispose();
      hologramRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Re-fly to a competitor regardless of whether it was already selected.
  // Lifting this out of the selectedCompetitor effect lets a re-click on
  // the *currently* selected pin still trigger a fresh fly + hologram,
  // which the previous toggle behavior swallowed.
  const focusCompetitor = useCallback((company: string) => {
    const map = mapRef.current;
    if (!map) return;
    const c = COMPETITORS.find((x) => x.name === company);
    if (!c) return;
    // No map.stop() — MapLibre chains a fresh flyTo cleanly. Stopping
    // mid-flight produced visible camera jerks.
    map.flyTo({
      center: [c.lng, c.lat],
      zoom: 17,
      pitch: 60,
      speed: 0.7,
      curve: 1.4,
      essential: true,
    });
    void hologramRef.current?.show(c);
    setSelectedCompetitor(company);
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    function onClick(e: MouseEvent) {
      const pin = (e.target as HTMLElement).closest(
        ".dashboard-pharma-pin--rival[data-company]",
      ) as HTMLElement | null;
      if (pin) {
        const company = pin.dataset.company || "";
        if (company) focusCompetitor(company);
      } else if (!(e.target as HTMLElement).closest(".dashboard-news-panel")) {
        setSelectedCompetitor(null);
      }
    }
    host.addEventListener("click", onClick);
    return () => host.removeEventListener("click", onClick);
  }, [focusCompetitor]);

  // Hide the hologram whenever the selection is cleared (X button on the
  // news panel, background click, voice "clear", etc.).
  useEffect(() => {
    if (!selectedCompetitor) {
      hologramRef.current?.hide();
    }
  }, [selectedCompetitor]);

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
        // Enforce minimum zoom 15 — the model often passes 11 from stale context.
        const zoom = Number.isFinite(zoomArg) && zoomArg >= 15 ? zoomArg : 16;
        const place = typeof args.place === "string" ? args.place : undefined;
        if (!map || !Number.isFinite(lat) || !Number.isFinite(lng)) {
          return { ok: false, error: "invalid coordinates" };
        }
        const matched = findCompetitorAt(lat, lng);
        map.flyTo({
          center: [lng, lat],
          zoom,
          pitch: matched ? 60 : DASHBOARD_REST_PITCH,
          speed: 0.6,
          curve: 1.4,
          essential: true,
        });
        if (matched) {
          // Mirror the click flow so the news panel + hologram stay in sync.
          setSelectedCompetitor(matched.name);
        } else {
          hologramRef.current?.hide();
        }
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
      <DashboardNewsPanel
        selectedCompetitor={selectedCompetitor}
        onDismissCompetitor={() => setSelectedCompetitor(null)}
      />
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
