"""SSRF egress protection for the web fetcher.

These tests assert that internal/link-local/loopback/private destinations are
blocked BEFORE any network connection is made, on every redirect hop, and that
the connection is PINNED to a validated IP so DNS rebinding cannot swap in an
internal address between the check and the connect. No real network calls are
made: DNS is monkeypatched and httpx is driven through a recording MockTransport
so we can prove which address is actually connected to.
"""

import socket

import httpx
import pytest

from contracts.fetcher import FetchError
from src.fetch import web
from src.fetch.web import WebFetcher

_PUBLIC_IP = "93.184.216.34"


class _RecordingTransport(httpx.MockTransport):
    """MockTransport that records every request httpx actually issues. The
    request URL's host is the PINNED IP; the original hostname rides in the Host
    header, so tests can assert both what was connected to and for which host."""

    def __init__(self, handler):
        self.requests: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
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
        "http://172.16.5.4/internal",
        "http://[::1]/loopback",
        "http://0.0.0.0/",
        # Carrier-grade NAT / shared space (RFC 6598) — Alibaba metadata + more.
        "http://100.100.100.200/latest/meta-data/",
        "http://100.64.0.1/internal",
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


def test_blocks_multi_a_record_when_one_is_internal(monkeypatch):
    """A host with several A records is blocked if ANY record is internal."""

    def fake_getaddrinfo(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 0)),
        ]

    monkeypatch.setattr(web.socket, "getaddrinfo", fake_getaddrinfo)
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch("http://mixed.example/")
    assert transport.requests == []


def test_pins_validated_ip_defeating_dns_rebinding(monkeypatch):
    """Rebinding: the guard's resolution returns a public IP, but a later
    resolution would return a private one. Because we pin the connection to the
    validated IP, httpx connects to the literal public IP and never re-resolves,
    so the internal address can never be reached."""
    calls = {"n": 0}

    def rebinding_getaddrinfo(host, *args, **kwargs):
        calls["n"] += 1
        # First answer (used for validation) is public; any later answer is internal.
        ip = _PUBLIC_IP if calls["n"] == 1 else "10.0.0.5"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(web.socket, "getaddrinfo", rebinding_getaddrinfo)

    def handler(request):
        return httpx.Response(200, html="<title>Safe</title>")

    fetcher, transport = _make(handler)
    result = fetcher.fetch("http://rebind.example/")
    assert result.title == "Safe"
    # The socket targeted the pinned, validated public IP — not the rebind target.
    assert [r.url.host for r in transport.requests] == [_PUBLIC_IP]
    assert all(r.url.host != "10.0.0.5" for r in transport.requests)


def test_malformed_hostname_becomes_fetch_error(monkeypatch):
    """A hostname that fails IDNA encoding raises UnicodeError from getaddrinfo;
    it must surface as a handled FetchError (→ 502), never a raw 500."""

    def raiser(host, *args, **kwargs):
        raise UnicodeError("label empty or too long")

    monkeypatch.setattr(web.socket, "getaddrinfo", raiser)
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch("http://xn--malformed--host/")
    assert transport.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://[::1",  # invalid IPv6 literal -> urlsplit raises ValueError
        "http://example.com:99999/",  # out-of-range port -> parts.port raises ValueError
        "http://",  # no host
        "http:///path/only",  # no host, path only
    ],
)
def test_malformed_url_becomes_fetch_error_not_500(url):
    """URL parsing (urlsplit/.hostname/.port) is inside the guarded region, so a
    malformed URL is a handled FetchError (-> 502), never a raw ValueError/500,
    and no connection is attempted."""
    fetcher, transport = _make(_boom)
    with pytest.raises(FetchError):
        fetcher.fetch(url)
    assert transport.requests == []


def test_malformed_redirect_location_becomes_fetch_error(public_dns):
    """A redirect whose Location is an unparseable URL surfaces as a handled
    FetchError, not a raw 500, when re-parsed for the next hop."""

    def handler(request):
        return httpx.Response(302, headers={"location": "http://[::1"})

    fetcher, transport = _make(handler)
    with pytest.raises(FetchError):
        fetcher.fetch("http://public.example.com/redirector")


def test_blocks_redirect_to_internal_ip(public_dns):
    def handler(request):
        # The original hostname rides in the Host header (URL host is the pinned IP).
        if request.headers.get("host") == "public.example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})
        raise AssertionError(f"followed redirect to blocked host: {request.url}")

    fetcher, transport = _make(handler)
    with pytest.raises(FetchError):
        fetcher.fetch("http://public.example.com/redirector")
    # The public URL was contacted, but the internal redirect target never was.
    assert [r.headers.get("host") for r in transport.requests] == ["public.example.com"]


def test_pins_connection_to_validated_ip(public_dns):
    """Sanity check on the pin: URL host is the validated IP, Host header + SNI
    carry the real hostname so TLS/cert verification still targets it."""

    def handler(request):
        return httpx.Response(200, html="<title>Public Page</title>")

    fetcher, transport = _make(handler)
    fetcher.fetch("https://public.example.com/path?q=1")
    (req,) = transport.requests
    assert req.url.host == _PUBLIC_IP
    assert req.url.path == "/path"
    assert req.headers.get("host") == "public.example.com"
    assert req.extensions.get("sni_hostname") == "public.example.com"


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
    assert [r.url.path for r in transport.requests] == ["/start", "/final"]
