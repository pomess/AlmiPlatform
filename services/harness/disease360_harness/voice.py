"""Voice endpoints for the dashboard.

This module owns three things:

1. The voice picker / sample endpoints (`/voice/voices`, `/voice/sample`)
   that the Voices page uses to audition prebuilt voices.

2. A turn-based voice pipeline (`POST /voice/turn`) that wraps the same
   chat agent the typed `/chat/stream` uses, with audio in / audio out:

       audio (WAV) -> Gemini Flash STT -> agent.astream -> per-sentence TTS

   The agent streams the same `tool` / `tool_done` / `token` events it
   does for typed chat. We additionally emit:

       transcript -- the user's transcribed text
       tool_call  -- a request for the browser to execute a page-scoped
                     tool (e.g. `fly_to_location`)
       audio      -- base64-encoded raw 16-bit mono PCM @ 24 kHz chunks

   Page-scoped tools are stitched in via `client_tools.ClientToolBridge`:
   the tool body publishes a `tool_call` SSE event, awaits a Future, and
   `POST /voice/turn/{turn_id}/tool_result` resolves it with the browser's
   answer.

3. Verbal cues. When the agent starts a known long-running tool (search,
   page read, fly_to_location) we synthesize and play a short canned line
   so the user gets immediate feedback while the tool runs.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import logging
import math
import re
import struct
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response, StreamingResponse
from google import genai
from google.genai import types
from disease360_runtime.config import get as config_get
from disease360_runtime.config import require as config_require
from pydantic import BaseModel

from .client_tools import (
    ClientToolBridge,
    get_turn_bridge,
    register_turn,
    reset_active_bridge,
    set_active_bridge,
    unregister_turn,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Voice catalog (sourced from Google's AI Studio voice picker).
# ---------------------------------------------------------------------------

VOICES: list[dict[str, str]] = [
    {"name": "Zephyr", "character": "Bright"},
    {"name": "Puck", "character": "Upbeat"},
    {"name": "Charon", "character": "Informative"},
    {"name": "Kore", "character": "Firm"},
    {"name": "Fenrir", "character": "Excitable"},
    {"name": "Leda", "character": "Youthful"},
    {"name": "Orus", "character": "Firm"},
    {"name": "Aoede", "character": "Breezy"},
    {"name": "Callirrhoe", "character": "Easy-going"},
    {"name": "Autonoe", "character": "Bright"},
    {"name": "Enceladus", "character": "Breathy"},
    {"name": "Iapetus", "character": "Clear"},
    {"name": "Umbriel", "character": "Easy-going"},
    {"name": "Algieba", "character": "Smooth"},
    {"name": "Despina", "character": "Smooth"},
    {"name": "Erinome", "character": "Clear"},
    {"name": "Algenib", "character": "Gravelly"},
    {"name": "Rasalgethi", "character": "Informative"},
    {"name": "Laomedeia", "character": "Upbeat"},
    {"name": "Achernar", "character": "Soft"},
    {"name": "Alnilam", "character": "Firm"},
    {"name": "Schedar", "character": "Even"},
    {"name": "Gacrux", "character": "Mature"},
    {"name": "Pulcherrima", "character": "Forward"},
    {"name": "Achird", "character": "Friendly"},
    {"name": "Zubenelgenubi", "character": "Casual"},
    {"name": "Vindemiatrix", "character": "Gentle"},
    {"name": "Sadachbia", "character": "Lively"},
    {"name": "Sadaltager", "character": "Knowledgeable"},
    {"name": "Sulafat", "character": "Warm"},
]
VOICE_NAMES = {v["name"] for v in VOICES}

# Voices most likely to feel JARVIS-esque: mature, smooth, informative,
# gravelly, even -- British/warm male-coded timbres in practice.
JARVIS_SHORTLIST = {
    "Charon",
    "Rasalgethi",
    "Algenib",
    "Gacrux",
    "Algieba",
    "Iapetus",
    "Alnilam",
    "Schedar",
    "Orus",
}


# ---------------------------------------------------------------------------
# JARVIS delivery persona.
#
# Layered on top of the normal Disease360 system prompt (SOUL + USER + brain)
# whenever a turn comes in via /voice/turn. Typed chat keeps the neutral
# Disease360 voice; speaking with him sounds like JARVIS.
# ---------------------------------------------------------------------------

JARVIS_STYLE = (
    "You are currently replying by voice. Adopt this delivery on top of "
    "your normal Disease360 persona:\n"
    "- Calm, even tone. Natural cadence. Not theatrical, not breathless.\n"
    "- Keep replies to one or two short sentences. Clip rather than ramble.\n"
    "- Answer directly. Skip preambles like 'Of course.', 'Right away.', "
    "'Certainly.' -- just give the answer.\n"
    "- Do not address the user as 'sir' or any honorific. First name or "
    "no name at all.\n"
    "- No filler words. No 'as an AI'. No disclaimers. No apologising "
    "for things you didn't do.\n"
    "- Avoid markdown, lists, code fences, and emojis -- this output will be "
    "spoken aloud.\n"
    "\n"
    "TOOL ROUTING\n"
    "- The KNOWLEDGE LANDSCAPE block lists what each of the user's brains "
    "holds, with the page path next to every entity and concept. If the "
    "topic is named there, call `get_page(path, brain=...)` DIRECTLY using "
    "that path -- do NOT call `search_wiki`. Cross-brain search reindexes "
    "every vault and is ~25s; a direct page read is ~1s.\n"
    "- Only call `search_wiki` when the topic is genuinely not named in the "
    "atlas. When you do search, scope it to the most likely brain rather "
    "than running cross-brain.\n"
    "\n"
    "VERBAL CONNECTORS\n"
    "- Before calling `search_wiki` or `get_page`, speak ONE short, "
    "specific sentence naming what you are checking, like 'Let me pull up "
    "your Almirall page.' or 'Checking your Deloitte notes.' Then call the "
    "tool. The user hears that sentence aloud while the lookup runs, so "
    "they are never sitting in silence.\n"
    "- Make it specific: name the brain, project, person, or page. Never "
    "use empty filler like 'Looking.' or 'One moment.' on its own."
)


# ---------------------------------------------------------------------------
# Models / config helpers.
# ---------------------------------------------------------------------------

PLAYBACK_RATE = 24_000  # Gemini TTS native rate


def _tts_model() -> str:
    """Text-to-speech model. Defaults to the Gemini 3.1 preview which
    supports the same prebuilt voice catalog as 2.5."""
    return config_get("DISEASE360_VOICE_TTS_MODEL") or "gemini-3.1-flash-tts-preview"


def _voice_name() -> str:
    name = config_get("DISEASE360_VOICE_NAME") or "Algieba"
    return name if name in VOICE_NAMES else "Algieba"


# ---------------------------------------------------------------------------
# Language pinning for Gemini TTS prosody / accent.
#
# The Gemini-TTS preview catalog (per the Cloud TTS docs) lists several
# Spanish variants -- es-ES (Spain, GA), es-419 (Latin America, Preview),
# es-MX (Mexico, Preview) -- plus Catalan as ca-ES (Spain, Preview). With
# no `language_code` set on `SpeechConfig`, the model auto-detects the
# language and tends to pick a Latin American accent for Spanish text,
# which is wrong for the user (Bruno is in Catalonia).
#
# Detection: Catalan input -> ca-ES, Spanish input -> es-ES, English input
# -> en-US. When the text has no clear signal we fall back to en-US so the
# default voice for warm cues ("Got it.", "Checking.") and the first-boot
# greeting stays in English.
#
# Two override knobs:
#   - DISEASE360_VOICE_LANGUAGE_PIN: hard pin (e.g. "ca-ES"). Bypasses the
#     detector entirely. Useful for demos or A/B-ing accents.
#   - DISEASE360_VOICE_LANGUAGE_DEFAULT: fallback when the detector finds
#     no signal (defaults to en-US).
# ---------------------------------------------------------------------------

_LANGUAGE_DEFAULT_FALLBACK = "en-US"


def _voice_language_pin() -> str | None:
    raw = (config_get("DISEASE360_VOICE_LANGUAGE_PIN") or "").strip()
    return raw or None


def _voice_language_default() -> str:
    raw = (config_get("DISEASE360_VOICE_LANGUAGE_DEFAULT") or "").strip()
    return raw or _LANGUAGE_DEFAULT_FALLBACK


# Catalan-only character signals. `ç` does not occur in modern Castilian
# Spanish. The middle-dot `·` appears in the Catalan geminate digraph
# `l·l` and almost nowhere else in Spanish/English text.
_CA_HARD_CHARS = ("ç", "·")

# Catalan distinctive tokens. Each entry is whitespace-padded so we match
# at word boundaries (the input is also whitespace-padded before the
# scan). Curated to be ABSENT in Spanish or English of normal text:
#   - distinct accent direction (`està` grave vs Spanish `está` acute,
#     `també` vs Spanish `también`, `què` vs Spanish `qué`)
#   - distinct lexicon (`amb`/`con`, `però`/`pero`, `tinc`/`tengo`,
#     `vaig`/`voy`, `ets`/`eres`, `vull`/`quiero`, `puc`/`puedo`,
#     `pots`/`puedes`, `molt`/`mucho`, `també`/`también`, `avui`/`hoy`,
#     `demà`/`mañana`, `aquesta`/`esta`, `aquest`/`este`)
#   - distinct toponym morphology (`edifici`/`edificio`, `carrer`/`calle`,
#     `avinguda`/`avenida`)
#   - apostrophe contractions (`l'`, `d'`, `des d'`) which Spanish does
#     not produce
_CA_WORDS = (
    " amb ", " però ", " perquè ", " tinc ", " vaig ", " ets ",
    " uns ", " una mica ", " des d'", " l'", " d'", " què ",
    " és ", " són ", " molt ", " també ", " bé ", " avui ",
    " demà ", " aquesta ", " aquest ", " edifici", " carrer",
    " avinguda", " estic ", " estem ", " estàs ", " està ",
    " vull ", " vols ", " volem ", " puc ", " pots ",
    " gràcies", " benvingut", " benvinguda",
    " minuts en ", " fins a ", " feina ", " noi ", " noia ",
)

# Spanish hard signal: `ñ` is unique to Spanish among the languages we
# handle (Catalan uses `ny` for the same phoneme, English doesn't have
# it). Cheap, high-precision short-circuit.
_ES_HARD_CHARS = ("ñ",)

# Spanish distinctive tokens. As above, mirrors of the Catalan list:
# pick conjugations / lexicon that Catalan doesn't share.
_ES_WORDS = (
    " está ", " están ", " estoy ", " estás ", " estamos ",
    " soy ", " eres ", " tienes ", " puedes ", " puedo ",
    " puedas ", " pueda ", " pueden ", " puedan ",
    " buenos días", " buenas ", " donde ", " dónde ", " porque ",
    " porqué ", " tengo ", " voy ", " quiero ", " quieres ",
    " edificio ", " calle ", " avenida ", " qué tal",
    " cómo estás", " hola ", " adiós ", " mucho ", " entonces ",
    " vamos ", " ahora ", " bueno ", " llámame ", " llamame ",
    " ayer ", " hoy ", " mañana ", " hasta luego",
)

# English distinctive tokens. Skewed toward warm-cue / opener phrases
# the harness pre-renders ("Got it.", "Checking.", ...) so those don't
# get read with a Catalan accent.
_EN_WORDS = (
    " the ", " is ", " are ", " you ", " your ", " hello ", " hi ",
    " ok ", " okay ", " thank ", " thanks ", " sure ", " got it",
    " on it", " one moment", " all set", " checking", " done",
    " listening",
)


def _detect_speech_language(text: str) -> str:
    """Heuristic BCP-47 language code for the TTS prosody/accent.

    High-precision, low-recall by design: each token in the markers
    above was chosen to be uniquely Catalan / Spanish / English in
    typical conversational text, so any single hit is a strong signal.
    Ties resolve to whichever language has the highest count; if all
    counts are zero, fall back to `_voice_language_default()` (en-US
    out of the box; override with DISEASE360_VOICE_LANGUAGE_DEFAULT).

    Honours `DISEASE360_VOICE_LANGUAGE_PIN` -- when set, every TTS call
    uses that locale regardless of text content.
    """
    pin = _voice_language_pin()
    if pin:
        return pin
    if not text:
        return _voice_language_default()
    s = " " + text.lower() + " "
    if any(c in s for c in _CA_HARD_CHARS):
        return "ca-ES"
    if any(c in s for c in _ES_HARD_CHARS):
        return "es-ES"
    ca = sum(1 for w in _CA_WORDS if w in s)
    es = sum(1 for w in _ES_WORDS if w in s)
    en = sum(1 for w in _EN_WORDS if w in s)
    best = max(ca, es, en)
    if best == 0:
        return _voice_language_default()
    if ca == best:
        return "ca-ES"
    if es == best:
        return "es-ES"
    return "en-US"


def _voice_temperature() -> float:
    raw = config_get("DISEASE360_VOICE_TEMPERATURE")
    if not raw:
        return 0.6
    try:
        return max(0.0, min(2.0, float(raw)))
    except ValueError:
        return 0.6


def _stt_model() -> str:
    """Gemini multimodal model used to transcribe the user's mic audio."""
    return config_get("DISEASE360_VOICE_STT_MODEL") or "gemini-2.5-flash"


