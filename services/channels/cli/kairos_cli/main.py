"""`kairos` CLI — spawn-and-exit per command."""

from __future__ import annotations

import json

import httpx
import typer
from kairos_runtime.config import get
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import state

app = typer.Typer(help="Kairos — Bruno's personal AI.", no_args_is_help=True)
approvals_app = typer.Typer(help="Manage pending approvals.", no_args_is_help=True)
app.add_typer(approvals_app, name="approvals")

console = Console()


def _harness_url() -> str:
    return get("KAIROS_HARNESS_URL", "http://127.0.0.1:8002") or "http://127.0.0.1:8002"


def _memory_url() -> str:
    return get("KAIROS_MEMORY_URL", "http://127.0.0.1:8001") or "http://127.0.0.1:8001"


@app.command()
def ask(
    message: str = typer.Argument(..., help="Question or instruction for Kairos."),
    brain: str | None = typer.Option(None, "--brain", "-b", help="Override active brain."),
    tenant: str | None = typer.Option(None, "--tenant", "-t", help="Override active tenant."),
    profile: str = typer.Option("chat", "--profile", "-p", help="chat | local | private"),
) -> None:
    """Send a one-shot message to Kairos."""
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
        console.print(Panel(data["final_text"], title="Kairos", border_style="cyan"))
    if data.get("interrupted"):
        console.print(
            f"[yellow]paused — {len(data['approvals'])} approval(s) pending. "
            f"Run [bold]kairos approvals list[/bold] to review.[/yellow]"
        )


@app.command()
def status() -> None:
    """Show backend health + pending approvals count."""
    rows = []
    for name, url in (("memory", _memory_url()), ("harness", _harness_url())):
        try:
            with httpx.Client(timeout=2.0) as c:
                r = c.get(f"{url}/healthz")
                rows.append((name, "ok" if r.status_code == 200 else f"http {r.status_code}"))
        except Exception as e:
            rows.append((name, f"down ({type(e).__name__})"))

    pending = "?"
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"{_harness_url()}/approvals", params={"status": "pending"})
            pending = str(len(r.json()))
    except Exception:
        pass

    s = state.load()
    t = Table(show_header=False, box=None)
    for name, st in rows:
        t.add_row(name, st)
    t.add_row("active brain", s["active_brain"])
    t.add_row("thread", s.get("thread_id") or "(new)")
    t.add_row("pending approvals", pending)
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
    """Set the active brain for subsequent `kairos ask` calls."""
    s = state.load()
    s["active_brain"] = brain
    s["thread_id"] = None  # new conversation thread
    state.save(s)
    console.print(f"active brain → [bold]{brain}[/bold]")


@app.command()
def tenant(tenant_id: str = typer.Argument(...)) -> None:
    """Set the active tenant for subsequent `kairos ask` calls."""
    s = state.load()
    s["tenant_id"] = tenant_id
    s["thread_id"] = None
    state.save(s)
    console.print(f"active tenant → [bold]{tenant_id}[/bold]")


@approvals_app.command("list")
def approvals_list(
    status: str = typer.Option("pending", "--status", "-s", help="pending|approved|denied|expired|dnd_held|all"),
) -> None:
    """List approval queue (reads SQLite directly via the harness)."""
    params = {} if status == "all" else {"status": status}
    try:
        with httpx.Client(timeout=2.0) as c:
            data = c.get(f"{_harness_url()}/approvals", params=params).json()
    except httpx.HTTPError as e:
        console.print(f"[red]harness unreachable:[/red] {e}")
        raise typer.Exit(2) from e

    if not data:
        console.print(f"[dim]no approvals matching status={status}[/dim]")
        return

    t = Table(title=f"Approvals ({status})")
    t.add_column("id", style="dim", overflow="fold")
    t.add_column("tool")
    t.add_column("status")
    t.add_column("created")
    t.add_column("args", overflow="fold")
    for a in data:
        t.add_row(
            a["id"][:8],
            a["tool"],
            a["status"],
            a["created_at"][:19],
            json.dumps(a["args"])[:80],
        )
    console.print(t)


@approvals_app.command("approve")
def approvals_approve(
    approval_id: str = typer.Argument(..., help="Full id or 8-char prefix."),
) -> None:
    """Approve a pending tool call. Resumes the paused agent."""
    full_id = _resolve_id(approval_id)
    try:
        with httpx.Client(timeout=120.0) as c:
            r = c.post(f"{_harness_url()}/approvals/{full_id}/approve", json={"by": "cli"})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        console.print(f"[red]approve failed:[/red] {e}")
        raise typer.Exit(2) from e

    console.print(f"[green]approved[/green] {full_id[:8]}")
    if data.get("final_text"):
        console.print(Panel(data["final_text"], title="Kairos", border_style="cyan"))


@approvals_app.command("deny")
def approvals_deny(
    approval_id: str = typer.Argument(...),
    feedback: str | None = typer.Option(None, "--feedback", "-f"),
) -> None:
    """Deny a pending tool call. Agent gets the feedback and resumes."""
    full_id = _resolve_id(approval_id)
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(
                f"{_harness_url()}/approvals/{full_id}/deny",
                json={"by": "cli", "feedback": feedback},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        console.print(f"[red]deny failed:[/red] {e}")
        raise typer.Exit(2) from e

    console.print(f"[red]denied[/red] {full_id[:8]}")
    if data.get("final_text"):
        console.print(Panel(data["final_text"], title="Kairos", border_style="cyan"))


def _resolve_id(prefix: str) -> str:
    """Allow short 8-char prefixes — lookup by listing all and matching."""
    if len(prefix) >= 32:
        return prefix
    try:
        with httpx.Client(timeout=2.0) as c:
            data = c.get(f"{_harness_url()}/approvals").json()
    except httpx.HTTPError as e:
        raise typer.Exit(f"harness unreachable: {e}") from e
    matches = [a["id"] for a in data if a["id"].startswith(prefix)]
    if len(matches) == 0:
        raise typer.Exit(f"no approval matches {prefix!r}")
    if len(matches) > 1:
        raise typer.Exit(f"ambiguous prefix {prefix!r} — matches {len(matches)} items")
    return matches[0]
