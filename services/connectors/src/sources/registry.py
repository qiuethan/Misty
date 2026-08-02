"""Config-driven source selection. Add a source = new impl + one entry here."""

from collections.abc import Callable

from src.config import Settings
from src.sources.base import SourceFetcher

SOURCE_BUILDERS: dict[str, Callable[[Settings], SourceFetcher]] = {}


def build_registry(settings: Settings) -> dict[str, SourceFetcher]:
    """Instantiate every configured source once, at startup."""
    return {source_id: build(settings) for source_id, build in SOURCE_BUILDERS.items()}