def _live_stt_model() -> str:
    """Live API model used by `/voice/stream/stt` for streaming STT.

    Defaults to the current public Live preview that supports
    `input_audio_transcription`. Override via `DISEASE360_VOICE_LIVE_STT_MODEL`.

    History: the previous default (`gemini-live-2.5-flash-preview`) was
    retired from the v1beta endpoint -- requests against it returned
    `1008 policy violation: ... is not found for API version v1beta, or
    is not supported for bidiGenerateContent`. Replaced with the current
    Google-recommended Live model (`gemini-3.1-flash-live-preview`),
    which natively supports `input_audio_transcription` per the Live
    API capabilities guide. The streaming-STT WebSocket falls back to
    the multipart `POST /voice/turn` STT path on connect failure, so a
    future rename will degrade quietly to a slower-but-working voice
    turn while we update the default.
    """
    return (
        config_get("DISEASE360_VOICE_LIVE_STT_MODEL")
        or "gemini-3.1-flash-live-preview"
    )


def _streaming_stt_enabled() -> bool:
    """Master switch for the WebSocket STT path. Default ON.

    Set `DISEASE360_VOICE_STREAMING_STT=0` to disable the endpoint and force
    the browser back to the multipart `POST /voice/turn` path.
    """
    raw = (config_get("DISEASE360_VOICE_STREAMING_STT") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _voice_pace() -> str | None:
    """Audio-tag pacing prefix prepended to TTS calls.

    Gemini TTS doesn't expose a numeric speaking-rate knob. Pacing is
    controlled via audio tags in the transcript: `[fast]`, `[very fast]`,
    `[slow]`, etc. The downside is the model treats them as *performance
    direction* and tends to also change vocal character (excited pitch
    rise, theatrical delivery) which breaks the smooth-baritone JARVIS
    feel. Default is therefore None — we keep Algieba's native prosody
    and apply a small mechanical speedup on the client instead. Set
    `DISEASE360_VOICE_PACE=fast` to opt back in if you want model-level
    pacing.
    """
    raw = config_get("DISEASE360_VOICE_PACE")
    if raw is None:
        return None
    s = raw.strip()
    return s or None


# Process-shared Gemini client. The google-genai SDK pools HTTP/2
# connections per `Client` instance, so reusing one client across STT,
# TTS, and sample requests reuses the warm TLS session and shaves
# ~50-150 ms off every per-turn call after the first. Initialised lazily
# so importing this module doesn't blow up when GOOGLE_API_KEY is missing.
_SHARED_CLIENT: genai.Client | None = None
_SHARED_CLIENT_LOCK = threading.Lock()


def _genai_client() -> genai.Client:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        with _SHARED_CLIENT_LOCK:
            if _SHARED_CLIENT is None:
                api_key = config_require("GOOGLE_API_KEY")
                _SHARED_CLIENT = genai.Client(
                    api_key=api_key, http_options={"api_version": "v1beta"}
                )
    return _SHARED_CLIENT


def warm_genai_client() -> None:
    """Force initialisation of the shared client at process startup so the
    very first user turn doesn't pay the import + auth cost on the hot path."""
    try:
        _genai_client()
    except Exception:
        log.warning("warm_genai_client failed (likely missing GOOGLE_API_KEY)", exc_info=True)


# ---------------------------------------------------------------------------
# WAV helpers (kept from the previous Live-based implementation).
# ---------------------------------------------------------------------------

def _wav_from_pcm16(pcm: bytes, sample_rate: int = 24_000) -> bytes:
    """Wrap raw little-endian 16-bit mono PCM in a RIFF/WAVE header."""
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = len(pcm)
    riff_size = 36 + data_size
    header = b"RIFF" + struct.pack("<I", riff_size) + b"WAVE"
    fmt = (
        b"fmt "
        + struct.pack(
            "<IHHIIHH",
            16,
            1,
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
    )
    data = b"data" + struct.pack("<I", data_size) + pcm
    return header + fmt + data


# ---------------------------------------------------------------------------
# Voice picker / sample endpoints.
# ---------------------------------------------------------------------------

DEMO_LINE_DEFAULT = (
    "Good evening. All systems are online. "
    "Shall I bring up the global map, or would you prefer a situation report?"
)
# WAV blobs keyed by (voice, demo_line). Used by /voice/sample so the
# Voices page doesn't re-synth the same demo every audition.
_SAMPLE_CACHE: dict[tuple[str, str], bytes] = {}

# Raw 24 kHz PCM keyed by (voice, pace, language_code, text). Shared by
# `_tts_pcm_sync` (so /voice/sample, the turn pipeline, and verbal cues
# all hit the same cache) so a hot phrase only ever round-trips Gemini
# TTS once per process. The language_code dimension prevents a Catalan
# pronunciation of "Got it." from being served when the same phrase is
# later requested in English (or vice versa). Sized for short canned
# lines; turn-time sentences are also inserted but won't repeat in
# practice. Keep the entries short.
_PCM_CACHE: dict[tuple[str, str | None, str, str], bytes] = {}
_PCM_CACHE_MAX_TEXT = 240  # don't memo long agent sentences

# Common phrases the agent reaches for early in a turn. Pre-rendering at
# startup means the first audio chunk for any of these is essentially
# instant (a dict lookup) instead of a ~600-1200 ms Gemini TTS RTT.
WARM_OPENERS: tuple[str, ...] = (
    "Got it.",
    "Done.",
    "On it.",
    "Checking.",
    "One moment.",
    "Sure.",
    "Okay.",
    "All set.",
)


@router.get("/voice/voices")
def list_voices() -> dict:
    return {
        "voices": [
            {**v, "jarvis_candidate": v["name"] in JARVIS_SHORTLIST}
            for v in VOICES
        ],
        "default": _voice_name(),
    }


def _tts_pcm_sync(text: str, voice: str, pace: str | None = None) -> bytes:
    """Synthesize one line via the TTS preview model. Returns raw 24kHz PCM.

    `pace`, when provided, is wrapped as a Gemini audio tag (e.g. "fast"
    becomes a `[fast]` prefix) so the model generates faster prosody
    natively rather than us time-stretching on the client.

    Hot phrases (tool cues, common openers) are cached in `_PCM_CACHE` so
    they only ever round-trip Gemini once per process; subsequent calls
    return the memoised PCM in microseconds.
    """
    stripped = text.strip()
    if not stripped:
        return b""
    if voice not in VOICE_NAMES:
        voice = _voice_name()

    # Pin the prosody/accent BEFORE the cache lookup so different
    # languages don't share the same cached PCM. Detection runs on the
    # original `text` (not the pace-prefixed `prompt`) so a leading
    # `[fast]` doesn't bias the heuristic.
    language_code = _detect_speech_language(stripped)

    cache_key = (voice, pace, language_code, stripped)
    cached = _PCM_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prompt = f"[{pace}] {text}" if pace else text
    client = _genai_client()
    res = client.models.generate_content(
        model=_tts_model(),
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                # `language_code` biases the model to the target locale's
                # accent/prosody. Without it, Spanish text routinely
                # comes out with a Latin American accent because the
                # default es voice is es-419-coded.
                language_code=language_code,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    ),
                ),
            ),
        ),
    )
    for cand in res.candidates or []:
        parts = getattr(cand.content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                pcm = inline.data
                # Only memo short canned lines; agent sentences are mostly
                # unique so caching them just bloats the dict.
                if len(stripped) <= _PCM_CACHE_MAX_TEXT:
                    _PCM_CACHE[cache_key] = pcm
                return pcm
    return b""


async def warm_cue_cache() -> None:
    """Pre-render TTS for every tool cue + common opener in the active voice.

    Runs as a background task at startup. Each phrase that successfully
    synthesises is inserted into `_PCM_CACHE`, so when the agent emits
    "Got it." or "Listening." mid-turn `TTSPipeline.speak_now` returns
    instantly. Failures are logged but not raised — a missing cache just
    means the phrase pays its normal RTT on first use.
    """
    voice = _voice_name()
    pace = _voice_pace()
    phrases: list[str] = list(WARM_OPENERS)
    for lines in TOOL_CUES.values():
        phrases.extend(lines)
    seen: set[str] = set()
    for phrase in phrases:
        s = phrase.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        if (voice, pace, s) in _PCM_CACHE:
            continue
        try:
            await asyncio.to_thread(_tts_pcm_sync, s, voice, pace)
        except Exception:
            log.warning("warm_cue_cache failed for %r", s, exc_info=True)
    log.info(
        "warm_cue_cache: pre-rendered %d phrases for voice=%s",
        len(seen),
        voice,
    )


@router.get("/voice/sample")
async def voice_sample(voice: str, text: str | None = None) -> Response:
    if voice not in VOICE_NAMES:
        raise HTTPException(404, f"unknown voice: {voice}")
    line = (text or DEMO_LINE_DEFAULT).strip()
    if len(line) > 400:
        line = line[:400]

    cache_key = (voice, line)
    cached = _SAMPLE_CACHE.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="audio/wav")

    try:
        pcm = await asyncio.to_thread(_tts_pcm_sync, line, voice)
    except Exception as e:
        log.exception("TTS sample failed for voice=%s", voice)
        raise HTTPException(502, f"TTS failed: {e}") from e

    if not pcm:
        raise HTTPException(502, "TTS returned no audio")

    wav = _wav_from_pcm16(pcm, sample_rate=PLAYBACK_RATE)
    _SAMPLE_CACHE[cache_key] = wav
    return Response(content=wav, media_type="audio/wav")


