"""Extensive throughput benchmark for an Ollama-hosted model.

Hits Ollama's raw streaming `/api/chat` so we can capture both:

  - Wall-clock metrics (what the user feels):
      TTFT, total wall time, decode tps = output_tokens / (total - TTFT)
  - Ollama's internal counters (what the model actually does, network-free):
      prompt_eval_count, prompt_eval_duration_ns
      eval_count,        eval_duration_ns
      load_duration_ns,  total_duration_ns

Several scenarios sweep over short / medium / long output sizes and small /
large input contexts so we can see how decode tps degrades as the KV cache
fills, and how prompt-processing rate compares to decode rate.

A markdown report is written to docs/benchmarks/<model>-<timestamp>.md.

Usage:
    python scripts/bench_ollama_deep.py
    python scripts/bench_ollama_deep.py --model gemma4:e4b --trials 10
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "runtime"))

from kairos_runtime import config  # noqa: E402

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
# Each scenario is (id, label, system_prompt, user_prompt, num_predict).
# `num_predict` is forwarded to Ollama as a soft cap on the output length;
# the model often stops sooner if it naturally finishes the answer.

SHORT_OUTPUT = 120
MEDIUM_OUTPUT = 500
LONG_OUTPUT = 1500

# A ~4k-token preamble built by repeating a chunk of plausible "second-brain"
# context. We pre-render it once so every long-context trial gets the same
# input and per-trial variance reflects model state rather than input drift.
_LONG_CONTEXT_BLOCK = (
    "Bruno is building Kairos, a personal AI cockpit that fuses a markdown "
    "second brain, a voice-first dashboard, and an approval-gated harness. "
    "The cloud profile uses Gemini 3 Flash; the private/offline profile uses "
    "Gemma 3 E4B via Ollama on the same machine. Each brain is a folder of "
    "wiki-linked markdown notes with a hot cache, an index, and a raw capture "
    "stream. The graph viewer renders a force-directed layout of every page; "
    "the lint endpoint surfaces orphans, sparse pages, and broken wikilinks. "
    "Approvals are mandatory for every mutating tool. The route flyover on the "
    "dashboard interpolates a smooth Chaikin-and-Gaussian-blurred camera path "
    "over the raw ORS polyline so the camera anticipates corners well before "
    "reaching them. Voice STT and TTS both go through Gemini's 3.1 preview "
    "models; the chat agent runs through LangChain 1.x with Deep Agents on "
    "top of LangGraph, persisted via langgraph-checkpoint-sqlite. The harness "
    "exposes a FastAPI surface on :8002, the memory service on :8001, and the "
    "Vite dev server on :5173. "
)
LONG_CONTEXT = (_LONG_CONTEXT_BLOCK * 12).strip()  # ~4k tokens

SCENARIOS: list[tuple[str, str, str, str, int]] = [
    (
        "short",
        "short reply (~100 tokens, small context)",
        "You are a precise technical writer.",
        "In one short paragraph (about 80-100 words), explain why decode in "
        "transformer inference is memory-bandwidth-bound rather than "
        "compute-bound.",
        SHORT_OUTPUT,
    ),
    (
        "medium",
        "medium reply (~400 tokens, small context)",
        "You are a precise technical writer.",
        "Write about 300 words explaining how a transformer language model "
        "generates text token-by-token at inference time. Cover the KV-cache, "
        "sampling temperature, and why decode is memory-bandwidth-bound.",
        MEDIUM_OUTPUT,
    ),
    (
        "long",
        "long reply (~1500 tokens, small context)",
        "You are a precise technical writer.",
        "Write a thorough ~1200 word essay comparing cloud-hosted frontier "
        "language models with locally run small-to-medium models for a "
        "single user's personal AI cockpit. Cover latency, privacy, cost, "
        "capability, failure modes, and integration patterns. Use clear "
        "sections.",
        LONG_OUTPUT,
    ),
    (
        "long_ctx_short_out",
        "long context (~4k tokens) -> short reply (~150 tokens)",
        f"You are an assistant with the following context:\n\n{LONG_CONTEXT}",
        "Given the context above, summarise in about 100 words what Kairos's "
        "private/offline profile is for and how it differs from the cloud "
        "profile.",
        SHORT_OUTPUT,
    ),
    (
        "long_ctx_long_out",
        "long context (~4k tokens) -> long reply (~1500 tokens)",
        f"You are an assistant with the following context:\n\n{LONG_CONTEXT}",
        "Using the context above, write a detailed ~1200 word architectural "
        "overview of Kairos. Cover the harness, memory service, voice path, "
        "dashboard, and approvals model, and call out where the private "
        "Ollama profile would be preferred over the cloud one.",
        LONG_OUTPUT,
    ),
]


# ---------------------------------------------------------------------------
# Stats container
# ---------------------------------------------------------------------------


# Below this many seconds between TTFT and end-of-stream, the wall-clock
# decode rate is dominated by I/O buffer flush boundaries (we received
# multiple model tokens in a single httpx chunk) rather than by actual
# streaming throughput. Ollama tends to do this on short outputs where
# the whole response fits in one TCP write. We mark those trials' wall-
# clock decode rate as unreliable and exclude them from aggregates.
WALL_DECODE_MIN_DELTA_S = 0.05


@dataclass
class TrialStats:
    scenario_id: str
    trial: int
    ttft_s: float
    total_s: float
    # From Ollama's `done: true` JSON.
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0
    eval_count: int = 0
    eval_duration_ns: int = 0
    load_duration_ns: int = 0
    total_duration_ns: int = 0
    # Output text length in characters (sanity check).
    response_chars: int = 0

    @property
    def wall_decode_unreliable(self) -> bool:
        return (self.total_s - self.ttft_s) < WALL_DECODE_MIN_DELTA_S

    @property
    def decode_tps_wall(self) -> float:
        if self.wall_decode_unreliable:
            return float("nan")
        decode = max(self.total_s - self.ttft_s, 1e-9)
        return self.eval_count / decode

    @property
    def decode_tps_model(self) -> float:
        if self.eval_duration_ns <= 0:
            return 0.0
        return self.eval_count / (self.eval_duration_ns / 1e9)

    @property
    def prompt_tps_model(self) -> float:
        if self.prompt_eval_duration_ns <= 0:
            return 0.0
        return self.prompt_eval_count / (self.prompt_eval_duration_ns / 1e9)

    @property
    def e2e_tps_wall(self) -> float:
        return self.eval_count / max(self.total_s, 1e-9)


@dataclass
class ScenarioStats:
    scenario_id: str
    label: str
    trials: list[TrialStats] = field(default_factory=list)

    def summary(self, attr: str) -> dict[str, float]:
        raw = [getattr(t, attr) for t in self.trials]
        # Drop NaNs so an unreliable wall-clock decode rate doesn't poison
        # the aggregate stats. A NaN-only column collapses to all-zeros.
        vals = [v for v in raw if isinstance(v, (int, float)) and v == v]
        if not vals:
            return {"mean": 0, "p50": 0, "p95": 0, "stdev": 0, "min": 0, "max": 0}
        sorted_vals = sorted(vals)

        def pct(p: float) -> float:
            if not sorted_vals:
                return 0.0
            k = (len(sorted_vals) - 1) * p
            f = int(k)
            c = min(f + 1, len(sorted_vals) - 1)
            if f == c:
                return sorted_vals[f]
            return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

        return {
            "mean": statistics.mean(vals),
            "p50": pct(0.50),
            "p95": pct(0.95),
            "stdev": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "min": min(vals),
            "max": max(vals),
        }


# ---------------------------------------------------------------------------
# Ollama streaming runner
# ---------------------------------------------------------------------------


def _run_trial(
    *,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    num_predict: int,
    scenario_id: str,
    trial: int,
    timeout_s: float,
) -> TrialStats:
    """Stream one chat turn and capture timing + Ollama counters."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_predict": num_predict,
        },
    }

    stats = TrialStats(scenario_id=scenario_id, trial=trial, ttft_s=0.0, total_s=0.0)
    response_chars = 0

    start = time.perf_counter()
    ttft_seen = False
    with httpx.stream(
        "POST",
        f"{base_url}/api/chat",
        json=payload,
        timeout=timeout_s,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") or {}
            content = msg.get("content") or ""
            if content and not ttft_seen:
                stats.ttft_s = time.perf_counter() - start
                ttft_seen = True
            if content:
                response_chars += len(content)
            if obj.get("done"):
                stats.prompt_eval_count = int(obj.get("prompt_eval_count") or 0)
                stats.prompt_eval_duration_ns = int(
                    obj.get("prompt_eval_duration") or 0
                )
                stats.eval_count = int(obj.get("eval_count") or 0)
                stats.eval_duration_ns = int(obj.get("eval_duration") or 0)
                stats.load_duration_ns = int(obj.get("load_duration") or 0)
                stats.total_duration_ns = int(obj.get("total_duration") or 0)
                break
    stats.total_s = time.perf_counter() - start
    if not ttft_seen:
        stats.ttft_s = stats.total_s
    stats.response_chars = response_chars
    return stats


# ---------------------------------------------------------------------------
# Pretty printing for live console output
# ---------------------------------------------------------------------------


def _print_trial(t: TrialStats) -> None:
    wall = (
        f"{t.decode_tps_wall:6.1f}" if not t.wall_decode_unreliable else "  n/a "
    )
    print(
        f"  trial {t.trial:>2}  "
        f"ttft={t.ttft_s:5.2f}s  total={t.total_s:6.2f}s  "
        f"in={t.prompt_eval_count:>5}  out={t.eval_count:>5}  "
        f"decode={wall} tps "
        f"(model={t.decode_tps_model:6.1f}, "
        f"prompt={t.prompt_tps_model:7.1f})",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _fmt(value: float, kind: str = "n") -> str:
    if kind == "s":
        return f"{value:.2f}s"
    if kind == "tps":
        return f"{value:.1f}"
    if kind == "int":
        return f"{int(round(value))}"
    return f"{value:.2f}"


def _scenario_summary_row(s: ScenarioStats) -> str:
    out = s.summary("eval_count")
    in_ = s.summary("prompt_eval_count")
    ttft = s.summary("ttft_s")
    total = s.summary("total_s")
    dec_w = s.summary("decode_tps_wall")
    dec_m = s.summary("decode_tps_model")
    prm_m = s.summary("prompt_tps_model")
    return (
        f"| {s.label} "
        f"| {_fmt(in_['mean'], 'int')} "
        f"| {_fmt(out['mean'], 'int')} "
        f"| {_fmt(ttft['p50'], 's')} "
        f"| {_fmt(total['p50'], 's')} "
        f"| {_fmt(dec_w['p50'], 'tps')} "
        f"| {_fmt(dec_m['p50'], 'tps')} "
        f"| {_fmt(prm_m['p50'], 'tps')} "
        f"|"
    )


def _scenario_detail(s: ScenarioStats) -> str:
    lines: list[str] = []
    lines.append(f"### {s.label}")
    lines.append("")
    lines.append(
        "| trial | ttft | total | in tok | out tok | decode tps (wall) | "
        "decode tps (model) | prompt tps (model) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for t in s.trials:
        wall = "n/a" if t.wall_decode_unreliable else _fmt(t.decode_tps_wall, 'tps')
        lines.append(
            f"| {t.trial} "
            f"| {_fmt(t.ttft_s, 's')} "
            f"| {_fmt(t.total_s, 's')} "
            f"| {t.prompt_eval_count} "
            f"| {t.eval_count} "
            f"| {wall} "
            f"| {_fmt(t.decode_tps_model, 'tps')} "
            f"| {_fmt(t.prompt_tps_model, 'tps')} |"
        )

    def _stat_row(name: str, attr: str, kind: str) -> str:
        st = s.summary(attr)
        return (
            f"| **{name}** "
            f"| mean {_fmt(st['mean'], kind)} "
            f"| p50 {_fmt(st['p50'], kind)} "
            f"| p95 {_fmt(st['p95'], kind)} "
            f"| stdev {_fmt(st['stdev'], kind)} "
            f"| min {_fmt(st['min'], kind)} "
            f"| max {_fmt(st['max'], kind)} |"
        )

    lines.append("")
    lines.append("| metric | mean | p50 | p95 | stdev | min | max |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.append(_stat_row("ttft (s)", "ttft_s", "s"))
    lines.append(_stat_row("total (s)", "total_s", "s"))
    lines.append(_stat_row("decode tps (wall)", "decode_tps_wall", "tps"))
    lines.append(_stat_row("decode tps (model)", "decode_tps_model", "tps"))
    lines.append(_stat_row("prompt tps (model)", "prompt_tps_model", "tps"))
    lines.append("")
    return "\n".join(lines)


def _hardware_block() -> str:
    lines = [
        f"- **Host:** {socket.gethostname()}",
        f"- **OS:** {platform.system()} {platform.release()} ({platform.version()})",
        f"- **Machine:** {platform.machine()}",
        f"- **Processor:** {platform.processor() or 'n/a'}",
        f"- **Python:** {platform.python_version()}",
    ]
    return "\n".join(lines)


def _build_report(
    *,
    model: str,
    base_url: str,
    trials: int,
    warmup: int,
    started_at: str,
    finished_at: str,
    duration_s: float,
    scenarios: list[ScenarioStats],
) -> str:
    parts: list[str] = []
    parts.append(f"# {model} — Throughput benchmark")
    parts.append("")
    parts.append(f"**Generated:** {started_at} (took {duration_s:.1f}s)")
    parts.append("")
    parts.append("## Setup")
    parts.append("")
    parts.append(f"- **Backend:** Ollama at `{base_url}`")
    parts.append(f"- **Model:** `{model}`")
    parts.append(f"- **Trials per scenario:** {trials}  (+ {warmup} warmup, not recorded)")
    parts.append(f"- **Scenarios:** {len(scenarios)}")
    parts.append(f"- **Started:** {started_at}")
    parts.append(f"- **Finished:** {finished_at}")
    parts.append("")
    parts.append("### Hardware")
    parts.append("")
    parts.append(_hardware_block())
    parts.append("")
    parts.append("## Methodology")
    parts.append("")
    parts.append(
        "Each trial hits Ollama's raw `/api/chat` endpoint with `stream: true` "
        "so we can pick up both wall-clock latency and the model's internal "
        "counters (`prompt_eval_count`, `prompt_eval_duration`, `eval_count`, "
        "`eval_duration`) from the final `done: true` chunk. **Decode tps "
        "(wall)** divides Ollama's `eval_count` by `(total - TTFT)` — what "
        "the user feels, including network/IPC overhead. **Decode tps "
        "(model)** uses Ollama's own `eval_duration` — the model's pure "
        "decode rate net of any host-side noise. **Prompt tps (model)** is "
        "Ollama's prompt-eval rate, measured against `prompt_eval_duration`."
    )
    parts.append("")
    parts.append(
        f"On short outputs Ollama sometimes flushes the entire response in a "
        f"single TCP write, which makes `(total - ttft)` collapse to a few "
        f"milliseconds and the wall-clock decode rate meaningless. Trials "
        f"where this happened (delta < {WALL_DECODE_MIN_DELTA_S * 1000:.0f} ms) "
        f"show `n/a` for **decode tps (wall)** and are excluded from that "
        f"column's aggregates; the model-reported rate is still trustworthy "
        f"for those trials."
    )
    parts.append("")
    parts.append(
        "A single warmup call at the start of the run pays the model-load "
        "cost so the recorded trials reflect steady-state throughput. "
        "Temperature is fixed at 0.2; `num_predict` caps the output length "
        "but the model often stops sooner."
    )
    parts.append("")
    parts.append("## Headline (p50 across trials)")
    parts.append("")
    parts.append(
        "| scenario | in tok (mean) | out tok (mean) | ttft p50 | total p50 "
        "| decode tps (wall) | decode tps (model) | prompt tps |"
    )
    parts.append("|---|---|---|---|---|---|---|---|")
    for s in scenarios:
        parts.append(_scenario_summary_row(s))
    parts.append("")
    parts.append("## Per-scenario detail")
    parts.append("")
    for s in scenarios:
        parts.append(_scenario_detail(s))

    parts.append("## Reading the numbers")
    parts.append("")
    parts.append(
        "- **TTFT** is dominated by model state (cache hot vs cold) and prompt-"
        "eval time on long contexts. Compare TTFT across the small-context "
        "and 4k-context scenarios to see how prompt-eval scales."
    )
    parts.append(
        "- **Decode tps (wall) vs (model)** — the gap is the host-side "
        "overhead: Ollama IPC, HTTP framing, Python receive loop. A small "
        "gap means the bottleneck is the model itself."
    )
    parts.append(
        "- **Decode tps drift across long outputs** — if decode tps falls "
        "as `eval_count` grows, the KV cache is starting to hurt; flat lines "
        "mean the model is bandwidth-bound at full speed regardless of "
        "context size."
    )
    parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None,
                    help="Ollama model tag (else env-resolved).")
    ap.add_argument("--trials", type=int, default=10,
                    help="Trials per scenario (default 10).")
    ap.add_argument("--warmup", type=int, default=1,
                    help="Warmup runs before measurement (default 1).")
    ap.add_argument("--scenarios", nargs="*", default=None,
                    help="Subset of scenario ids to run.")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="HTTP read timeout per trial, seconds (default 600).")
    ap.add_argument("--out", default=None,
                    help="Output markdown path (default: docs/benchmarks/<model>-<timestamp>.md).")
    args = ap.parse_args()

    base_url = config.get("OLLAMA_HOST", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"
    model = args.model or config.get("OLLAMA_DEFAULT_MODEL", "gemma4:e4b") or "gemma4:e4b"

    scenarios_to_run = SCENARIOS
    if args.scenarios:
        wanted = set(args.scenarios)
        scenarios_to_run = [s for s in SCENARIOS if s[0] in wanted]
        if not scenarios_to_run:
            raise SystemExit(f"No scenarios match {wanted}")

    print(f"Backend:  {base_url}")
    print(f"Model:    {model}")
    print(f"Trials:   {args.trials} per scenario  ({args.warmup} warmup)")
    print(f"Scenarios:")
    for sid, label, *_ in scenarios_to_run:
        print(f"  - {sid:<22} {label}")
    print()

    started_at_dt = datetime.now()
    started_at = started_at_dt.strftime("%Y-%m-%d %H:%M:%S")
    t_start = time.perf_counter()

    # Warmup against the first scenario so the model loads into memory.
    if args.warmup > 0:
        sid, label, sysp, usrp, npred = scenarios_to_run[0]
        for w in range(args.warmup):
            print(f"warmup {w+1}/{args.warmup} ({sid})…", flush=True)
            _run_trial(
                base_url=base_url,
                model=model,
                system_prompt=sysp,
                user_prompt=usrp,
                num_predict=min(npred, 80),
                scenario_id="warmup",
                trial=w + 1,
                timeout_s=args.timeout,
            )

    results: list[ScenarioStats] = []
    for sid, label, sysp, usrp, npred in scenarios_to_run:
        print(f"\n=== {sid}: {label} ===")
        ss = ScenarioStats(scenario_id=sid, label=label)
        for i in range(args.trials):
            t = _run_trial(
                base_url=base_url,
                model=model,
                system_prompt=sysp,
                user_prompt=usrp,
                num_predict=npred,
                scenario_id=sid,
                trial=i + 1,
                timeout_s=args.timeout,
            )
            ss.trials.append(t)
            _print_trial(t)
        results.append(ss)

    finished_at_dt = datetime.now()
    finished_at = finished_at_dt.strftime("%Y-%m-%d %H:%M:%S")
    duration_s = time.perf_counter() - t_start

    report = _build_report(
        model=model,
        base_url=base_url,
        trials=args.trials,
        warmup=args.warmup,
        started_at=started_at,
        finished_at=finished_at,
        duration_s=duration_s,
        scenarios=results,
    )

    if args.out:
        out_path = Path(args.out).resolve()
    else:
        slug = model.replace(":", "-").replace("/", "-")
        ts = started_at_dt.strftime("%Y%m%d-%H%M%S")
        out_path = ROOT / "docs" / "benchmarks" / f"{slug}-{ts}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
