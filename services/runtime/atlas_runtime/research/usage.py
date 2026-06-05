"""Token-usage callback for the deep research pipeline.

Attach to any LangChain ``ChatGoogleGenerativeAI`` instance to record real
token usage to a shared ``TokenMeter`` keyed on stage name. Replaces the
hardcoded estimates that previously made the pipeline's budget meter fictional.

Used by classifier, brief, lead, subagents, verifier, synthesizer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler

if TYPE_CHECKING:
    from langchain_core.outputs import LLMResult


class _MeterLike(Protocol):
    def record(self, stage: str, tokens: int) -> None: ...


class UsageCallback(AsyncCallbackHandler):
    """Records ``total_tokens`` from each LLM response into a TokenMeter."""

    def __init__(self, meter: _MeterLike, stage: str) -> None:
        self._meter = meter
        self._stage = stage

    async def on_llm_end(
        self,
        response: "LLMResult",
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        total = _extract_total_tokens(response)
        if total:
            self._meter.record(self._stage, total)

    def on_llm_end_sync(
        self,
        response: "LLMResult",
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        total = _extract_total_tokens(response)
        if total:
            self._meter.record(self._stage, total)


def _extract_total_tokens(response: "LLMResult") -> int:
    """Pull total tokens from a langchain LLMResult.

    Gemini's ChatGoogleGenerativeAI puts usage in two places. The newer path is
    ``message.usage_metadata`` on each AIMessage in ``response.generations``.
    Older paths put it in ``response.llm_output["token_usage"]``.
    """
    total = 0
    for gen_list in response.generations or []:
        for gen in gen_list:
            msg = getattr(gen, "message", None)
            if msg is None:
                continue
            usage = getattr(msg, "usage_metadata", None)
            if not usage:
                continue
            try:
                total += int(usage.get("total_tokens", 0) or 0)
            except (AttributeError, TypeError):
                pass

    if total:
        return total

    llm_output = getattr(response, "llm_output", None) or {}
    token_usage = llm_output.get("token_usage") if isinstance(llm_output, dict) else None
    if isinstance(token_usage, dict):
        try:
            return int(token_usage.get("total_tokens", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def attach(llm: Any, meter: _MeterLike | None, stage: str) -> Any:
    """Attach a usage callback to ``llm`` so its LLM calls record to ``meter``.

    Mutates the underlying ``BaseChatModel`` instance by appending a callback
    to its existing list. We mutate (rather than ``with_config`` wrapping)
    because deepagents' ``resolve_model`` only special-cases ``BaseChatModel``
    instances — a ``RunnableBinding`` returned by ``with_config`` is treated
    as a model spec string, which crashes profile lookup.

    Pass ``meter=None`` to skip — useful for tests that don't care about
    accounting.
    """
    if meter is None:
        return llm
    cb = UsageCallback(meter, stage)
    existing = getattr(llm, "callbacks", None)
    if existing is None:
        llm.callbacks = [cb]
    elif isinstance(existing, list):
        existing.append(cb)
    else:
        # `callbacks` may also be a BaseCallbackManager. Wrap as a list.
        llm.callbacks = [existing, cb]  # type: ignore[assignment]
    return llm
