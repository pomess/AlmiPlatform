# Launch all Kairos services in one terminal.
# Usage:  .\run.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Activate venv if present (so `python` and console-scripts resolve).
$activate = Join-Path $root ".venv\Scripts\Activate.ps1"
if (Test-Path $activate) { . $activate }

# Prefer `uv run` (matches how you've been launching the services), fall back to python.
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv run python scripts\run.py @args
} else {
    python scripts\run.py @args
}
