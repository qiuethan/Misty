"""Config-driven source selection. Add a source = new impl + one entry here."""

from collections.abc import Callable

from src.config import Settings
from src.sources.base import SourceFetcher
from src.sources.google import GOOGLE_SOURCE_IDS, GoogleSource


def _build_google(settings: Settings) -> SourceFetcher:
    return GoogleSource(
        credentials_json_b64=settings.google_credentials_json,
        max_content_chars=settings.max_content_chars,
    )


SOURCE_BUILDERS: dict[str, Callable[[Settings], SourceFetcher]] = {
    source_id: _build_google for source_id in GOOGLE_SOURCE_IDS
}


def build_registry(settings: Settings) -> dict[str, SourceFetcher]:
    """Instantiate every configured source once, at startup."""
    return {source_id: build(settings) for source_id, build in SOURCE_BUILDERS.items()}
