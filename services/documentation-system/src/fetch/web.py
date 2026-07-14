import ipaddress
import re
import socket
from urllib.parse import urlsplit

import httpx

from contracts.fetcher import FetchError, FetchResult

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TIMEOUT = httpx.Timeout(5.0)

# SSRF egress protection.
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 5
_METADATA_IP = ipaddress.ip_address("169.254.169.254")

_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class BlockedURLError(FetchError):
    """A URL was rejected by SSRF egress protection before any connection was
    attempted. Subclasses FetchError so ingest treats it as a normal fetch
    failure (warning) and the router surfaces it as a fetch error, not a 500."""


def parse_title(html: str) -> str | None:
    m = _TITLE_RE.search(html)
    if not m:
        return None
    title = _WS_RE.sub(" ", m.group(1)).strip()
    return title or None


def extract_text(html: str, limit: int = 2000) -> str:
    stripped = _TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", stripped).strip()
    return text[:limit]


def _is_blocked_ip(ip: _IpAddress) -> bool:
    """True if `ip` is in a private/loopback/link-local/reserved range or is the
    cloud metadata address. IPv4-mapped IPv6 addresses are unwrapped first so an
    attacker cannot smuggle an internal IPv4 through the IPv6 form."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip == _METADATA_IP:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def _resolve_ips(host: str) -> list[_IpAddress]:
    """Resolve `host` to the IPs httpx would connect to. A literal IP is returned
    as-is (no DNS); otherwise every getaddrinfo answer is returned so that ALL
    candidate addresses can be validated, not just the first."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips: list[_IpAddress] = []
    for info in infos:
        addr = info[4][0]
        # getaddrinfo can suffix a scope id on link-local IPv6 (e.g. "fe80::1%eth0").
        addr = addr.split("%", 1)[0]
        ips.append(ipaddress.ip_address(addr))
    return ips


def _guard_url(url: str) -> None:
    """Reject `url` unless it uses http(s) and every address it resolves to is a
    public destination. Raises BlockedURLError otherwise. Called for the initial
    URL and again for each redirect hop, so the address actually connected to is
    always validated first."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise BlockedURLError(f"blocked URL scheme: {scheme or '(none)'!r}")
    host = parts.hostname
    if not host:
        raise BlockedURLError(f"blocked URL with no host: {url!r}")
    try:
        ips = _resolve_ips(host)
    except socket.gaierror as e:
        raise BlockedURLError(f"could not resolve host {host!r}: {e}") from e
    if not ips:
        raise BlockedURLError(f"could not resolve host {host!r}")
    for ip in ips:
        if _is_blocked_ip(ip):
            raise BlockedURLError(f"blocked internal address for host {host!r}: {ip}")


class WebFetcher:
    """Fetch title + a text snapshot from a public web page.

    Redirects are followed manually (httpx auto-follow is disabled) so that every
    hop's URL and resolved IP is validated by the SSRF guard before a request is
    issued. A blocked host is therefore never connected to."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, url: str) -> FetchResult:
        # follow_redirects stays False: we validate and follow each hop ourselves.
        client = self._client or httpx.Client(timeout=_TIMEOUT)
        try:
            current = url
            for _ in range(_MAX_REDIRECTS + 1):
                _guard_url(current)  # raises BlockedURLError before connecting
                resp = client.get(current)
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchError("web fetch failed: redirect without location header")
                    current = str(resp.url.join(location))
                    continue
                resp.raise_for_status()
                return FetchResult(
                    title=parse_title(resp.text),
                    content_snapshot=extract_text(resp.text),
                )
            raise FetchError(f"web fetch failed: too many redirects (>{_MAX_REDIRECTS})")
        except httpx.HTTPError as e:
            raise FetchError(f"web fetch failed: {e}") from e
        finally:
            if self._client is None:
                client.close()
