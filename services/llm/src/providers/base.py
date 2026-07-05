"""Provider-agnostic LLM adapter interface — no FastAPI, no vendor SDK.

Neutral request/response types the API layer maps to/from, plus the provider
protocol and a normalized error hierarchy the router maps to HTTP status codes.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMRequest:
    messages: list[LLMMessage] = field(default_factory=list)
    system: str | None = None
    model: str | None = None
    max_tokens: int = 16000
    thinking: bool = True


@dataclass
class LLMResult:
    content: str
    model: str
    stop_reason: str
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    def chat(self, request: LLMRequest) -> LLMResult: ...


class ProviderError(Exception):
    """Base for normalized provider failures."""


class ProviderRateLimited(ProviderError):
    """Upstream returned 429."""


class ProviderTimeout(ProviderError):
    """Upstream connection/timeout failure."""


class ProviderUnavailable(ProviderError):
    """Upstream 5xx / auth / other status failure."""
