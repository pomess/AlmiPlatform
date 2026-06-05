"""Disease360 Atlas — Unified FastAPI application.

Single process serving:
  - Static files (React build) at /
  - Memory API at /api/memory/*
  - Harness API at /api/harness/*

In Databricks Apps: binds to 0.0.0.0:DATABRICKS_APP_PORT.
In local dev: runs memory on :8001, harness on :8002 separately (via run.ps1).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from atlas_memory.main import app as memory_app
from atlas_harness.api import app as harness_app

app = FastAPI(title="Disease360 Atlas", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "atlas-unified"}


# Mount sub-applications
app.mount("/api/memory", memory_app)
app.mount("/api/harness", harness_app)

# Serve static files (React build output) at root — must be mounted LAST
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    """Entry point for Databricks Apps and local unified mode."""
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", os.environ.get("ATLAS_PORT", "8000")))
    host = "0.0.0.0"
    uvicorn.run("atlas_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
