# NemoClaw (NVIDIA)

> Open-source security wrapper around OpenClaw. **Apache 2.0**, 19.8K stars, 2.5K forks.
> First released **March 16, 2026 — alpha**, announced at NVIDIA GTC 2026.
> Repo: [`github.com/NVIDIA/NemoClaw`](https://github.com/NVIDIA/NemoClaw) · Docs: `docs.nvidia.com/nemoclaw/latest/`

## What it is — and isn't

**NemoClaw is *not* a replacement for OpenClaw.** You still need OpenClaw underneath — NemoClaw wraps it.

Internal NVIDIA framing:
> *"OpenClaw is the assistant. NemoClaw is the blast shield around it."*

The problem: OpenClaw has shell access, file access, network access, credentials. If the LLM hallucinates `rm -rf /`, OpenClaw has no kernel-level reason not to do it. NemoClaw fixes that.

## Stack

```
┌──────────────────────────────────────┐
│  OpenClaw            (the assistant) │  ← messaging, skills, agent behavior
├──────────────────────────────────────┤
│  NemoClaw Blueprint  (orchestration) │  ← versioned Python artifact
│                                      │     creates sandbox, applies policies
├──────────────────────────────────────┤
│  OpenShell Runtime  (the sandbox)    │  ← kernel-level isolation
├──────────────────────────────────────┤
│  Nemotron / Inference                │  ← model backend
└──────────────────────────────────────┘
```

NemoClaw is part of **NVIDIA Agent Toolkit**. It installs a *fresh* OpenClaw inside the sandbox during onboarding — it cannot wrap an existing OpenClaw setup (yet).

## The four policy layers

This is the meat of the value proposition.

| Layer | What it enforces | How |
|---|---|---|
| **Filesystem** | Reads/writes restricted to `/sandbox` and `/tmp` only | **Landlock** (Linux 5.13+) — kernel-enforced, not config-flag |
| **Network** | Default-deny outbound; explicit YAML allowlist; interactive approval TUI | **Network namespaces + L7 HTTP enforcement** — granular, "GET to API X yes, POST no" |
| **Process** | Privilege escalation & dangerous syscalls blocked | **seccomp** syscall filtering |
| **Inference** | API calls routed through OpenShell; agent never sees raw API keys | OpenShell intercepts → strips caller creds → injects backend creds |

**Key UX moment**: when the agent tries to hit a new endpoint, a **k9s-style TUI** pops up asking the operator to approve or deny in real time. Session-scoped or permanent.

## Install (Linux primary)

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
nemoclaw onboard            # guided wizard
nemoclaw connect            # shell into the sandbox
openclaw tui                # OpenClaw inside the sandbox
```

macOS (Apple Silicon, with Docker Desktop or Colima) and Windows WSL2 are also supported but with limitations.

## Hardware requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 4 vCPU | 4+ vCPU |
| RAM | **8 GB** (will OOM during install if less) | 16 GB |
| Disk | 20 GB free | 40 GB free |

The sandbox image alone is ~2.4 GB compressed. Docker, k3s, and the OpenShell gateway all run during setup.

Default model: `nvidia/nemotron-3-super-120b-a12b` (NVIDIA Endpoints, requires API key from build.nvidia.com — separate from your normal NVIDIA account). Local inference paths via Ollama / vLLM are *experimental*.

## NemoClaw vs native OpenClaw — when to use which

| | Native OpenClaw | NemoClaw + OpenClaw |
|---|---|---|
| **Best for** | Personal assistant on your trusted device | Enterprise, shared environments, governance |
| **Security** | Process-level, depends on host | Kernel-level (Landlock + seccomp + netns) |
| **Networking** | Unrestricted by default | Default-deny + interactive approval |
| **Filesystem** | Full host (scoped by config) | Locked to `/sandbox` + `/tmp` |
| **Model flexibility** | Any provider | Nemotron primary; Ollama/vLLM experimental |
| **Setup** | `npm install` | Docker + OpenShell + onboard wizard |
| **Maturity** | Stable | Alpha (interfaces may break) |
| **Resource overhead** | Minimal | ~2.4 GB image + k3s overhead |

## What's relevant to *us* (single-user JARVIS on Bruno's machine)

You are arguably *not* in NemoClaw's primary target audience right now (it's positioned at enterprise + multi-user shared environments, and it's alpha software). But its security model is the right one to copy.

**Patterns we should adopt even if we don't run NemoClaw itself:**

1. **Default-deny networking** — every external host the agent contacts should be on an allowlist.
2. **Interactive approval for "spending" or "irreversible" actions** — sending email, posting publicly, paying money, deleting files.
3. **Credential stripping** — the LLM should *never* see raw API keys. Inject them at the proxy layer.
4. **Filesystem scoping** — the agent gets a `~/.jarvis/sandbox/` workspace, not `/`.
5. **Audit log** — every tool call written to `log.md` with timestamp + result (Karpathy already recommends this for the wiki layer; we extend it to actions).

When NemoClaw goes stable (probably late 2026 / 2027), we can wrap our agent in it for free.

## Limitations (acknowledged by NVIDIA)

- **Alpha software**, breaking changes expected.
- **macOS Podman not supported** (only Docker / Colima).
- **8 GB RAM hard floor**.
- **Linux-centric** — Ubuntu 22.04+ primary.
- **Single-tenant only** — no multi-user yet.
- **OpenShell itself is described by NVIDIA as "proof-of-life" software.**
- Cannot wrap an existing OpenClaw setup; creates a fresh one.

## Sources

- Repo: <https://github.com/NVIDIA/NemoClaw>
- Site: <https://nemoclawai.io/> (community)
- Docs: <https://docs.nvidia.com/nemoclaw/latest/>
- Walkthroughs: *neuralstackly.com* ("NVIDIA NemoClaw: Complete Guide", 2026-03-22), *ico-optics.org* ("Secure Always-On Local AI Agent with NVIDIA NemoClaw and OpenClaw", 2026-04-18), NVIDIA developer blog.
