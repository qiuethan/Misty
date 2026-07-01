from typing import Protocol

from pydantic import BaseModel, ConfigDict


class FetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    content_snapshot: str | None = None


class FetchError(Exception):
    """Raised when a fetcher cannot retrieve or parse a URL. Non-fatal at the
    ingest layer — becomes a warning, never blocks the doc."""


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult:
        """Retrieve title/snapshot for a URL. Raises FetchError on failure."""
        ...
