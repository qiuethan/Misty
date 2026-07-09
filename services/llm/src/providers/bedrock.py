"""Claude via Amazon Bedrock (Mantle Messages endpoint).

Uses AnthropicBedrockMantle so usage bills as standard Amazon Bedrock (AWS
credits apply). Never AnthropicAWS / Claude Platform on AWS (Marketplace CCU).
"""

import anthropic
from anthropic import AnthropicBedrockMantle

from src.providers.base import (
    LLMRequest,
    LLMResult,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)


def _to_bedrock_model_id(model: str) -> str:
    # The Mantle Messages endpoint uses a bare `anthropic.` prefix
    # (e.g. anthropic.claude-sonnet-5). If cross-region inference requires a
    # `us.`/`global.` prefix on your account, adjust here — pin via smoke test.
    return f"anthropic.{model}"


class BedrockClaudeProvider:
    def __init__(self, *, aws_region: str, default_model: str, timeout_s: float, client=None):
        self._client = client or AnthropicBedrockMantle(aws_region=aws_region)
        self._default_model = default_model
        self._timeout_s = timeout_s

    def chat(self, request: LLMRequest) -> LLMResult:
        model = request.model or self._default_model
        kwargs: dict = {
            "model": _to_bedrock_model_id(model),
            "max_tokens": request.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        if request.system:
            kwargs["system"] = request.system
        if request.thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        try:
            msg = self._client.with_options(timeout=self._timeout_s).messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimited(str(exc)) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ProviderTimeout(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderUnavailable(str(exc)) from exc

        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        return LLMResult(
            content=text,
            model=msg.model,
            stop_reason=msg.stop_reason or "",
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
        )
