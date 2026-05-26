# Runtime service

LLM client layer. **Locked**: LangChain 1.0 + Deep Agents (the Deep Agents harness lives in [`../harness/`](../harness/)). This service exposes the model factory used everywhere.

## What lives here

- `kairos_runtime/llm.py` — `get_chat_model(profile: str) -> BaseChatModel`. Profiles:
  - `"chat"` (default) → Gemini via `langchain-google-genai`. Model = `KAIROS_MODEL_OVERRIDE` or `GEMINI_DEFAULT_MODEL` (default `gemini-flash-latest`).
  - `"local"` → Ollama via `langchain-ollama`. Model = `OLLAMA_DEFAULT_MODEL` (default `gemma4:4b`).
  - `"private"` → alias for `"local"`. Used when SOUL principle #4 fires (health/finance/intimate).
- `kairos_runtime/config.py` — env loader (reads `policies/secrets.env` + process env).

## Why LangChain + Deep Agents

Long-running, persistent memory across sessions, files-as-state, sub-agents per skill, HumanInTheLoop interrupts — all match Deep Agents' middleware bundle. See [docs/06-jarvis-architecture-proposal.md](../../docs/06-jarvis-architecture-proposal.md).

## Deps

- `langchain>=1.0,<2`, `langchain-core>=1.0,<2`, `deepagents`, `langgraph`, `langsmith>=0.3`, `langchain-google-genai`, `langchain-ollama`, `python-dotenv`.

Status: **scaffolded — implement in Phase 1**.
