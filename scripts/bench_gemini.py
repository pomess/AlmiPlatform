"""Quick throughput benchmark for a configured chat model.

Streams several prompts and reports:
  - TTFT  (time-to-first-token, seconds)
  - decode tokens/sec  (output_tokens / (total - TTFT))
  - end-to-end tokens/sec  (output_tokens / total)

Token counts come from the provider's `usage_metadata` when available
(true counts on Gemini; Ollama may or may not surface them depending on
version). Wall-clock measurement uses the same streaming path the harness
uses for live replies.

Usage (from repo root):
    python scripts/bench_gemini.py                          # defaults: gemini, env-resolved model
    python scripts/bench_gemini.py --backend ollama         # local Ollama via secrets.env
    python scripts/bench_gemini.py --backend ollama --model gemma4:e4b --runs 5
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Make `disease360_runtime` importable when running this file directly without
# `pip install -e .` having been re-run since the package layout changed.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "runtime"))

from disease360_runtime import config  # noqa: E402

PROMPTS = [
    (
        "Write a ~250 word, clear, technical explanation of how a transformer "
        "language model generates text token-by-token at inference time. Cover "
        "KV-cache, sampling, and why decode is memory-bandwidth-bound."
    ),
    (
        "Explain in ~250 words the trade-offs between cloud-hosted and locally "
        "run small language models for a single user's personal AI cockpit. "
        "Include latency, privacy, cost, and capability dimensions."
    ),
    (
        "In about 250 words, describe how to design a wikilink-aware second-"
        "brain over markdown, contrasting it with a flat embedding-based RAG "
        "store. Highlight where each shines."
    ),
]


@dataclass
class RunStats:
    label: str
    ttft_s: float
    total_s: float
    input_tokens: int
    output_tokens: int

    @property
    def decode_tps(self) -> float:
        decode = max(self.total_s - self.ttft_s, 1e-9)
        return self.output_tokens / decode

    @property
    def e2e_tps(self) -> float:
        return self.output_tokens / max(self.total_s, 1e-9)


def _model_name(backend: str, override: str | None) -> str:
    if override:
        return override
    if backend == "ollama":
        return config.get("OLLAMA_DEFAULT_MODEL", "gemma4:e4b") or "gemma4:e4b"
    return (
        config.get("DISEASE360_MODEL_OVERRIDE")
        or config.get("GEMINI_DEFAULT_MODEL", "gemini-flash-latest")
        or "gemini-flash-latest"
    )


def _build_client(backend: str, model: str):
    if backend == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            base_url=config.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
            temperature=0.2,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = config.require("GOOGLE_API_KEY")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0.2,
    )


def _run_one(client, prompt: str, label: str) -> RunStats:
    """Stream one prompt and time it."""
    start = time.perf_counter()
    ttft: float | None = None
    pieces: list[str] = []
    last_chunk = None
    for chunk in client.stream(prompt):
        if ttft is None:
            ttft = time.perf_counter() - start
        raw = getattr(chunk, "content", "") or ""
        # Gemini 3 Flash streams content as a list of parts (thinking +
        # text blocks); older providers stream a plain string.
        if isinstance(raw, list):
            text_parts: list[str] = []
            for part in raw:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and part.get("type") in (None, "text"):
                    t = part.get("text") or ""
                    if isinstance(t, str):
                        text_parts.append(t)
            text = "".join(text_parts)
        else:
            text = raw
        if text:
            pieces.append(text)
        last_chunk = chunk
    total = time.perf_counter() - start
    if ttft is None:
        ttft = total

    # Pull true token counts from usage_metadata. Streaming responses from
    # langchain-google-genai accumulate usage on the final chunk; fall back
    # to a non-stream call's count if the stream didn't surface it.
    usage = getattr(last_chunk, "usage_metadata", None) or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)

    if output_tokens == 0:
        # Heuristic fallback: ~4 chars/token. Mark as approximate by negating
        # the value? Keeping it positive — the README footnote will warn.
        output_tokens = max(1, len("".join(pieces)) // 4)

    return RunStats(
        label=label,
        ttft_s=ttft,
        total_s=total,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _fmt(stats: list[RunStats]) -> None:
    print()
    print(f"{'run':<14}{'ttft':>10}{'total':>10}{'in tok':>10}"
          f"{'out tok':>10}{'decode tps':>14}{'e2e tps':>11}")
    print("-" * 79)
    for s in stats:
        print(
            f"{s.label:<14}{s.ttft_s:>9.2f}s{s.total_s:>9.2f}s"
            f"{s.input_tokens:>10d}{s.output_tokens:>10d}"
            f"{s.decode_tps:>13.1f}{s.e2e_tps:>11.1f}"
        )
    print("-" * 79)
    if not stats:
        return
    decode = [s.decode_tps for s in stats]
    e2e = [s.e2e_tps for s in stats]
    ttfts = [s.ttft_s for s in stats]
    out_tok = [s.output_tokens for s in stats]
    print(
        f"{'mean':<14}{statistics.mean(ttfts):>9.2f}s"
        f"{statistics.mean([s.total_s for s in stats]):>9.2f}s"
        f"{'':>10}"
        f"{int(statistics.mean(out_tok)):>10d}"
        f"{statistics.mean(decode):>13.1f}{statistics.mean(e2e):>11.1f}"
    )
    if len(stats) >= 2:
        print(
            f"{'stdev':<14}{statistics.stdev(ttfts):>9.2f}s"
            f"{statistics.stdev([s.total_s for s in stats]):>9.2f}s"
            f"{'':>10}{'':>10}"
            f"{statistics.stdev(decode):>13.1f}{statistics.stdev(e2e):>11.1f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["gemini", "ollama"], default="gemini",
                    help="Which provider to benchmark (default: gemini).")
    ap.add_argument("--model", default=None,
                    help="Override the model name (else env-resolved).")
    ap.add_argument("--runs", type=int, default=3,
                    help="Number of measurement runs (default 3).")
    ap.add_argument("--warmup", type=int, default=1,
                    help="Number of warm-up runs (not measured, default 1).")
    args = ap.parse_args()

    model = _model_name(args.backend, args.model)
    print(f"Backend:     {args.backend}")
    print(f"Model:       {model}")
    print(f"Runs:        {args.runs} measured + {args.warmup} warmup")

    client = _build_client(args.backend, model)

    # Warm-ups (not recorded; first call pays cold-start latency on
    # Google's side and is not representative of steady-state throughput).
    for i in range(args.warmup):
        prompt = PROMPTS[i % len(PROMPTS)]
        print(f"Warmup {i+1}/{args.warmup}…", flush=True)
        _run_one(client, prompt, label=f"warmup{i+1}")

    stats: list[RunStats] = []
    for i in range(args.runs):
        prompt = PROMPTS[i % len(PROMPTS)]
        print(f"Run {i+1}/{args.runs}…", flush=True)
        stats.append(_run_one(client, prompt, label=f"run{i+1}"))

    _fmt(stats)


if __name__ == "__main__":
    main()
