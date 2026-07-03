from contracts.fetcher import Fetcher, FetchError, FetchResult
from src.fetch.github import GithubFetcher
from src.fetch.web import WebFetcher


class FetchUnsupported(FetchError):
    """No fetcher is registered for a source."""


class FetcherRegistry:
    def __init__(self, mapping: dict[str, Fetcher]) -> None:
        self._by_source = mapping

    def fetch_for(self, source_id: str, url: str) -> FetchResult:
        fetcher = self._by_source.get(source_id)
        if fetcher is None:
            raise FetchUnsupported(f"no fetcher registered for source: {source_id}")
        return fetcher.fetch(url)


def default_registry() -> FetcherRegistry:
    """Fetchers wired up in v1: public web + github. Matches the sources whose
    content_fetch_enabled is true."""
    return FetcherRegistry({"web": WebFetcher(), "github": GithubFetcher()})
