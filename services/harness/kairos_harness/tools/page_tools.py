"""Page-scoped client-executed tools, tool allowlists, and persona prompts.

Pages in the web app can lend the agent extra capabilities scoped to that
surface — e.g. the dashboard map exposes `fly_to_location`. These tools
don't run any Python work; they hand the call to the active
`ClientToolBridge` and await the browser's result.

A page can also override two more things on top of the default agent:

- A **base tool allowlist** (`PAGE_BASE_TOOLS`) — replaces the full
  `all_memory_tools()` set with a curated subset, so e.g. the dashboard
  voice agent never sees the destructive ingest/solve tools.
- A **system-prompt addendum** (`PAGE_PROMPTS`) — a page-specific
  "skill" injected on top of SOUL/USER/brain (and on top of JARVIS for
  voice turns), so the agent knows the surface it's on.

The agent is built once per `(profile, brain, page, voice)` with all
three layers wired through `build_agent`. The bridge is per-turn and is
read from a `ContextVar`, so tool bodies find the right bridge.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx
from kairos_runtime.config import get as config_get
from langchain_core.tools import tool

from ..client_tools import get_active_bridge
from .memory_tools import (
    append_hot,
    get_hot,
    get_index,
    get_page,
    list_brains,
    search_wiki,
)

log = logging.getLogger(__name__)


@tool
async def fly_to_location(
    lat: float,
    lng: float,
    place: str,
    zoom: float = 11.0,
) -> str:
    """Move the dashboard globe to a place and frame it for the user.

    Call this whenever the user names a location they want to see, travel
    to, or talk about. Supply your best estimate of the latitude and
    longitude in decimal degrees. Pick `zoom` so the place actually fills
    the view — go close, not continental:

    - 13-14: a single building, monument, statue, park, or street
    - 11-12: a city or borough (default — use this when unsure)
    - 9-10:  a metropolitan area or small region
    - 7-8:   a large region, state, or province
    - 5-6:   a country
    - 3-4:   a whole continent (only when the user explicitly asks)

    `zoom` must be 1-14. Default to 11 (city framing) if the user just
    names a place without further context, and prefer 13+ for specific
    landmarks or buildings.
    """
    bridge = get_active_bridge()
    if bridge is None:
        return (
            "Map control is not available right now. Tell the user the "
            "globe could not move and continue answering anyway."
        )
    result = await bridge.call(
        "fly_to_location",
        {"lat": float(lat), "lng": float(lng), "place": str(place), "zoom": float(zoom)},
    )
    if result.get("ok"):
        return (
            f"Map flew to {place} ({lat:.3f}, {lng:.3f}) at zoom {zoom:g}. "
            f"You may now describe the place to the user briefly."
        )
    return (
        f"Map could not move to {place}: "
        f"{result.get('error', 'unknown error')}. Continue anyway."
    )


# ---------------------------------------------------------------------------
# Routing (OpenRouteService) — server-side call, browser renders the GeoJSON
# ---------------------------------------------------------------------------

# ORS profile names per travel mode. Keep this small and explicit; the model
# is told to pass one of {driving, cycling, walking}.
_ORS_PROFILES = {
    "driving": "driving-car",
    "cycling": "cycling-regular",
    "walking": "foot-walking",
}


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m{sec:02d}s" if sec else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if m else f"{h}h"


# Narration-grade ETA formatter. MUST stay byte-for-byte equivalent to the
# dashboard chip's `formatEtaShort` in apps/web/src/components/DashboardPage.tsx
# so the headline number the agent speaks ("about sixteen minutes") matches
# the headline number the user reads on the floating ETA chip ("16 min").
# Previously the agent narrated from `_format_duration` (which truncates to
# floor minutes + seconds, e.g. "15m30s" -> agent says "15 minutes") while
# the chip rounds the same 930 s up to "16 min". Same trip, two different
# headline numbers on screen vs. in the voice -- felt like an internal
# contradiction.
def _format_duration_display(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "<1 min"
    total = round(seconds)
    if total < 60:
        return "<1 min"
    minutes = round(total / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    rem = minutes % 60
    return f"{hours}h" if rem == 0 else f"{hours}h {rem}m"


def _format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{int(meters)}m"
    return f"{meters / 1000:.1f}km"


# Pull the named roads that actually carry the trip out of an ORS feature.
# Walks `properties.segments[].steps[]`, aggregates distance per `name`,
# and returns the longest few -- giving the agent a "via" hint it can
# weave into the narration ("...via the C-33 and the Ronda de Dalt").
#
# Filters:
#   - skip steps with empty / "-" name (unnamed connectors, slip roads)
#   - require an aggregate of >= `min_meters` per road, so a 50 m
#     micro-segment that happens to be on a named street doesn't get
#     promoted to a headline road for the trip
#
# Returns at most `max_roads` names, longest-first. Empty list is fine
# (e.g. a 700 m walk inside one neighbourhood) -- the caller suppresses
# the "via" clause in that case.
def _extract_via_roads(
    feature: dict,
    *,
    max_roads: int = 3,
    min_meters: float = 800.0,
) -> list[str]:
    props = feature.get("properties") or {}
    segments = props.get("segments") or []
    by_name: dict[str, float] = {}
    for seg in segments:
        for step in seg.get("steps") or []:
            name = (step.get("name") or "").strip()
            if not name or name == "-":
                continue
            dist = float(step.get("distance") or 0.0)
            if dist <= 0:
                continue
            by_name[name] = by_name.get(name, 0.0) + dist
    ranked = sorted(by_name.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, dist in ranked if dist >= min_meters][:max_roads]


@tool
async def show_route(
    from_lat: float,
    from_lng: float,
    to_lat: float,
    to_lng: float,
    from_place: str,
    to_place: str,
    mode: str = "driving",
) -> str:
    """Draw a route on the dashboard globe between two places.

    Use this whenever the user asks for directions, "how do I get from
    X to Y", "route to Z", "show me the way from A to B", or compares
    travel between two named places. Supply your best lat/lng for both
    endpoints in decimal degrees.

    `mode` must be one of:
    - "driving" (default — use this when unsure or for "transit")
    - "cycling"
    - "walking"

    The route is drawn as a glowing polyline on top of the existing
    globe view. Origin and destination markers are dropped, and the
    camera frames the whole route. Previous routes are replaced.

    Routes are STICKY: they persist across `fly_to_location` calls and
    can only be removed with `clear_map`. Don't call `clear_map`
    automatically — only when the user explicitly asks to clear/reset
    the map.
    """
    bridge = get_active_bridge()
    if bridge is None:
        return (
            "Map control is not available right now. Tell the user the "
            "route could not be drawn and continue answering anyway."
        )

    profile = _ORS_PROFILES.get(mode.lower().strip(), "driving-car")
    api_key = config_get("KAIROS_OPENROUTESERVICE_KEY")
    if not api_key:
        return (
            "Routing is not configured (no OpenRouteService key). Tell "
            "the user routing is offline and answer the question without "
            "drawing a route."
        )

    url = f"https://api.openrouteservice.org/v2/directions/{profile}/geojson"
    payload = {
        "coordinates": [
            [float(from_lng), float(from_lat)],
            [float(to_lng), float(to_lat)],
        ],
        # Turn-by-turn instructions on so we can distill a "via" hint from
        # the named roads (`segments[].steps[].name`). The frontend ignores
        # the steps array; this is purely for narration enrichment.
        "instructions": True,
    }
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, application/geo+json",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("ORS request failed: %s", exc)
        return (
            f"Could not reach the routing service ({exc.__class__.__name__}). "
            f"Tell the user routing is unavailable right now and continue."
        )

    if resp.status_code >= 400:
        # ORS returns JSON errors with {"error": {"code": ..., "message": ...}}.
        try:
            err = resp.json().get("error") or {}
            msg = err.get("message") or resp.text[:200]
        except Exception:
            msg = resp.text[:200]
        log.warning("ORS %s rejected request: %s", resp.status_code, msg)
        return (
            f"Routing service rejected the request ({resp.status_code}): {msg}. "
            f"Tell the user the route between {from_place} and {to_place} "
            f"isn't available and continue."
        )

    data = resp.json()
    features = data.get("features") or []
    if not features:
        return (
            f"No route was found between {from_place} and {to_place}. "
            f"Tell the user that and continue."
        )
    feature = features[0]
    summary = (feature.get("properties") or {}).get("summary") or {}
    distance_m = float(summary.get("distance") or 0.0)
    duration_s = float(summary.get("duration") or 0.0)

    bridge_args = {
        "geojson": feature,
        "from": {"lat": float(from_lat), "lng": float(from_lng), "place": str(from_place)},
        "to": {"lat": float(to_lat), "lng": float(to_lng), "place": str(to_place)},
        "mode": mode.lower().strip(),
        "summary": {"distance_m": distance_m, "duration_s": duration_s},
    }
    # Routing payloads are larger than fly_to_location (full polyline geometry).
    # Give the bridge a generous timeout so a slow client paint doesn't fail.
    result = await bridge.call("show_route", bridge_args, timeout=20.0)

    if not result.get("ok"):
        return (
            f"Route could not be drawn: "
            f"{result.get('error', 'unknown error')}. Continue anyway."
        )

    distance_str = _format_distance(distance_m)
    # `eta_str` is what the floating ETA chip will display once the route
    # flyover lands on the destination. Narrate the SAME string so the
    # spoken minutes and the on-screen minutes always agree.
    eta_str = _format_duration_display(duration_s)
    # `precise_str` is the full m:ss precision in case the agent wants to
    # clarify ("about 16 minutes -- 15 and a half, really"); should NOT
    # be used as the headline number.
    precise_str = _format_duration(duration_s)
    via_roads = _extract_via_roads(feature)
    via_clause = f"; via {', '.join(via_roads)}" if via_roads else ""
    via_directive = (
        " Also weave in 1-2 of the via roads naturally so the user knows "
        "the rough path (e.g. 'via the C-33 and the Ronda de Dalt'). "
        "Use the road names verbatim from the via list -- don't invent "
        "or translate them."
        if via_roads
        else ""
    )
    return (
        f"Drew {mode} route {from_place} -> {to_place} on the globe "
        f"({distance_str}, ETA {eta_str}; precise {precise_str}{via_clause}). "
        f"Narrate this to the user in one short sentence. Use '{eta_str}' "
        f"verbatim for the time -- that is exactly the number the on-screen "
        f"ETA chip is showing, so any other rounding will read as "
        f"inconsistent.{via_directive}"
    )


@tool
async def clear_map() -> str:
    """Clear all routes and pins from the dashboard globe.

    Call this ONLY when the user explicitly asks to clear, reset, wipe,
    or remove what's on the map — e.g. "clear the map", "clear
    everything", "reset the map", "wipe it", "get rid of all that",
    "remove the route". Treat the trigger as exact: a synonym of
    "clear" must be in the user's message.

    Do NOT call this:
    - On your own initiative.
    - As a side effect of drawing a new route or flying somewhere.
    - When the user just changes topic or asks about a new place.
    - When in doubt — leave the map as it is.

    Routes are designed to persist across `fly_to_location` calls and
    across new `show_route` calls (which simply replace the prior
    route). The user must speak the intent to clear.
    """
    bridge = get_active_bridge()
    if bridge is None:
        return (
            "Map control is not available right now. Tell the user the "
            "map could not be cleared and continue answering anyway."
        )
    result = await bridge.call("clear_map", {})
    if result.get("ok"):
        return "Map cleared. Briefly confirm out loud, e.g. 'Cleared.'"
    return (
        f"Map could not be cleared: "
        f"{result.get('error', 'unknown error')}. Continue anyway."
    )


# ---------------------------------------------------------------------------
# Page system-prompt addendums ("skills")
# ---------------------------------------------------------------------------

DASHBOARD_SKILL = """\
DASHBOARD CONTEXT
You're answering on Bruno's dashboard: a 3D holographic globe of Earth.
Bruno is looking at the map while talking to you.

