import httpx
import pytest

from contracts.fetcher import FetchError
from src.fetch.github import GithubFetcher, parse_github_title
from src.fetch.registry import FetchUnsupported, FetcherRegistry
from src.fetch.web import WebFetcher, extract_text, parse_title, MAX_CONTENT_CHARS, SNAPSHOT_CHARS


def test_parse_title_from_html():
    assert parse_title("<html><head><title>Hello  World</title></head></html>") == "Hello World"


def test_parse_title_none_when_absent():
    assert parse_title("<html><body>no title</body></html>") is None


def test_extract_text_strips_tags_and_truncates():
    out = extract_text("<p>Alpha</p><p>Beta</p>", limit=100)
    assert "Alpha" in out and "<p>" not in out


def test_parse_github_title_from_path():
    assert parse_github_title("https://github.com/utmist/site") == "utmist/site"


def test_web_fetcher_uses_injected_client():
    def handler(request):
        return httpx.Response(200, html="<title>Injected</title>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # Literal public IP: the SSRF guard validates it without any DNS lookup.
    result = WebFetcher(client=client).fetch("https://93.184.216.34")
    assert result.title == "Injected"


def test_web_fetcher_raises_fetcherror_on_http_error():
    def handler(request):
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(FetchError):
        WebFetcher(client=client).fetch("https://93.184.216.34")


def test_registry_routes_by_source_and_rejects_unknown():
    reg = FetcherRegistry({"github": GithubFetcher()})
    assert reg.fetch_for("github", "https://github.com/a/b").title == "a/b"
    with pytest.raises(FetchUnsupported):
        reg.fetch_for("web", "https://x.com")


def test_web_fetcher_returns_full_content_and_bounded_snapshot():
    body = "<html><title>T</title><body>" + ("word " * 2000) + "</body></html>"

    def handler(request):
        return httpx.Response(200, html=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = WebFetcher(client=client).fetch("https://93.184.216.34")
    assert result.content is not None
    assert len(result.content) > SNAPSHOT_CHARS
    assert len(result.content_snapshot) == SNAPSHOT_CHARS
    assert result.content.startswith(result.content_snapshot)


def test_extract_text_caps_at_max_content_chars():
    huge = "<p>" + ("x" * (MAX_CONTENT_CHARS + 5000)) + "</p>"
    assert len(extract_text(huge)) == MAX_CONTENT_CHARS