# ---------------------------------------------------------------------------
# Verbal tool cues.
#
# When the agent starts a tool that takes more than ~250 ms, we play a
# short pre-rendered line so the user hears feedback immediately. The
# cues round-robin so the same line doesn't repeat back-to-back, and
# their TTS is cached on first use.
# ---------------------------------------------------------------------------

TOOL_CUES: dict[str, list[str]] = {
    # search_wiki / read_page intentionally have no rotor cue -- the
    # JARVIS_STYLE / DASHBOARD_SKILL prompts now instruct the model to
    # speak its own contextual preface ("Let me pull up your Almirall
    # page.") before the tool call. Layering a generic "Checking." on
    # top of that produces awkward double-talk.
    "list_brains": [
        "Listing your brains.",
    ],
    # deep_research has no cue — the model narrates the escalation via
    # SOUL.md instruction, so a cue would produce double-talk.
    # No cue for fly_to_location -- the map physically moves the moment
    # the tool call hits the client, which is feedback enough.
}

# itertools.cycle iterators for round-robin selection.
_CUE_ROTORS: dict[str, Iterable[str]] = {
    name: itertools.cycle(lines) for name, lines in TOOL_CUES.items()
}


def _next_cue(tool_name: str) -> str | None:
    rotor = _CUE_ROTORS.get(tool_name)
    if rotor is None:
        return None
    return next(rotor)


