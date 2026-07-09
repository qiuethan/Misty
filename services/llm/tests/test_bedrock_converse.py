import botocore.exceptions
import pytest

from src.providers.base import (
    LLMMessage,
    LLMRequest,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from src.providers.bedrock_converse import BedrockConverseProvider


class _FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.captured = {}

    def converse(self, **kwargs):
        self.captured = kwargs
        if self._exc is not None:
            raise self._exc
        return self._response


def _resp(text="hello world", stop="end_turn", tin=5, tout=3, extra_blocks=None):
    content = list(extra_blocks or []) + [{"text": text}]
    return {
        "output": {"message": {"content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": tin, "outputTokens": tout, "totalTokens": tin + tout},
    }


def _provider(client):
    return BedrockConverseProvider(
        aws_region="us-east-1", default_model="claude-sonnet-4-6", timeout_s=30.0, client=client
    )


def test_maps_request_and_normalizes_response():
    client = _FakeClient(response=_resp())
    result = _provider(client).chat(
        LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            system="be brief",
            max_tokens=1000,
            thinking=True,
        )
    )
    sent = client.captured
    assert sent["modelId"] == "us.anthropic.claude-sonnet-4-6"
    assert sent["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
    assert sent["system"] == [{"text": "be brief"}]
    assert sent["inferenceConfig"] == {"maxTokens": 1000}
    assert sent["additionalModelRequestFields"] == {"thinking": {"type": "adaptive"}}
    assert result.content == "hello world"
    assert result.model == "us.anthropic.claude-sonnet-4-6"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 5 and result.output_tokens == 3


def test_opus_override_maps_to_v1_profile():
    client = _FakeClient(response=_resp())
    _provider(client).chat(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="claude-opus-4-6")
    )
    assert client.captured["modelId"] == "us.anthropic.claude-opus-4-6-v1"


def test_thinking_off_omits_field():
    client = _FakeClient(response=_resp())
    _provider(client).chat(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], thinking=False)
    )
    assert "additionalModelRequestFields" not in client.captured


def test_reasoning_block_is_ignored_in_content():
    # Adaptive thinking prepends a reasoningContent block; only text is the answer.
    client = _FakeClient(
        response=_resp(extra_blocks=[{"reasoningContent": {"reasoningText": {"text": "hmm"}}}])
    )
    result = _provider(client).chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")]))
    assert result.content == "hello world"


def test_unsupported_model_raises_unavailable():
    with pytest.raises(ProviderUnavailable):
        _provider(_FakeClient(response=_resp())).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="claude-sonnet-5")
        )


def _client_error(code):
    return botocore.exceptions.ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


def test_throttling_maps_to_rate_limited():
    with pytest.raises(ProviderRateLimited):
        _provider(_FakeClient(exc=_client_error("ThrottlingException"))).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_other_client_error_maps_to_unavailable():
    with pytest.raises(ProviderUnavailable):
        _provider(_FakeClient(exc=_client_error("AccessDeniedException"))).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_read_timeout_maps_to_timeout():
    exc = botocore.exceptions.ReadTimeoutError(endpoint_url="https://bedrock")
    with pytest.raises(ProviderTimeout):
        _provider(_FakeClient(exc=exc)).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_missing_credentials_maps_to_unavailable_not_timeout():
    # NoCredentialsError is a BotoCoreError but a config fault, not a timeout.
    with pytest.raises(ProviderUnavailable):
        _provider(_FakeClient(exc=botocore.exceptions.NoCredentialsError())).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_unexpected_response_shape_maps_to_unavailable():
    # e.g. content-filtered / guardrail response with no message content.
    with pytest.raises(ProviderUnavailable):
        _provider(_FakeClient(response={"stopReason": "content_filtered"})).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_bad_default_model_raises_at_construction():
    with pytest.raises(ValueError, match="unsupported default model"):
        BedrockConverseProvider(
            aws_region="us-east-1",
            default_model="claude-sonnet-5",
            timeout_s=30.0,
            client=_FakeClient(),
        )
