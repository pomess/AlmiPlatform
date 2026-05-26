"""Tiny CLI chatbot to verify Gemini 3 Flash Preview native grounding.

Streams replies with the built-in `google_search` tool enabled and prints
the grounding metadata (queries the model issued + cited source URIs)
after each turn, so you can confirm grounding actually fired.

Usage:
    python scripts/grounding_chat.py
    python scripts/grounding_chat.py --model gemini-3-flash-preview
    python scripts/grounding_chat.py --no-grounding   # A/B compare

Reads GOOGLE_API_KEY from the environment, falling back to
policies/secrets.env (KEY=VALUE lines).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _print_grounding(resp) -> None:
    """Pretty-print groundingMetadata if present on the final response."""
    cands = getattr(resp, "candidates", None) or []
    if not cands:
        return
    gm = getattr(cands[0], "grounding_metadata", None)
    if gm is None:
        print("\n[grounding] no grounding_metadata on response (model did not search).")
        return

    queries = getattr(gm, "web_search_queries", None) or []
    chunks = getattr(gm, "grounding_chunks", None) or []
    supports = getattr(gm, "grounding_supports", None) or []

    print("\n[grounding] queries issued:")
    if queries:
        for q in queries:
            print(f"  - {q}")
    else:
        print("  (none)")

    print(f"[grounding] sources ({len(chunks)}):")
    for i, ch in enumerate(chunks, 1):
        web = getattr(ch, "web", None)
        if web is None:
            continue
        title = getattr(web, "title", "") or ""
        uri = getattr(web, "uri", "") or ""
        print(f"  [{i}] {title}\n      {uri}")

    if supports:
        print(f"[grounding] {len(supports)} citation span(s) attached to text.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3-flash-preview",
                    help="Gemini model id (default: gemini-3-flash-preview).")
    ap.add_argument("--no-grounding", action="store_true",
                    help="Disable the google_search tool (for A/B comparison).")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    _load_env_file(repo_root / "policies" / "secrets.env")

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: set GOOGLE_API_KEY (or GEMINI_API_KEY) in env or policies/secrets.env",
              file=sys.stderr)
        sys.exit(2)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    tools = None if args.no_grounding else [types.Tool(google_search=types.GoogleSearch())]
    cfg = types.GenerateContentConfig(tools=tools) if tools else None

    chat = client.chats.create(model=args.model, config=cfg)

    print(f"Model:     {args.model}")
    print(f"Grounding: {'OFF' if args.no_grounding else 'ON (google_search)'}")
    print("Type a message. Ctrl-C or empty line + Ctrl-D to quit.\n")

    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user:
            continue

        print("bot> ", end="", flush=True)
        final = None
        for chunk in chat.send_message_stream(user):
            txt = getattr(chunk, "text", None)
            if txt:
                print(txt, end="", flush=True)
            final = chunk
        print()
        if final is not None:
            _print_grounding(final)
        print()


if __name__ == "__main__":
    main()
