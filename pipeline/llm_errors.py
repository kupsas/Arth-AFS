"""
Structured LLM failure reporting for classification (native SDKs) and shared types for the agent.

Used when every provider in the fallback chain fails so the UI can pause safely and show
actionable copy (busy provider, billing, bad key, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ErrorType = Literal["rate_limit", "billing", "auth", "other"]


def _safe_exc_message(exc: BaseException, *, max_len: int = 500) -> str:
    """Short, user-facing-safe snippet (never empty)."""
    s = str(exc).strip()
    if not s:
        s = type(exc).__name__
    return s[:max_len]


@dataclass(frozen=True)
class ProviderFailure:
    """One failed attempt for a cloud provider used for smart labels / Ask Arth."""

    provider: str  # "openai" | "anthropic" | "google" | "other"
    error_type: ErrorType
    message: str


class ClassifierPausedError(Exception):
    """All classification LLM providers failed for this batch — pause import and surface reasons."""

    failures: list[ProviderFailure]

    def __init__(self, failures: list[ProviderFailure]) -> None:
        super().__init__(f"classifier_paused:{len(failures)}")
        self.failures = failures


class AgentPausedError(Exception):
    """All agent (LiteLLM) models in the chain failed for this turn."""

    failures: list[ProviderFailure]

    def __init__(self, failures: list[ProviderFailure]) -> None:
        super().__init__(f"agent_paused:{len(failures)}")
        self.failures = failures


def _billing_hint(lower: str) -> bool:
    return any(
        x in lower
        for x in (
            "insufficient_quota",
            "billing",
            "credit balance",
            "exceeded your current quota",
            "payment required",
        )
    )


def classify_provider_sdk_error(exc: BaseException, provider: str) -> ProviderFailure:
    """
    Map native OpenAI / Anthropic / Google client exceptions to :class:`ProviderFailure`.

    Unknown types fall through to ``other`` with the original message trimmed.
    """
    msg = _safe_exc_message(exc)
    lower = msg.lower()

    # --- OpenAI ---
    try:
        from openai import AuthenticationError as OpenAIAuthError
        from openai import RateLimitError as OpenAIRateLimitError
    except ImportError:
        OpenAIRateLimitError = OpenAIAuthError = ()  # type: ignore[misc,assignment]

    if OpenAIRateLimitError and isinstance(exc, OpenAIRateLimitError):  # type: ignore[truthy-function]
        et: ErrorType = "billing" if _billing_hint(lower) else "rate_limit"
        return ProviderFailure(provider, et, msg)
    if OpenAIAuthError and isinstance(exc, OpenAIAuthError):  # type: ignore[truthy-function]
        return ProviderFailure(provider, "auth", msg)

    # --- Anthropic ---
    try:
        from anthropic import AuthenticationError as AnthropicAuthError
        from anthropic import RateLimitError as AnthropicRateLimitError
    except ImportError:
        AnthropicRateLimitError = AnthropicAuthError = ()  # type: ignore[misc,assignment]

    if AnthropicRateLimitError and isinstance(exc, AnthropicRateLimitError):  # type: ignore[truthy-function]
        et = "billing" if _billing_hint(lower) else "rate_limit"
        return ProviderFailure(provider, et, msg)
    if AnthropicAuthError and isinstance(exc, AnthropicAuthError):  # type: ignore[truthy-function]
        return ProviderFailure(provider, "auth", msg)

    # --- Google GenAI / api_core ---
    try:
        from google.api_core import exceptions as gexc
    except ImportError:
        gexc = None  # type: ignore[assignment]

    if gexc is not None:
        if isinstance(exc, gexc.ResourceExhausted):
            return ProviderFailure(provider, "rate_limit", msg)
        if isinstance(exc, (gexc.PermissionDenied, gexc.Unauthenticated)):
            return ProviderFailure(provider, "auth", msg)

    return ProviderFailure(provider, "other", msg)
