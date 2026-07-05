"""Claude via Amazon Bedrock using the Converse API (bedrock-runtime).

Used because this account's Bedrock model access is US-regional (cross-region
inference profiles), which the Messages/Mantle endpoint cannot target. Still
standard Amazon Bedrock billing (credits apply) — NOT AnthropicAWS / Claude
Platform on AWS. Credentials come from the standard AWS chain (incl.
AWS_BEARER_TOKEN_BEDROCK).
"""

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from src.providers.base import (
    LLMRequest,
    LLMResult,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

# Neutral model name -> the exact Bedrock inference-profile id this account can
# invoke. Per-model: prefixes/suffixes differ, so this is an explicit table (not
# a formula). Pinned by live probes against the account.
_MODEL_IDS = {
    "claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
    "claude-opus-4-6": "us.anthropic.claude-opus-4-6-v1",
}

_RATE_LIMIT_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceQuotaExceededException",
}

# Genuine timeout/connection failures (map to 504). Other BotoCoreError subtypes
# — NoCredentialsError, ParamValidationError, etc. — are config faults, not timeouts.
_TIMEOUT_ERRORS = (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError)


class BedrockConverseProvider:
    def __init__(self, *, aws_region: str, default_model: str, timeout_s: float, client=None):
        if default_model not in _MODEL_IDS:
            raise ValueError(
                f"unsupported default model {default_model!r}; expected one of {sorted(_MODEL_IDS)}"
            )
        self._client = client or boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            config=Config(read_timeout=timeout_s, connect_timeout=min(timeout_s, 10.0)),
        )
        self._default_model = default_model
        self._timeout_s = timeout_s

    def _model_id(self, model: str) -> str:
        try:
            return _MODEL_IDS[model]
        except KeyError:
            raise ProviderUnavailable(f"unsupported model: {model!r}")

    def chat(self, request: LLMRequest) -> LLMResult:
        model = request.model or self._default_model
        bedrock_id = self._model_id(model)
        kwargs: dict = {
            "modelId": bedrock_id,
            "messages": [
                {"role": m.role, "content": [{"text": m.content}]} for m in request.messages
            ],
            "inferenceConfig": {"maxTokens": request.max_tokens},
        }
        if request.system:
            kwargs["system"] = [{"text": request.system}]
        if request.thinking:
            # Adaptive thinking returns an extra `reasoningContent` block, which
            # we ignore when extracting the answer text below.
            kwargs["additionalModelRequestFields"] = {"thinking": {"type": "adaptive"}}

        try:
            response = self._client.converse(**kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in _RATE_LIMIT_CODES:
                raise ProviderRateLimited(str(exc)) from exc
            raise ProviderUnavailable(str(exc)) from exc
        except _TIMEOUT_ERRORS as exc:
            raise ProviderTimeout(str(exc)) from exc
        except BotoCoreError as exc:  # credential/param/other boto-side faults
            raise ProviderUnavailable(str(exc)) from exc

        try:
            blocks = response["output"]["message"]["content"]
        except (KeyError, TypeError) as exc:
            # Content-filtered / guardrail / unexpected-shape responses.
            raise ProviderUnavailable(f"unexpected Bedrock response shape: {exc}") from exc
        text = "".join(b["text"] for b in blocks if "text" in b)
        usage = response.get("usage", {})
        return LLMResult(
            content=text,
            model=bedrock_id,
            stop_reason=response.get("stopReason", ""),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )
