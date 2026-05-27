"""Launch all Disease360 services in one terminal.

Starts:
  - disease360_memory   (FastAPI)  http://127.0.0.1:8001
  - disease360_harness  (FastAPI)  http://127.0.0.1:8002
  - apps/web        (Vite)     http://127.0.0.1:5173

Output from every process is streamed to this terminal with a colored prefix.
Press Ctrl+C once to shut everything down cleanly.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "apps" / "web"

# ANSI colors (Windows 10+ terminals support these).
COLORS = {
    "memory":  "\033[36m",  # cyan
    "harness": "\033[35m",  # magenta
    "web":     "\033[33m",  # yellow
    "sys":     "\033[32m",  # green
}
RESET = "\033[0m"


def _say(tag: str, msg: str) -> None:
    color = COLORS.get(tag, "")
    print(f"{color}[{tag:>7}]{RESET} {msg}", flush=True)


def _stream(tag: str, proc: subprocess.Popen) -> None:
    color = COLORS.get(tag, "")
    prefix = f"{color}[{tag:>7}]{RESET} "
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if line:
            print(prefix + line, flush=True)


def _spawn(tag: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    _say("sys", f"starting {tag}: {' '.join(cmd)}  (cwd={cwd})")
    creationflags = 0
    if os.name == "nt":
        # New process group so we can deliver CTRL_BREAK to children only.
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=creationflags,
    )
    threading.Thread(target=_stream, args=(tag, proc), daemon=True).start()
    return proc


def _resolve_npm() -> str:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        _say("sys", "ERROR: npm not found on PATH. Install Node.js to run the web UI.")
        sys.exit(1)
    return npm


def _ensure_web_deps(npm: str) -> None:
    if not (WEB / "node_modules").exists():
        _say("sys", "apps/web/node_modules missing — running `npm install` once...")
        subprocess.check_call([npm, "install"], cwd=str(WEB))


def main() -> int:
    npm = _resolve_npm()
    _ensure_web_deps(npm)

    py = sys.executable
    # `-u` keeps child stdout unbuffered so logs stream live through our pipes.
    procs: dict[str, subprocess.Popen] = {}
    procs["memory"] = _spawn("memory",  [py, "-u", "-m", "disease360_memory.main"], ROOT)
    # Slight stagger so the harness can hit memory if it wants to on boot.
    time.sleep(0.5)
    procs["harness"] = _spawn("harness", [py, "-u", "-m", "disease360_harness.api"], ROOT)
    procs["web"] = _spawn("web", [npm, "run", "dev"], WEB)

    _say("sys", "all services launched. URLs:")
    _say("sys", "  memory   http://127.0.0.1:8001/healthz")
    _say("sys", "  harness  http://127.0.0.1:8002/healthz")
    _say("sys", "  web      http://127.0.0.1:5173")
    _say("sys", "press Ctrl+C to stop everything.")

    def _shutdown(*_: object) -> None:
        _say("sys", "shutting down...")
        for tag, p in procs.items():
            if p.poll() is not None:
                continue
            try:
                if os.name == "nt":
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    p.terminate()
            except Exception as e:  # pragma: no cover
                _say("sys", f"failed to signal {tag}: {e}")
        # Grace period, then hard kill stragglers.
        deadline = time.time() + 5
        for tag, p in procs.items():
            remaining = max(0.0, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _say("sys", f"force-killing {tag}")
                p.kill()
        _say("sys", "bye.")

    try:
        while True:
            time.sleep(0.5)
            for tag, p in procs.items():
                rc = p.poll()
                if rc is not None:
                    _say("sys", f"{tag} exited with code {rc} — shutting down siblings")
                    _shutdown()
                    return rc or 1
    except KeyboardInterrupt:
        _shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
