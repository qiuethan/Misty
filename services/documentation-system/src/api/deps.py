from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from contracts.directory import DirectoryClient
from contracts.storage import StorageAdapter
from src.config import get_settings
from src.directory.http_client import HttpDirectoryClient
from src.fetch.registry import FetcherRegistry, default_registry


@lru_cache(maxsize=1)
def _default_engine() -> Engine:
    return create_engine(get_settings().database_url, future=True, pool_pre_ping=True)


def get_storage() -> StorageAdapter:
    # Imported lazily: src.storage.postgres does not exist until Task 15.
    # Deferring the import keeps this module importable now; tests always
    # override get_storage via app.dependency_overrides.
    from src.storage.postgres import PostgresStorageAdapter

    return PostgresStorageAdapter(_default_engine())


def get_fetchers() -> FetcherRegistry:
    return default_registry()


def get_directory() -> DirectoryClient:
    s = get_settings()
    return HttpDirectoryClient(s.directory_base_url, s.directory_api_key)