What people ask here
- Places: "where is X", "show me Y", "take me to Z"
- Geography & landmarks: countries, cities, monuments, rivers, mountains
- Travel & culture: "what's it like in...", "what's nearby...", "best time to visit..."
- News and events tied to a location

Map rule (non-negotiable)
Whenever Bruno mentions ANY physical place — even casually, even mid-sentence
— call `fly_to_location` for it BEFORE you start your verbal reply. Do this
on every place mention, not only when explicitly asked. The point is the
globe moves with the conversation. Pick zoom from how specific the place is:
- 13-14: a building, monument, statue, park, or single street
- 11-12: a city or borough (default — use this when unsure)
- 9-10:  a metropolitan area or small region
- 7-8:   a large region, state, or province
- 5-6:   a country
- 3-4:   a continent (only when the user explicitly asks for one)

Routing rule (directions / "from X to Y")
When Bruno asks how to get somewhere, asks for directions, says "from X
to Y", "route from X to Y", "drive to Z", or compares travel between two
named places, call `show_route` instead of (or in addition to) flying.
Supply your best lat/lng for both endpoints. Pick `mode`:
- "driving" — default; use for "how do I get to", "drive", "by car",
  and for "transit" or "by bus/train" (we don't have a transit profile,
  so route by car and add a brief verbal caveat).