# ---------------------------------------------------------------------------
# /voice/turn -- main turn-based voice pipeline.
# ---------------------------------------------------------------------------


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# Sentence boundary regex: stop at `.`, `!`, `?`, `\n`, optionally followed
# by a closing quote/bracket. Using a regex keeps numeric strings like
# "3.14" together (no whitespace after the dot) most of the time.
_SENTENCE_BREAK = re.compile(r'([.!?\u2026][\'")\]]*[\s\n]|\n+)')

# Soft clause break used only when a "sentence" runs unusually long
# without any terminal punctuation -- comma, semicolon, em-dash. We only
# break on these when the buffer is already past `LONG_CLAUSE_CHARS` so
# normal short sentences still TTS as one unit.
_LONG_CLAUSE_BREAK = re.compile(r'[,;][\s\n]| -- ')


def _split_sentences(buf: str) -> tuple[list[str], str]:
    """Pull complete sentences out of `buf`. Returns (sentences, remainder).

    A "complete sentence" ends with `.`, `!`, `?`, or a newline followed
    by whitespace -- so we don't break mid-decimal or mid-acronym.
    """
    out: list[str] = []
    pos = 0
    for m in _SENTENCE_BREAK.finditer(buf):
        end = m.end()
        sentence = buf[pos:end].strip()
        if sentence:
            out.append(sentence)
        pos = end
    return out, buf[pos:]


