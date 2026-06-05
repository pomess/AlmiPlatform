"""LLM client factory.

Profiles:
    chat     -> Gemini via langchain-google-genai (cloud)
    local    -> Ollama via langchain-ollama       (private/offline fallback)
    private  -> alias for `local` (used for health/finance/intimate context)
"""

from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from . import config

Profile = Literal["chat", "local", "private"]


def get_chat_model(
    profile: Profile = "chat",
    *,
    temperature: float = 0.2,
    cached_content: str | None = None,
) -> BaseChatModel:
    """Build a chat model for the given profile.

    `cached_content`, when provided, is forwarded to the Gemini wrapper
    so requests reference an existing context cache instead of resending
    the full system prompt + tool schemas every turn. See
    `atlas_runtime.prompt_cache` for the caching policy.
    """
    if profile == "chat":
        return _gemini(temperature=temperature, cached_content=cached_content)
    if profile in ("local", "private"):
        return _ollama(temperature=temperature)
    raise ValueError(f"Unknown profile: {profile!r}")


def _gemini(*, temperature: float, cached_content: str | None = None) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = config.require("GOOGLE_API_KEY")
    model = config.get("DISEASE360_MODEL_OVERRIDE") or config.get(
        "GEMINI_DEFAULT_MODEL", "gemini-flash-latest"
    )
    kwargs: dict = {
        "model": model,
        "google_api_key": api_key,
        "temperature": temperature,
        "timeout": 90,
    }
    if cached_content:
        # When a context cache is bound, the wrapper sends only the new
        # user turn + the cache reference -- the system prompt and any
        # cached tools live in the cache, not the request body.
        kwargs["cached_content"] = cached_content
    return ChatGoogleGenerativeAI(**kwargs)


def _ollama(*, temperature: float) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=config.get("OLLAMA_DEFAULT_MODEL", "gemma4:4b"),
        base_url=config.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        temperature=temperature,
    )