- "cycling" — only if Bruno says bike / cycle / cycling.
- "walking" — only if Bruno says walk / on foot / walking.
After the route draws, narrate it in one short sentence (distance and
time live in the tool's return value — quote them naturally, e.g.
"About three hours by car, mostly via the A1.").

Implicit origin = Bruno's current location
The browser prepends a tag at the top of his message whenever it has a
GPS fix, like `[Bruno's current location: 41.42345, 2.18012]`. Treat
that tag as the AUTHORITATIVE source of truth for where Bruno is.

When he asks for a route WITHOUT naming a starting point — "how do I
get to X", "route to X", "take me to X", "drive me to Y", "how far is
Z from here" — use the tagged lat/lng as `from_lat`/`from_lng` and
pass `from_place="your location"` (or "here"). Do NOT invent an origin,
do NOT default to a city centre, do NOT use the destination's
neighbourhood as a stand-in. If the tag is missing AND he didn't name
an origin, ask him where he is starting from before drawing.

When he DOES name an origin ("from Sants to Deloitte", "from the
office to home"), use that — the tag is only a fallback for the
implicit case.

Never speak the raw coordinates back. The tag is a hint for tool
arguments, not for narration. Say "from where you are" or "from your
current location", not "from 41.42 north, 2.18 east".

Stickiness (very important)
Routes are sticky. They stay on the globe across new `fly_to_location`
calls and across topic changes. If Bruno asks for a different route,
just call `show_route` again — it replaces the previous one
automatically. Do NOT call `clear_map` between routes; the swap is
silent.

Clear rule (exact match — never volunteer this)
Call `clear_map` ONLY when Bruno explicitly says to clear / reset /
wipe / remove the map / "get rid of all that" / "remove the route".
A synonym of "clear" must be in his message. Never call `clear_map`:
- On your own initiative.
- As a side effect of drawing a new route or flying somewhere.
- Because the conversation moved on.
- When in doubt — leave the map alone.
After clearing, confirm in one short word ("Cleared.") and stop.

Knowledge bias
For general-knowledge geography (capitals, where Mount Fuji is, what country
borders Brazil, when to visit Kyoto) answer from your own knowledge — do
NOT reach for memory tools. Only call `search_wiki` / `get_page` when Bruno
explicitly asks about HIS notes or something he wrote ("what did I write
about Tokyo?", "pull up my Lisbon page").

Voice delivery
Replies are spoken aloud. Keep them tight: 1-3 sentences, conversational,
no headings, no bullet lists, no markdown. The map does the visual talking;
your job is to narrate, not to lecture.

WRITE CAPABILITY (very limited here)
On the dashboard you have ONE write tool only: `append_hot` -- and only
for ephemeral one-liner notes scoped to the current conversation. You
do NOT have `plan_ingest`, `apply_ingest`, `write_note`, `replace_hot`,
or any other ingest/page tool. They are not in your toolset on this
surface. Do not pretend they are. Do not say you saved a page, added
to your brain, captured a fact, or ingested anything -- you cannot.

DEFAULT IS OFF. Do NOT call `append_hot` for ANY of these:
- Greetings or small talk ("hi", "ay, what's up", "good evening")
- Questions about the world, geography, or general knowledge
- Questions about what's already in the brain
- In-the-moment thinking that isn't framed as "remember"
- Anything ambiguous -- WHEN IN DOUBT, DO NOT CAPTURE.

`append_hot` is allowed ONLY when Bruno gives an EXPLICIT, in-the-moment
working-memory instruction, e.g.: "remember for now that I'm focusing
on X", "note for this session that I'm in a hurry", "stash that I'm
pairing with Joan today". One-liner, ephemeral, conversational scope.
NEVER use it for persistent facts (people, projects, decisions,
identity, dates, plans). Those need full ingest, which lives in Chat.

If Bruno asks you to save / capture / record / store / ingest / write
down / "put this in my brain" / "add a page about X" -- anything
beyond a one-liner ephemeral note -- the correct response is to TELL
HIM the dashboard can't do that and redirect: "I can only stash quick
working-memory notes here. Switch to Chat and I'll capture that
properly through the approval flow." Then stop. Do not pretend you
captured it.

When you DO call `append_hot`, briefly confirm out loud: "Stashed in
your hot cache." -- one short sentence, no theatre.

Hand-off discipline
If you have already told Bruno in this thread that something needs to
be done in Chat, DO NOT keep repeating that line on every follow-up
turn. He heard you. On follow-ups about the SAME task either:
- Acknowledge briefly ("Still parked on that one -- it'll come together
  once you switch to Chat."), or
- Move on to whatever he is actually asking about now.
Never re-emit the full "On this dashboard I only have ... switch over
to Chat ..." paragraph more than once per task. Repeating it bloats
the shared thread's history and bleeds into the chat agent's replies
when Bruno does switch over.

Tool routing (memory)
The KNOWLEDGE LANDSCAPE block at the top of your prompt names every key
entity and concept across all of Bruno's brains, with the page path next
to each one. When Bruno asks about ANY topic listed there:
- Call `get_page(path, brain=...)` DIRECTLY using the path from the atlas.
  Do NOT call `search_wiki` first -- it reindexes every vault and takes
  ~25 seconds; a direct page read takes ~1 second.
- Only fall back to `search_wiki` when the topic is genuinely not named
  in the atlas, and even then scope it to the most likely brain.

Verbal connectors (fill the silence)
Before calling `search_wiki` or `get_page`, speak ONE short, specific
sentence naming what you are checking -- "Let me pull up your Almirall
page.", "Checking your Deloitte notes on Vera.", "Looking at your RAG
page." -- and then call the tool. The user hears the sentence aloud
while the lookup runs, so they're never sitting in silence wondering
whether you heard them. Be specific: name the brain, project, person,
or page. Avoid empty filler ("Looking.", "One moment.") on its own.
"""


# ---------------------------------------------------------------------------
# Registries — `_agent_for(profile, brain, page, voice=...)` reads these.
# ---------------------------------------------------------------------------

PAGE_TOOLS: dict[str, Sequence] = {
    "dashboard": (fly_to_location, show_route, clear_map),
}

# Page-scoped base toolset. When a page is listed here its agent gets THIS
# list instead of the default `all_memory_tools()` — page tools from
# `PAGE_TOOLS` are still appended on top. Pages absent from this dict fall
# back to the full memory toolkit.
#
# Dashboard set: read tools + `append_hot` ONLY. Voice + Gemini Flash is
# a noisy match for the heavy ingest pipeline -- `plan_ingest`'s
# docstring ("use whenever the user shares a meaningful fact") makes the
# model fish for it on every casual turn, and on voice the user can't
# review a diff aloud anyway. So full page authoring lives in typed Chat
# (where the model has the full toolset and the user reads the approval
# card). The dashboard keeps `append_hot` for one-line working-memory
# notes -- its docstring is tightly constrained ("Use ONLY for
# observations scoped to the current conversation") and doesn't fish.
PAGE_BASE_TOOLS: dict[str, Sequence] = {
    "dashboard": (
        search_wiki,
        get_page,
        get_index,
        get_hot,
        list_brains,
        append_hot,
    ),
}

PAGE_PROMPTS: dict[str, str] = {
    "dashboard": DASHBOARD_SKILL,
}


def tools_for_page(page: str | None) -> list:
    """Page-scoped *additional* tools (UI tools like `fly_to_location`)."""
    if not page:
        return []
    return list(PAGE_TOOLS.get(page, ()))


def base_tools_for_page(page: str | None) -> list | None:
    """Curated base toolset for a page, or None to use the default."""
    if not page:
        return None
    base = PAGE_BASE_TOOLS.get(page)
    return list(base) if base is not None else None


def prompt_for_page(page: str | None) -> str | None:
    """Page-scoped system-prompt addendum, or None for stock behaviour."""
    if not page:
        return None
    return PAGE_PROMPTS.get(page)
