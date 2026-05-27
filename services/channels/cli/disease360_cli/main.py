"""`disease360` CLI — spawn-and-exit per command."""

from __future__ import annotations

import httpx
import typer
from disease360_runtime.config import get
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import state

app = typer.Typer(help="Disease360 — Bruno's personal AI.", no_args_is_help=True)

console = Console()


def _harness_url() -> str:
    return get("DISEASE360_HARNESS_URL", "http://127.0.0.1:8002") or "http://127.0.0.1:8002"


def _memory_url() -> str:
    return get("DISEASE360_MEMORY_URL", "http://127.0.0.1:8001") or "http://127.0.0.1:8001"


@app.command()
def ask(
    message: str = typer.Argument(..., help="Question or instruction for Disease360."),
    brain: str | None = typer.Option(None, "--brain", "-b", help="Override active brain."),
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Override active tenant."),
    profile: str = typer.Option("chat", "--profile", "-p", help="chat | local | private"),
) -> None:
    """Send a one-shot message to Disease360."""
    s = state.load()
    active_brain = brain or s["active_brain"]
    active_tenant = tenant or s.get("tenant_id") or "local"
    thread_id = s.get("thread_id")
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                f"{_harness_url()}/chat",
                json={
                    "message": message,
                    "brain": active_brain,
                    "tenant_id": active_tenant,
                    "thread_id": thread_id,
                    "profile": profile,
                },
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        console.print(f"[red]harness unreachable:[/red] {e}")
        raise typer.Exit(2) from e

    s["thread_id"] = data["thread_id"]
    state.save(s)

    if data.get("final_text"):
        console.print(Panel(data["final_text"], title="Disease360", border_style="cyan"))


@app.command()
def status() -> None:
    """Show backend health."""
    rows = []
    for name, url in (("memory", _memory_url()), ("harness", _harness_url())):
        try:
            with httpx.Client(timeout=2.0) as c:
                r = c.get(f"{url}/healthz")
                rows.append((name, "ok" if r.status_code == 200 else f"http {r.status_code}"))
        except Exception as e:
            rows.append((name, f"down ({type(e).__name__})"))

    s = state.load()
    t = Table(show_header=False, box=None)
    for name, st in rows:
        t.add_row(name, st)
    t.add_row("active brain", s["active_brain"])
    t.add_row("thread", s.get("thread_id") or "(new)")
    console.print(t)


@app.command()
def brains() -> None:
    """List available brains for the active tenant."""
    s = state.load()
    tenant = s.get("tenant_id") or "local"
    try:
        with httpx.Client(timeout=5.0) as c:
            data = c.get(f"{_memory_url()}/tenant/{tenant}/brains").json()
    except httpx.HTTPError as e:
        console.print(f"[red]memory unreachable:[/red] {e}")
        raise typer.Exit(2) from e
    s = state.load()
    t = Table(title="Brains")
    t.add_column("active")
    t.add_column("id")
    t.add_column("pages")
    t.add_column("hot?")
    for b in data:
        t.add_row(
            "*" if b["id"] == s["active_brain"] else "",
            b["id"],
            str(b["page_count"]),
            "y" if b["has_hot"] else "n",
        )
    console.print(t)


@app.command()
def switch(brain: str = typer.Argument(...)) -> None:
    """Set the active brain for subsequent `disease360 ask` calls."""
    s = state.load()
    s["active_brain"] = brain
    s["thread_id"] = None  # new conversation thread
    state.save(s)
    console.print(f"active brain → [bold]{brain}[/bold]")


@app.command()
def tenant(tenant_id: str = typer.Argument(...)) -> None:
    """Set the active tenant for subsequent `disease360 ask` calls."""
    s = state.load()
    s["tenant_id"] = tenant_id
    s["thread_id"] = None
    state.save(s)
    console.print(f"active tenant → [bold]{tenant_id}[/bold]")
