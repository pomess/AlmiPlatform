import { useCallback, useEffect, useRef, useState } from "react";

type Voice = {
  name: string;
  character: string;
  d360_candidate: boolean;
};

type VoicesResponse = {
  voices: Voice[];
  default: string;
};

const DEMO_LINES = [
  "Good evening. All systems are online. Shall I bring up the global map, or would you prefer a situation report?",
  "Take me to Tokyo. What would you like to do there, sir?",
  "Recalibrating orbital view. Please stand by.",
];

export function VoicesPage() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [defaultVoice, setDefaultVoice] = useState<string>("Charon");
  const [line, setLine] = useState<string>(DEMO_LINES[0]);
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [onlyD360, setOnlyD360] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cacheRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    fetch("/api/harness/voice/voices")
      .then((r) => r.json())
      .then((data: VoicesResponse) => {
        setVoices(data.voices);
        setDefaultVoice(data.default);
        setSelected(data.default);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const stopPlayback = useCallback(() => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.currentTime = 0;
    }
    setPlaying(null);
  }, []);

  const play = useCallback(
    async (voiceName: string) => {
      if (playing === voiceName) {
        stopPlayback();
        return;
      }
      setError(null);
      stopPlayback();

      const cacheKey = `${voiceName}::${line}`;
      let url = cacheRef.current.get(cacheKey) ?? null;

      if (!url) {
        setLoading(voiceName);
        try {
          const res = await fetch(
            `/api/harness/voice/sample?voice=${encodeURIComponent(voiceName)}&text=${encodeURIComponent(line)}`,
          );
          if (!res.ok) {
            throw new Error(`${res.status} ${res.statusText}`);
          }
          const blob = await res.blob();
          url = URL.createObjectURL(blob);
          cacheRef.current.set(cacheKey, url);
        } catch (e) {
          setLoading(null);
          setError(`Failed to load "${voiceName}": ${e instanceof Error ? e.message : String(e)}`);
          return;
        }
        setLoading(null);
      }

      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying((v) => (v === voiceName ? null : v));
      audio.onerror = () => {
        setPlaying(null);
        setError(`Playback failed for ${voiceName}`);
      };
      setPlaying(voiceName);
      try {
        await audio.play();
      } catch (e) {
        setPlaying(null);
        setError(`Playback blocked: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [line, playing, stopPlayback],
  );

  useEffect(() => {
    // If the demo line changes, invalidate cached URLs so we refetch.
    const cache = cacheRef.current;
    cache.forEach((url) => URL.revokeObjectURL(url));
    cache.clear();
    stopPlayback();
  }, [line, stopPlayback]);

  useEffect(() => {
    return () => {
      cacheRef.current.forEach((url) => URL.revokeObjectURL(url));
      cacheRef.current.clear();
      audioRef.current?.pause();
    };
  }, []);

  const shown = onlyD360 ? voices.filter((v) => v.d360_candidate) : voices;
  const D360 = shown.filter((v) => v.d360_candidate);
  const others = shown.filter((v) => !v.d360_candidate);

  return (
    <div className="voices-page page">
      <div className="voices-head">
        <div>
          <span className="eyebrow">VOICE LIBRARY</span>
          <h2>Pick a voice</h2>
          <p className="muted">
            {voices.length} prebuilt voices available on native-audio + TTS
            models. Default is <b>{defaultVoice}</b>. Tap a card to hear it.
          </p>
        </div>
        <div className="voices-controls">
          <label className="voices-toggle">
            <input
              type="checkbox"
              checked={onlyD360}
              onChange={(e) => setOnlyD360(e.target.checked)}
            />
            D360 voice only
          </label>
        </div>
      </div>

      <div className="voices-script">
        <label className="eyebrow" htmlFor="voice-line">
          DEMO LINE
        </label>
        <div className="voices-script-row">
          <textarea
            id="voice-line"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            rows={2}
          />
          <div className="voices-presets">
            {DEMO_LINES.map((preset, i) => (
              <button
                key={i}
                type="button"
                className={preset === line ? "active" : ""}
                onClick={() => setLine(preset)}
              >
                Preset {i + 1}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="voices-error">{error}</div>}

      {!onlyD360 && D360.length > 0 && (
        <>
          <h3 className="voices-section-title">D360 shortlist</h3>
          <div className="voices-grid">
            {D360.map((v) => (
              <VoiceCard
                key={v.name}
                voice={v}
                isPlaying={playing === v.name}
                isLoading={loading === v.name}
                isSelected={selected === v.name}
                onPlay={() => play(v.name)}
                onSelect={() => setSelected(v.name)}
              />
            ))}
          </div>
          <h3 className="voices-section-title">All voices</h3>
        </>
      )}

      <div className="voices-grid">
        {(onlyD360 ? D360 : others).map((v) => (
          <VoiceCard
            key={v.name}
            voice={v}
            isPlaying={playing === v.name}
            isLoading={loading === v.name}
            isSelected={selected === v.name}
            onPlay={() => play(v.name)}
            onSelect={() => setSelected(v.name)}
          />
        ))}
      </div>

      <div className="voices-footer">
        <div>
          <span className="eyebrow">SELECTED</span>
          <b>{selected ?? "—"}</b>
        </div>
        <div className="muted small">
          To use this voice: set <code>DISEASE360_VOICE_NAME={selected ?? "Charon"}</code>{" "}
          in <code>policies/secrets.env</code> and restart the harness.
        </div>
      </div>
    </div>
  );
}

function VoiceCard({
  voice,
  isPlaying,
  isLoading,
  isSelected,
  onPlay,
  onSelect,
}: {
  voice: Voice;
  isPlaying: boolean;
  isLoading: boolean;
  isSelected: boolean;
  onPlay: () => void;
  onSelect: () => void;
}) {
  return (
    <div
      className={`voice-card${isSelected ? " is-selected" : ""}${isPlaying ? " is-playing" : ""}`}
      onClick={onSelect}
    >
      <div className="voice-card-head">
        <div className="voice-card-name">{voice.name}</div>
        {voice.d360_candidate && <span className="voice-tag">D360 voice</span>}
      </div>
      <div className="voice-card-char">{voice.character}</div>
      <button
        type="button"
        className="voice-card-play"
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
          onPlay();
        }}
        disabled={isLoading}
        aria-label={isPlaying ? "Stop" : "Play"}
      >
        {isLoading ? (
          <span className="voice-spinner" aria-hidden="true" />
        ) : isPlaying ? (
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <rect x="3" y="3" width="4" height="10" fill="currentColor" />
            <rect x="9" y="3" width="4" height="10" fill="currentColor" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M4 3 L13 8 L4 13 Z" fill="currentColor" />
          </svg>
        )}
      </button>
    </div>
  );
}
