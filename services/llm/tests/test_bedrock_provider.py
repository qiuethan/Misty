import anthropic
import httpx
import pytest

from src.providers.base import (
    LLMMessage,
    LLMRequest,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from src.providers.bedrock import BedrockClaudeProvider, _to_bedrock_model_id


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class _Msg:
    def __init__(self):
        self.content = [_Block("hello world")]
        self.model = "anthropic.claude-sonnet-5"
        self.stop_reason = "end_turn"
        self.usage = _Usage(3, 2)


class _FakeMessages:
    def __init__(self, captured, exc=None):
        self._captured = captured
        self._exc = exc

    def create(self, **kwargs):
        self._captured.update(kwargs)
        if self._exc is not None:
            raise self._exc
        return _Msg()


class _FakeClient:
    def __init__(self, exc=None):
        self.captured = {}
        self._messages = _FakeMessages(self.captured, exc)

    def with_options(self, **_kwargs):
        return self

    @property
    def messages(self):
        return self._messages


def _provider(client):
    return BedrockClaudeProvider(
        aws_region="us-east-1", default_model="claude-sonnet-5", timeout_s=30.0, client=client
    )


def test_model_id_prefix():
    assert _to_bedrock_model_id("claude-sonnet-5") == "anthropic.claude-sonnet-5"


def test_chat_maps_request_and_normalizes_response():
    client = _FakeClient()
    result = _provider(client).chat(
        LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            system="be brief",
            max_tokens=1000,
            thinking=True,
        )
    )
    sent = client.captured
    assert sent["model"] == "anthropic.claude-sonnet-5"
    assert sent["max_tokens"] == 1000
    assert sent["messages"] == [{"role": "user", "content": "hi"}]
    assert sent["system"] == "be brief"
    assert sent["thinking"] == {"type": "adaptive"}
    assert result.content == "hello world"
    assert result.model == "anthropic.claude-sonnet-5"
    assert result.stop_reason == "end_turn"
    assert result.input_tokens == 3 and result.output_tokens == 2


def test_per_request_model_override():
    client = _FakeClient()
    _provider(client).chat(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="claude-opus-4-8")
    )
    assert client.captured["model"] == "anthropic.claude-opus-4-8"


def test_thinking_off_omits_thinking():
    client = _FakeClient()
    _provider(client).chat(
        LLMRequest(messages=[LLMMessage(role="user", content="hi")], thinking=False)
    )
    assert "thinking" not in client.captured


def _resp(status):
    return httpx.Response(status, request=httpx.Request("POST", "https://x"))


def test_rate_limit_translation():
    exc = anthropic.RateLimitError("rate", response=_resp(429), body=None)
    with pytest.raises(ProviderRateLimited):
        _provider(_FakeClient(exc=exc)).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_connection_error_translation():
    exc = anthropic.APIConnectionError(message="boom", request=httpx.Request("POST", "https://x"))
    with pytest.raises(ProviderTimeout):
        _provider(_FakeClient(exc=exc)).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )


def test_status_error_translation():
    exc = anthropic.InternalServerError("boom", response=_resp(500), body=None)
    with pytest.raises(ProviderUnavailable):
        _provider(_FakeClient(exc=exc)).chat(
            LLMRequest(messages=[LLMMessage(role="user", content="hi")])
        )