def _split_long_clause(buf: str, threshold: int) -> tuple[str, str] | None:
    """Soft break for runaway sentences with no terminal punctuation yet.

    If `buf` is at least `threshold` chars and contains a comma, semicolon
    or em-dash beyond the halfway point, return (clause, remainder) so the
    leading clause can be sent to TTS early. Returns None when no good
    break exists yet -- the caller should keep buffering.
    """
    if len(buf) < threshold:
        return None
    # Search starting halfway in so we don't chop off a tiny pre-comma
    # ("Yes," fragments are too short to be worth TTSing on their own).
    start = max(40, threshold // 2)
    m = _LONG_CLAUSE_BREAK.search(buf, start)
    if not m:
        return None
    end = m.end()
    clause = buf[:end].strip()
    if not clause:
        return None
    return clause, buf[end:]


class TTSPipeline:
    """Streams reply text into per-sentence TTS jobs and pushes audio chunks.

    Latency design (see plans/voice-tts-latency_*.plan.md):

    - Tiny first sentences ("Of course.") are merged with the start of the
      next sentence into a single TTS job so the user never hears the awkward
      acknowledgment-then-pause gap. Once the first chunk is past
      `MIN_QUEUED_CHARS`, every subsequent sentence is submitted on its own.
    - TTS jobs run concurrently (capped by `MAX_PARALLEL_TTS`) -- by the time
      sentence N's PCM is being chunked out, sentence N+1's Gemini call is
      already in flight.
    - A single emitter task awaits the jobs in submission order and pushes
      audio events, so audio plays in the right order even though synthesis
      is parallel.
    - Runaway sentences (>`LONG_CLAUSE_CHARS` with no terminal punctuation
      yet) are broken on the next comma/semicolon so we don't sit waiting
      for the period to arrive.
    """

    AUDIO_CHUNK_BYTES = 16 * 1024  # ~5.3 kB after base64
    MIN_QUEUED_CHARS = 30
    MAX_PARALLEL_TTS = 5
    LONG_CLAUSE_CHARS = 120
    # Aggressive break threshold for the FIRST sentence only. The opener is
    # the single biggest chunk of TTFA we control: if the model produces a
    # long opening sentence, we'd otherwise wait for it to reach a period
    # OR `LONG_CLAUSE_CHARS=120` chars before any audio leaves. Lowering
    # to 50 chars + first comma/dash for sentence #1 cuts ~200-500 ms off
    # the first audio chunk; subsequent sentences keep the conservative
    # threshold so mid-reply prosody isn't choppy.
    FIRST_CLAUSE_CHARS = 50

    def __init__(self, push: Any, voice_name: str) -> None:
        self._push = push
        self._voice = voice_name
        self._pace = _voice_pace()
        self._buf = ""
        self._seq = 0
        self._merge_buf = ""
        self._first_submitted = False
        self._closed = False
        self._jobs: list[asyncio.Task[bytes]] = []
        self._jobs_changed = asyncio.Event()
        self._sem = asyncio.Semaphore(self.MAX_PARALLEL_TTS)
        self._emitter_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API (unchanged signatures)
    # ------------------------------------------------------------------

    def feed_text(self, text: str) -> None:
        if not text:
            return
        self._buf += text
        self._drain_buffer()

    def speak_now(self, text: str) -> None:
        """Bypass the buffer and push a tool cue directly to the SSE stream.

        If the phrase is pre-cached in _PCM_CACHE, its audio is pushed
        immediately without going through the emitter queue — zero latency.
        Otherwise falls back to inserting a synthesis job at the front.
        """
        s = text.strip()
        if not s:
            return
        if self._merge_buf:
            self._submit(self._merge_buf)
            self._merge_buf = ""
            self._first_submitted = True

        cache_key = (self._voice, self._pace, _detect_speech_language(s), s)
        cached_pcm = _PCM_CACHE.get(cache_key)
        if cached_pcm:
            asyncio.create_task(self._push_pcm_direct(cached_pcm))
        else:
            self._ensure_emitter()
            task = asyncio.create_task(self._synthesize(s))
            idx = getattr(self, "_emit_idx", len(self._jobs))
            self._jobs.insert(idx, task)
            self._jobs_changed.set()
        self._first_submitted = True

    async def _push_pcm_direct(self, pcm: bytes) -> None:
        """Push pre-cached PCM audio directly to the client, no queue."""
        for off in range(0, len(pcm), self.AUDIO_CHUNK_BYTES):
            chunk = pcm[off : off + self.AUDIO_CHUNK_BYTES]
            await self._push(
                {
                    "type": "audio",
                    "b64": base64.b64encode(chunk).decode("ascii"),
                    "seq": self._seq,
                    "rate": PLAYBACK_RATE,
                }
            )
            self._seq += 1

    async def flush_remainder(self) -> None:
        # Pull any complete sentences still hiding in the buffer.
        self._drain_buffer()
        # Whatever's left -- tail of the last sentence + merge buffer --
        # gets submitted as one final job, even if below threshold.
        tail = self._buf.strip()
        self._buf = ""
        final = " ".join(p for p in (self._merge_buf, tail) if p).strip()
        self._merge_buf = ""
        if final:
            self._submit(final)
            self._first_submitted = True
        # Signal the emitter that no further jobs will be appended.
        self._closed = True
        self._jobs_changed.set()
        if self._emitter_task is None:
            return
        try:
            await self._emitter_task
        except Exception:
            log.exception("TTS emitter crashed")

    async def cancel(self) -> None:
        self._closed = True
        for job in self._jobs:
            if not job.done():
                job.cancel()
        if self._emitter_task is not None and not self._emitter_task.done():
            self._emitter_task.cancel()
        # Drain everything so we don't leak tasks.
        for job in self._jobs:
            try:
                await job
            except (asyncio.CancelledError, Exception):
                pass
        if self._emitter_task is not None:
            try:
                await self._emitter_task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _drain_buffer(self) -> None:
        """Pull as many complete sentences (or long clauses) out of `_buf`
        as we can right now, and submit them subject to the merge rule."""
        sentences, leftover = _split_sentences(self._buf)
        self._buf = leftover

        # If nothing terminated, see if a runaway clause is ready to break.
        # Use the more-aggressive FIRST_CLAUSE_CHARS threshold while we
        # haven't submitted anything yet -- the first audio chunk is the
        # one the user actually waits for, so we trade some prosody risk
        # for noticeably faster TTFA on long opening sentences.
        if not sentences:
            threshold = (
                self.FIRST_CLAUSE_CHARS
                if not self._first_submitted
                else self.LONG_CLAUSE_CHARS
            )
            split = _split_long_clause(self._buf, threshold)
            if split is not None:
                clause, remainder = split
                sentences = [clause]
                self._buf = remainder

        for s in sentences:
            self._enqueue_sentence(s)

    def _enqueue_sentence(self, sentence: str) -> None:
        s = sentence.strip()
        if not s:
            return
        # Merge tiny opening sentences so "Of course." rides into the next
        # clause as one TTS job. After we've submitted the first job we
        # stop merging entirely -- subsequent sentences race independently.
        if not self._first_submitted:
            merged_len = len(self._merge_buf) + (1 if self._merge_buf else 0) + len(s)
            if merged_len < self.MIN_QUEUED_CHARS:
                self._merge_buf = (self._merge_buf + " " + s).strip() if self._merge_buf else s
                return
            payload = (self._merge_buf + " " + s).strip() if self._merge_buf else s
            self._merge_buf = ""
            self._submit(payload)
            self._first_submitted = True
            return
        self._submit(s)

    def _ensure_emitter(self) -> None:
        if self._emitter_task is None or self._emitter_task.done():
            self._emitter_task = asyncio.create_task(self._emitter())

    def _submit(self, sentence: str) -> None:
        self._ensure_emitter()
        task = asyncio.create_task(self._synthesize(sentence))
        self._jobs.append(task)
        self._jobs_changed.set()

    async def _synthesize(self, sentence: str) -> bytes:
        async with self._sem:
            try:
                return await asyncio.to_thread(
                    _tts_pcm_sync, sentence, self._voice, self._pace,
                )
            except Exception:
                log.exception("TTS synth failed for sentence=%r", sentence[:60])
                return b""

    async def _emitter(self) -> None:
        idx = 0
        while True:
            while idx >= len(self._jobs):
                if self._closed:
                    return
                await self._jobs_changed.wait()
                self._jobs_changed.clear()
            self._emit_idx = idx
            try:
                pcm = await self._jobs[idx]
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("TTS job awaited with error")
                idx += 1
                continue
            idx += 1
            if not pcm:
                continue
            for off in range(0, len(pcm), self.AUDIO_CHUNK_BYTES):
                chunk = pcm[off : off + self.AUDIO_CHUNK_BYTES]
                await self._push(
                    {
                        "type": "audio",
                        "b64": base64.b64encode(chunk).decode("ascii"),
                        "seq": self._seq,
                        "rate": PLAYBACK_RATE,
                    }
                )
                self._seq += 1


# ---------------------------------------------------------------------------
# STT helper.
# ---------------------------------------------------------------------------

_STT_INSTRUCTION = (
    "Transcribe the user's audio verbatim into plain text. "
    "Output only the words the user spoke, with normal punctuation. "
    "Do not add narration, do not summarise, do not translate. "
    "If the audio contains no speech, output an empty string."
)


def _stt_sync(audio_bytes: bytes, mime: str) -> str:
    client = _genai_client()
    model = _stt_model()
    res = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(text=_STT_INSTRUCTION),
                    types.Part(
                        inline_data=types.Blob(
                            data=audio_bytes,
                            mime_type=mime or "audio/wav",
                        )
                    ),
                ],
            )
        ],
    )
    for cand in res.candidates or []:
        parts = getattr(cand.content, "parts", None) or []
        for part in parts:
            t = getattr(part, "text", None)
            if t:
                return t.strip()
    return ""


