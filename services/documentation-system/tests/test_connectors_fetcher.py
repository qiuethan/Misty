import httpx
import pytest

from contracts.fetcher import FetchError
from src.fetch.connectors import ConnectorsFetcher


def _fetcher(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ConnectorsFetcher(
        source_id="gdocs", base_url="http://connectors", api_key="k", client=client
    )


def test_successful_fetch_returns_content_and_derived_snapshot():
    def handler(request):
        return httpx.Response(
            200, json={"title": "Deck", "content": "x" * 5000, "warnings": []}
        )

    result = _fetcher(handler).fetch("https://docs.google.com/document/d/abc/edit")
    assert result.title == "Deck"
    assert len(result.content) == 5000
    assert len(result.content_snapshot) == 2000
    assert result.content.startswith(result.content_snapshot)


def test_warnings_are_surfaced():
    def handler(request):
        return httpx.Response(
            200, json={"title": "Budget", "content": "a,b", "warnings": ["first sheet only"]}
        )

    result = _fetcher(handler).fetch("https://docs.google.com/spreadsheets/d/abc/edit")
    assert result.warnings == ["first sheet only"]


def test_source_id_is_sent_in_the_request_body():
    seen = {}

    def handler(request):
        import json as _json

        seen.update(_json.loads(request.content))
        return httpx.Response(200, json={"title": "t", "content": "c", "warnings": []})

    _fetcher(handler).fetch("https://docs.google.com/document/d/abc/edit")
    assert seen["source_id"] == "gdocs"
    assert seen["url"] == "https://docs.google.com/document/d/abc/edit"


@pytest.mark.parametrize("status", [403, 404, 422, 502, 503, 500])
def test_every_error_status_becomes_a_fetcherror(status):
    def handler(request):
        return httpx.Response(status, json={"detail": "nope"})

    with pytest.raises(FetchError):
        _fetcher(handler).fetch("https://docs.google.com/document/d/abc/edit")


def test_transport_failure_becomes_a_fetcherror():
    def handler(request):
        raise httpx.ConnectError("connectors is down")

    with pytest.raises(FetchError):
        _fetcher(handler).fetch("https://docs.google.com/document/d/abc/edit")
