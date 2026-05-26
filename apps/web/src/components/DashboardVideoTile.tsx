import { useCallback, useEffect, useRef, useState } from "react";
import type { NewsVideo } from "../lib/api";

// Latched state of the global "AI is currently speaking the news intro"
// flag. The DashboardNewsPanel sets this on `window` while the intro
// audio is in flight so the video can hold playback (or stay muted) and
// avoid stomping on the spoken line.
declare global {
  interface Window {
    __kairosNewsIntroSpeaking?: boolean;
    __kairosOnNewsIntroEnd?: (() => void) | null;
  }
}

type Props = { video: NewsVideo };

function buildSrc(videoId: string): string {
  const origin =
    typeof window !== "undefined" ? encodeURIComponent(window.location.origin) : "";
  const params = new URLSearchParams({
    autoplay: "1",
    mute: "1",
    playsinline: "1",
    controls: "0",
    modestbranding: "1",
    rel: "0",
    iv_load_policy: "3",
    disablekb: "1",
    fs: "0",
    enablejsapi: "1",
    vq: "hd1080",
  });
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(
    videoId,
  )}?${params.toString()}${origin ? `&origin=${origin}` : ""}`;
}

const VOLUME_TARGET = 30;
const FADE_STEPS = 6;
const FADE_INTERVAL_MS = 120;

const LS_HIDDEN = "kairos.video.hidden";

export function DashboardVideoTile({ video }: Props) {
  const [started, setStarted] = useState(false);
  const [muted, setMuted] = useState(true);
  const [playing, setPlaying] = useState(true);
  const [hovered, setHovered] = useState(false);
  const [hidden, setHidden] = useState<boolean>(() => {
    try {
      return localStorage.getItem(LS_HIDDEN) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(LS_HIDDEN, hidden ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [hidden]);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const fadeRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const post = (func: string, args: unknown[] = []) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    win.postMessage(
      JSON.stringify({ event: "command", func, args }),
      "https://www.youtube-nocookie.com",
    );
  };

  const clearFade = () => {
    if (fadeRef.current) {
      clearInterval(fadeRef.current);
      fadeRef.current = null;
    }
  };

  const fadeIn = useCallback(() => {
    clearFade();
    post("unMute");
    post("playVideo");
    let step = 0;
    fadeRef.current = setInterval(() => {
      step++;
      const vol = Math.round((step / FADE_STEPS) * VOLUME_TARGET);
      post("setVolume", [vol]);
      if (step >= FADE_STEPS) clearFade();
    }, FADE_INTERVAL_MS);
    setMuted(false);
  }, []);

  const fadeOut = useCallback(() => {
    clearFade();
    let step = FADE_STEPS;
    fadeRef.current = setInterval(() => {
      step--;
      const vol = Math.round((step / FADE_STEPS) * VOLUME_TARGET);
      post("setVolume", [vol]);
      if (step <= 0) {
        clearFade();
        post("mute");
        setMuted(true);
      }
    }, FADE_INTERVAL_MS);
  }, []);

  const handleMouseEnter = () => {
    setHovered(true);
    if (started) fadeIn();
  };

  const handleMouseLeave = () => {
    setHovered(false);
    if (started) fadeOut();
  };

  const handleUnmute = () => {
    clearFade();
    post("unMute");
    post("setVolume", [VOLUME_TARGET]);
    post("playVideo");
    setMuted(false);
  };

  const handleMute = () => {
    clearFade();
    post("mute");
    setMuted(true);
  };

  const handlePlayPause = () => {
    if (playing) {
      post("pauseVideo");
      setPlaying(false);
    } else {
      post("playVideo");
      setPlaying(true);
    }
  };

  useEffect(() => {
    if (started) return;
    if (!window.__kairosNewsIntroSpeaking) {
      setStarted(true);
      return;
    }
    window.__kairosOnNewsIntroEnd = () => {
      setStarted(true);
      window.__kairosOnNewsIntroEnd = null;
    };
    return () => {
      if (window.__kairosOnNewsIntroEnd) {
        window.__kairosOnNewsIntroEnd = null;
      }
    };
  }, [started]);

  useEffect(() => {
    return () => clearFade();
  }, []);

  // Force HD quality once the player is ready.
  useEffect(() => {
    if (!started) return;
    const timer = setTimeout(() => {
      post("setPlaybackQuality", ["hd1080"]);
    }, 2000);
    return () => clearTimeout(timer);
  }, [started]);

  // Full-window-height rail on the right edge — always rendered so the
   // user can hide and re-summon the video without it disappearing.
  const rail = (
    <button
      type="button"
      className={`dashboard-video-rail${hidden ? "" : " dashboard-video-rail--open"}`}
      onClick={() => setHidden((h) => !h)}
      aria-label={hidden ? "Show video panel" : "Hide video panel"}
      title={hidden ? "Show video" : "Hide video"}
    >
      <span>{hidden ? "▶  Show video" : "◀  Hide video"}</span>
    </button>
  );

  if (hidden) {
    return rail;
  }

  return (
    <>
    <aside
      className={`dashboard-video-tile${hovered ? " dashboard-video-tile--focus" : ""}`}
      aria-label="Daily video briefing"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <header className="dashboard-video-header">
        <span className="dashboard-video-eyebrow">▶ VIDEO · {video.source}</span>
        <div className="dashboard-video-controls">
          <button
            type="button"
            className="dashboard-video-mute"
            onClick={handlePlayPause}
            aria-label={playing ? "Pause video" : "Play video"}
            title={playing ? "Pause" : "Play"}
          >
            {playing ? "⏸" : "▶"}
          </button>
          <button
            type="button"
            className="dashboard-video-mute"
            onClick={muted ? handleUnmute : handleMute}
            aria-label={muted ? "Unmute video" : "Mute video"}
            title={muted ? "Unmute" : "Mute"}
          >
            {muted ? "🔇" : "🔊"}
          </button>
        </div>
      </header>
      <div className="dashboard-video-frame">
        {started ? (
          <iframe
            ref={iframeRef}
            src={buildSrc(video.video_id)}
            title={video.title}
            allow="autoplay; encrypted-media; picture-in-picture"
            referrerPolicy="strict-origin-when-cross-origin"
            loading="lazy"
          />
        ) : (
          <img
            className="dashboard-video-placeholder"
            src={video.thumbnail}
            alt={video.title}
            loading="lazy"
          />
        )}
      </div>
      <a
        className="dashboard-video-title"
        href={video.link}
        target="_blank"
        rel="noopener noreferrer"
        title={video.title}
      >
        {video.title}
      </a>
    </aside>
    {rail}
    </>
  );
}

export default DashboardVideoTile;
