"""SSRF egress protection for the web fetcher.

These tests assert that internal/link-local/loopback/private destinations are
blocked BEFORE any network connection is made, and on every redirect hop. No
real network calls are made: DNS is monkeypatched and httpx is driven through a
recording MockTransport so we can prove a blocked host is never connected to.
"""

import socket

import httpx
import pytest

from contracts.fetcher import FetchError
from src.fetch import web
from src.fetch.web import WebFetcher

_PUBLIC_IP = "93.184.216.34"


class _RecordingTransport(httpx.MockTransport):
    """MockTransport that records every URL httpx actually tries to connect to."""

    def __init__(self, handler):
        self.requests: list[httpx.URL] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request.url)
            return handler(request)

        super().__init__(_wrapped)


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every hostname to a fixed public IP so no real DNS is used."""

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, 0))]

    monkeypatch.setattr(web.socket, "getaddrinfo", fake_getaddrinfo)


def _make(handler):
    transport = _RecordingTransport(handler)
    client = httpx.Client(transport=transport)
    return WebFetcher(client=client), transport


def _boom(request):
    raise AssertionError(f"connection attempted to blocked host: {request.url}")


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://127.0.0.1/admin",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://[::1]/loopback",
        "http://0.0.0.0/",
    ],
)
def test_blocks_literal_internal_ip_before_connecting(url):
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch(url)
    assert transport.requests == []  # never connected


def test_blocks_non_http_scheme():
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch("file:///etc/passwd")
    assert transport.requests == []


def test_blocks_hostname_resolving_to_internal_ip(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(web.socket, "getaddrinfo", fake_getaddrinfo)
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch("http://metadata.internal.example/")
    assert transport.requests == []


def test_blocks_ipv4_mapped_ipv6(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 0))]

    monkeypatch.setattr(web.socket, "getaddrinfo", fake_getaddrinfo)
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch("http://sneaky.example/")
    assert transport.requests == []


def test_blocks_redirect_to_internal_ip(public_dns):
    def handler(request):
        if request.url.host == "public.example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        raise AssertionError(f"followed redirect to blocked host: {request.url}")

    fetcher, transport = _make(handler)
    with pytest.raises(FetchError):
        fetcher.fetch("http://public.example.com/redirector")
    # The public URL was contacted, but the internal redirect target never was.
    assert [r.host for r in transport.requests] == ["public.example.com"]


def test_allows_public_url(public_dns):
    def handler(request):
        return httpx.Response(200, html="<title>Public Page</title>Body text")

    fetcher, transport = _make(handler)
    result = fetcher.fetch("https://public.example.com/")
    assert result.title == "Public Page"
    assert "Body text" in (result.content_snapshot or "")


def test_allows_public_redirect_chain(public_dns):
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "https://public.example.com/final"})
        return httpx.Response(200, html="<title>Final</title>")

    fetcher, transport = _make(handler)
    result = fetcher.fetch("https://public.example.com/start")
    assert result.title == "Final"
    assert [r.path for r in transport.requests] == ["/start", "/final"]
