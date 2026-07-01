import re

import httpx

from contracts.fetcher import FetchError, FetchResult

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TIMEOUT = httpx.Timeout(5.0)


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


class WebFetcher:
    """Fetch title + a text snapshot from a public web page."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, url: str) -> FetchResult:
        client = self._client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise FetchError(f"web fetch failed: {e}") from e
        finally:
            if self._client is None:
                client.close()
        return FetchResult(title=parse_title(resp.text), content_snapshot=extract_text(resp.text))
