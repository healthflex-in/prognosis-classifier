"""
Provider-agnostic LLM client factory.

The goal: switching the whole app to a different LLM provider should be an env
change (LLM_PROVIDER=...) plus, if that provider isn't wired up yet, one new
branch in this file — never a change to any individual agent file.

Currently implemented:
  - anthropic  (Claude, via langchain-anthropic)

Not yet implemented:
  - bedrock    (kept as a named, explicit gap below — add a ChatBedrock/
                ChatBedrockConverse branch here when the team actually needs it)

Agents call build_chat_llm(...) instead of importing a provider SDK class
directly. As of this migration, recommendation_agent, prognosis_agent, and
proper_react_agent go through this factory. triage_agent and clinical_agent
still talk to Google directly (raw google-genai, not LangChain) and are
migrated separately — see MIGRATION notes in those files.
"""
import os
from typing import Any, Dict, Optional

SUPPORTED_LLM_PROVIDERS = frozenset({"anthropic", "bedrock"})


def get_llm_provider() -> str:
    """The active provider. No silent default to a provider other than what's
    explicitly configured — but anthropic is a reasonable default today since
    it's the only one actually implemented."""
    return os.getenv("LLM_PROVIDER", "anthropic")


def build_chat_llm(
    *,
    model: str,
    temperature: Optional[float] = None,
    max_tokens: int = 1024,
    thinking_budget: Optional[int] = None,
):
    """
    Build a LangChain-compatible chat model for whichever provider LLM_PROVIDER
    selects.

    model: provider-specific model id/name (caller resolves this from its own
           env var, e.g. RECOMMENDATION_MODEL, with its own default).
    thinking_budget: None or <=0 means extended thinking is off. >0 enables it
           (provider-specific minimums are applied internally — e.g. Anthropic's
           API requires budget_tokens >= 1024).
    """
    provider = get_llm_provider()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise RuntimeError(
            f"LLM_PROVIDER={provider!r} is not supported. Choose one of {sorted(SUPPORTED_LLM_PROVIDERS)}."
        )

    if provider == "anthropic":
        return _build_anthropic_chat_llm(model, temperature, max_tokens, thinking_budget)

    # provider == "bedrock" — intentionally not implemented yet. Selecting it
    # fails loudly here instead of silently doing the wrong thing.
    raise NotImplementedError(
        f"LLM_PROVIDER={provider!r} is not implemented yet in prognosis-classifier. "
        "Add a branch in utils/llm_provider.py when this is needed."
    )


def _build_anthropic_chat_llm(
    model: str,
    temperature: Optional[float],
    max_tokens: int,
    thinking_budget: Optional[int],
):
    from langchain_anthropic import ChatAnthropic

    api_key = os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY (or ANTHROPIC_API_KEY) not set in environment")

    kwargs: Dict[str, Any] = dict(model=model, api_key=api_key, max_tokens=max_tokens)

    # CONFIRMED VIA REAL API CALL (2026-11-07) + corroborated by multiple sources:
    # Claude's 5.x-generation models (e.g. claude-haiku-5-5, released 2026-10-07)
    # reject `temperature` outright — ANY value, not just unusual ones — with
    # 400 "temperature: Extra inputs are not permitted". They moved to adaptive
    # thinking + an `effort` parameter instead. The same generation also rejects
    # explicit thinking.budget_tokens (the old extended-thinking shape used below).
    # No agent here has ever validated that a non-default temperature improves
    # quality (the one benchmark that exists, bench_report.md, is about thinking
    # budget, not temperature) — so rather than branch on model name (fragile the
    # next time Anthropic renames a generation), temperature is simply never sent.
    # If thinking_budget is ever set > 0 on a 5.x-generation model, expect the same
    # class of 400 for budget_tokens — that path hasn't been fixed for this
    # generation yet since every agent defaults to thinking disabled today.
    if thinking_budget and thinking_budget > 0:
        budget = max(thinking_budget, 1024)
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
        kwargs["max_tokens"] = max(max_tokens, budget + 256)

    return ChatAnthropic(**kwargs)
