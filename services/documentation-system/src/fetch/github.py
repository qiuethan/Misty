from urllib.parse import urlsplit

from contracts.fetcher import FetchResult


def parse_github_title(url: str) -> str | None:
    """Derive an `owner/repo` title from a github.com URL path. Returns None
    if the path lacks at least owner + repo."""
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if len(segments) < 2:
        return None
    return f"{segments[0]}/{segments[1]}"


class GithubFetcher:
    """Cheap, no-network fetcher: title from the URL path. Content snapshot is
    left empty in v1 (raw-content fetch is a later enhancement)."""

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(title=parse_github_title(url), content_snapshot=None)