# ---------------------------------------------------------------------------
# Streaming STT (Gemini Live API) -- WebSocket endpoint.
#
# The browser opens this socket the moment PTT is pressed and forwards
# 16 kHz Int16 PCM frames as the worklet produces them. On PTT release
# it sends a `{"type":"end"}` JSON control message; we flush
# `audio_stream_end` to Gemini and return the final transcript.
#
# Why bother:
#   - Today's `POST /voice/turn` waits until PTT release to *start*
#     uploading the WAV, then `_stt_sync` round-trips the entire blob
#     through `generate_content`. STT alone is ~600-1500 ms of pure
#     wait at the top of every voice turn.
#   - Live STT runs incrementally: most of the audio is already in
#     Gemini by the time PTT releases, so the final transcript usually
#     arrives within ~150-300 ms of the last audio frame.
#
# The endpoint is opt-in from the client side. Browsers that fail to
# open the WebSocket (corp proxy, dev mismatch, etc.) just fall back to
# the multipart path, which is unchanged.
# ---------------------------------------------------------------------------


@router.websocket("/voice/stream/stt")
async def voice_stream_stt(ws: WebSocket) -> None:
    if not _streaming_stt_enabled():
        await ws.close(code=1008, reason="streaming STT disabled")
        return

    await ws.accept()
    t_start = time.monotonic()
    final_parts: list[str] = []
    bytes_in = 0

    try:
        from google.genai import types as gtypes
    except Exception:
        await ws.send_json(
            {"type": "error", "message": "google-genai SDK missing; cannot stream STT"}
        )
        await ws.close()
        return

    client = _genai_client()
    model = _live_stt_model()
    config = gtypes.LiveConnectConfig(
        # We don't actually consume the model's response -- we only want
        # `server_content.input_transcription`. The current Live preview
        # models (gemini-3.1-flash-live-preview, gemini-2.5-flash-native-
        # audio-preview-12-2025) are all native-audio and reject any
        # response_modalities other than AUDIO with `1011 internal error`
        # at connect time. The previous default (`gemini-live-2.5-flash-
        # preview`) tolerated TEXT, but it was retired from v1beta. The
        # reader below only inspects `input_transcription`, so the model's
        # AUDIO output is generated, sent over the wire, and discarded
        # silently. That's wasteful in bandwidth but free in our hot
        # path -- the system instruction asks the model to keep the reply
        # near-empty so the audio blob is tiny.
        response_modalities=["AUDIO"],
        input_audio_transcription=gtypes.AudioTranscriptionConfig(),
        system_instruction=(
            "You are a transcription engine. The user has been instructed "
            "not to address you. Respond with an empty string for every "
            "turn -- the actual value we consume is `input_transcription`."
        ),
    )

    try:
        async with client.aio.live.connect(model=model, config=config) as session:

            async def reader() -> None:
                """Drain Gemini Live messages and accumulate the transcript."""
                async for msg in session.receive():
                    sc = getattr(msg, "server_content", None)
                    if sc is None:
                        continue
                    it = getattr(sc, "input_transcription", None)
                    if it is not None and getattr(it, "text", None):
                        text = it.text
                        final_parts.append(text)
                        try:
                            await ws.send_json(
                                {"type": "partial_transcript", "text": text}
                            )
                        except Exception:
                            return
                    if getattr(sc, "turn_complete", False) or (
                        it is not None and getattr(it, "finished", False)
                    ):
                        return

            reader_task = asyncio.create_task(reader())

            try:
                while True:
                    msg = await ws.receive()
                    msg_type = msg.get("type")
                    if msg_type == "websocket.disconnect":
                        break
                    if "bytes" in msg and msg["bytes"] is not None:
                        chunk = msg["bytes"]
                        if not chunk:
                            continue
                        bytes_in += len(chunk)
                        await session.send_realtime_input(
                            audio=gtypes.Blob(
                                data=chunk,
                                mime_type="audio/pcm;rate=16000",
                            )
                        )
                    elif msg.get("text"):
                        try:
                            ctrl = json.loads(msg["text"])
                        except Exception:
                            continue
                        if ctrl.get("type") == "end":
                            await session.send_realtime_input(
                                audio_stream_end=True
                            )
                            break
            except WebSocketDisconnect:
                pass

            # Wait for Gemini to flush the final input_transcription
            # chunk after we signaled audio_stream_end. The reader exits
            # on `turn_complete` or `finished`. 5s is a generous upper
            # bound; in practice Live wraps up within a few hundred ms.
            try:
                await asyncio.wait_for(reader_task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                pass
            finally:
                if not reader_task.done():
                    reader_task.cancel()
                    try:
                        await reader_task
                    except (asyncio.CancelledError, Exception):
                        pass

        full_text = "".join(final_parts).strip()
        ttfb_ms = (time.monotonic() - t_start) * 1000.0
        log.info(
            "voice_stream_stt: bytes=%d transcript_chars=%d total=%.0fms",
            bytes_in,
            len(full_text),
            ttfb_ms,
        )
        try:
            await ws.send_json({"type": "final_transcript", "text": full_text})
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("voice_stream_stt failed")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Local copies of small helpers from api.py (avoid a circular import).
# ---------------------------------------------------------------------------


def _flatten_content(content: Any) -> str:
    """Same logic as api._flatten_content -- coerce LangChain content to str."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------------
# Turn endpoint.
# ---------------------------------------------------------------------------


@router.post("/voice/turn")
async def voice_turn(
    audio: Annotated[UploadFile | None, File(description="WAV/PCM audio of the user's turn")] = None,
    transcript: Annotated[str | None, Form()] = None,
    thread_id: Annotated[str | None, Form()] = None,
    brain: Annotated[str | None, Form()] = None,
    tenant_id: Annotated[str, Form()] = "local",
    page: Annotated[str | None, Form()] = "dashboard",
    profile: Annotated[str, Form()] = "chat",
    user_lat: Annotated[float | None, Form()] = None,
    user_lng: Annotated[float | None, Form()] = None,
):
    """Run one voice turn through the chat agent and stream audio + events.

    Body is multipart/form-data. Two paths are supported:

    1. **Multipart with `audio`** (legacy): a WAV (16 kHz mono PCM is the
       expected shape, but Gemini accepts any common audio MIME). The
       harness runs server-side STT before invoking the agent.
    2. **Multipart with `transcript`** (streaming-STT path): the browser
       has already streamed audio to `/voice/stream/stt` and resolved
       the final transcript over the WebSocket. We skip server-side STT
       entirely. `audio` is then optional.

    `user_lat`/`user_lng` are optional and, when provided, are prepended
    to the transcript as a tagged line so the agent can use them as the
    implicit origin for "how do I get to X" routing questions on the
    dashboard.
    """
    # `transcript` is a tri-state:
    #   None     -> client did not run streaming STT; server must do its own.
    #   ""       -> streaming STT succeeded but heard nothing (silence/noise).
    #               Skip server STT and short-circuit to an empty turn.
    #   "abc..." -> streaming STT succeeded with text. Use it directly.
    transcript_text: str | None = None
    if transcript is not None:
        transcript_text = transcript.strip()
    audio_bytes: bytes = b""
    mime = "audio/wav"
    if audio is not None:
        audio_bytes = await audio.read()
        mime = audio.content_type or "audio/wav"
    if not audio_bytes and transcript_text is None:
        raise HTTPException(400, "either `audio` or `transcript` must be provided")

    return StreamingResponse(
        _voice_turn_stream(
            audio_bytes=audio_bytes,
            mime=mime,
            transcript_override=transcript_text,
            thread_id=thread_id,
            brain=brain,
            tenant_id=tenant_id,
            page=page,
            profile=profile,
            user_lat=user_lat,
            user_lng=user_lng,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _voice_turn_stream(
    *,
    audio_bytes: bytes,
    mime: str,
    thread_id: str | None,
    brain: str | None,
    tenant_id: str = "local",
    page: str | None,
    profile: str,
    user_lat: float | None = None,
    user_lng: float | None = None,
    transcript_override: str | None = None,
) -> AsyncIterator[str]:
    # Lazy imports to dodge circular references with api.py.
    from .api import _agent_for
    from .system_prompt import DEFAULT_BRAIN
    from .tools.memory_tools import reset_turn_budget, set_active_tenant
    from disease360_runtime.research.tool import reset_research_budget

    resolved_thread = thread_id or uuid.uuid4().hex
    resolved_brain = brain or DEFAULT_BRAIN
    resolved_page = (page or "").strip() or None
    turn_id = uuid.uuid4().hex

    bridge = ClientToolBridge()
    register_turn(turn_id, bridge)

    out_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    DONE = None  # sentinel placed on the queue when generation is finished

    # Per-stage timings used at the end of the turn to log a single
    # `voice_turn_timings ...` line. All values are wall-clock ms since
    # `t_start`. `None` means the stage didn't fire (e.g. empty
    # transcript -> no agent stream, no first token, no audio).
    t_start = time.monotonic()
    timings: dict[str, float | None] = {
        "stt_done": None,
        "first_token": None,
        "first_audio_pushed": None,
        "agent_done": None,
        "total": None,
    }

    def mark(stage: str) -> None:
        if timings.get(stage) is None:
            timings[stage] = (time.monotonic() - t_start) * 1000.0

    async def push(evt: dict) -> None:
        # Stamp the first audio chunk leaving the server so we have a
        # real time-to-first-audio measurement (TTFA) per turn.
        if evt.get("type") == "audio":
            mark("first_audio_pushed")
        await out_queue.put(evt)

    tts = TTSPipeline(push=push, voice_name=_voice_name())

    async def bridge_drainer() -> None:
        try:
            while True:
                evt = await bridge.events.get()
                await push(evt)
        except asyncio.CancelledError:
            pass

    async def agent_worker() -> None:
        token = set_active_bridge(bridge)
        try:
            await push(
                {
                    "type": "meta",
                    "thread_id": resolved_thread,
                    "turn_id": turn_id,
                    "brain": resolved_brain,
                    "page": resolved_page,
                }
            )

            # Skip server-side STT when the browser already streamed the
            # audio through `/voice/stream/stt` and supplied the final
            # transcript via the `transcript` form field. This is the
            # primary win of the streaming-STT path: ~600-1500 ms shaved
            # off the top of the turn because most of the audio was
            # already in Gemini by the time PTT released.
            if transcript_override is not None:
                transcript = transcript_override
            else:
                try:
                    transcript = await asyncio.to_thread(_stt_sync, audio_bytes, mime)
                except Exception as e:
                    log.exception("STT failed")
                    await push({"type": "error", "message": f"STT failed: {e}"})
                    return
            mark("stt_done")
            transcript = transcript.strip()
            if not transcript:
                await push({"type": "transcript", "text": ""})
                await push(
                    {
                        "type": "done",
                        "thread_id": resolved_thread,
                        "empty": True,
                    }
                )
                return
            await push({"type": "transcript", "text": transcript})

            # Prepend a location tag the agent can lean on for implicit-origin
            # routing ("how do I get to X" with no starting point named).
            # Sanitize numerically and only add the tag when both fields are
            # finite to avoid feeding NaN/Infinity into the prompt.
            agent_input = transcript
            if (
                user_lat is not None
                and user_lng is not None
                and math.isfinite(float(user_lat))
                and math.isfinite(float(user_lng))
            ):
                agent_input = (
                    f"[Bruno's current location: {float(user_lat):.5f}, "
                    f"{float(user_lng):.5f}]\n{transcript}"
                )

            agent = _agent_for(profile, resolved_brain, resolved_page, voice=True)
            config = {
                "configurable": {"thread_id": resolved_thread},
                "recursion_limit": 60,
            }
            set_active_tenant(tenant_id)
            reset_turn_budget()
            reset_research_budget()

            seen_tool_calls: set[str] = set()
            seen_tool_results: set[str] = set()
            # Last seen usage_metadata across the whole stream. Gemini
            # accumulates token counts on the final AIMessageChunk; we
            # surface `cached_content_token_count` so we can confirm
            # implicit prefix caching is firing turn-over-turn.
            last_usage: Any = None

            try:
                async for mode, data in agent.astream(
                    {"messages": [{"role": "user", "content": agent_input}]},
                    config=config,
                    stream_mode=["messages"],
                ):
                    if mode == "messages":
                        chunk, _meta = data
                        chunk_type = getattr(chunk, "type", None)

                        if chunk_type == "tool":
                            tc_id = getattr(chunk, "tool_call_id", None) or getattr(
                                chunk, "id", None
                            )
                            if tc_id and tc_id not in seen_tool_results:
                                seen_tool_results.add(tc_id)
                                await push(
                                    {
                                        "type": "tool_done",
                                        "name": getattr(chunk, "name", "") or "",
                                        "tool_call_id": tc_id,
                                    }
                                )
                            continue

                        if chunk_type not in ("ai", "AIMessageChunk", "AIMessage"):
                            continue

                        for tc in getattr(chunk, "tool_calls", None) or []:
                            name = (
                                tc.get("name")
                                if isinstance(tc, dict)
                                else getattr(tc, "name", None)
                            )
                            tc_id = (
                                tc.get("id")
                                if isinstance(tc, dict)
                                else getattr(tc, "id", None)
                            ) or name
                            if not name or tc_id in seen_tool_calls:
                                continue
                            seen_tool_calls.add(tc_id)
                            args = (
                                tc.get("args")
                                if isinstance(tc, dict)
                                else getattr(tc, "args", {})
                            )
                            await push(
                                {
                                    "type": "tool",
                                    "name": name,
                                    "args": args or {},
                                    "tool_call_id": tc_id,
                                }
                            )
                            cue = _next_cue(name)
                            if cue:
                                tts.speak_now(cue)

                        usage = getattr(chunk, "usage_metadata", None)
                        if usage is not None:
                            last_usage = usage

                        # Only stream tokens from the top-level agent node.
                        # Nested tool calls (e.g. deep_research internal LLMs)
                        # produce chunks from other nodes — skip them.
                        node = (_meta or {}).get("langgraph_node", "")
                        if node and node not in ("model", "agent"):
                            continue

                        text = _flatten_content(getattr(chunk, "content", None))
                        if text:
                            mark("first_token")
                            await push({"type": "token", "text": text})
                            tts.feed_text(text)

            except Exception as e:
                log.exception("agent stream crashed")
                await push({"type": "error", "message": str(e)})

            await tts.flush_remainder()
            mark("agent_done")
            await push(
                {
                    "type": "done",
                    "thread_id": resolved_thread,
                }
            )
        finally:
            reset_active_bridge(token)
            timings["total"] = (time.monotonic() - t_start) * 1000.0
            # Single-line timing log per turn. Helps verify each layer of
            # the latency plan: STT (post-step-5 streaming), agent first
            # token (post-step-3 context cache), first-audio TTFA
            # (post-steps-1/2/4 TTS path). `cache_read` is the number of
            # input tokens served from Gemini's prefix cache (implicit or
            # explicit) on the LAST chunk of the turn.
            cache_read: int | None = None
            try:
                if last_usage is not None:
                    raw = (
                        last_usage.get("input_token_details", {}).get("cache_read")
                        if isinstance(last_usage, dict)
                        else getattr(getattr(last_usage, "input_token_details", None), "cache_read", None)
                    )
                    if isinstance(raw, int):
                        cache_read = raw
            except Exception:
                cache_read = None

            def _fmt(v: float | None) -> str:
                return "—" if v is None else f"{v:.0f}ms"

            log.info(
                "voice_turn_timings turn=%s stt=%s first_token=%s first_audio=%s agent_done=%s total=%s cache_read=%s",
                turn_id,
                _fmt(timings["stt_done"]),
                _fmt(timings["first_token"]),
                _fmt(timings["first_audio_pushed"]),
                _fmt(timings["agent_done"]),
                _fmt(timings["total"]),
                cache_read if cache_read is not None else "—",
            )
            await out_queue.put(DONE)

    agent_task = asyncio.create_task(agent_worker())
    drainer_task = asyncio.create_task(bridge_drainer())

    try:
        while True:
            evt = await out_queue.get()
            if evt is DONE:
                break
            yield _sse(evt)
    finally:
        drainer_task.cancel()
        if not agent_task.done():
            agent_task.cancel()
        await tts.cancel()
        await bridge.close()
        unregister_turn(turn_id)


# ---------------------------------------------------------------------------
# Tool-result endpoint.
# ---------------------------------------------------------------------------


class ToolResultBody(BaseModel):
    call_id: str
    result: dict[str, Any] = {}


@router.post("/voice/turn/{turn_id}/tool_result")
async def voice_tool_result(turn_id: str, body: ToolResultBody) -> dict:
    bridge = get_turn_bridge(turn_id)
    if bridge is None:
        raise HTTPException(404, "turn not found (expired or unknown)")
    ok = bridge.resolve(body.call_id, body.result or {"ok": True})
    return {"ok": ok}
