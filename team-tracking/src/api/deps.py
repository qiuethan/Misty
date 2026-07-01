from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from contracts.storage import StorageAdapter
from src.config import get_settings
from src.storage.postgres import PostgresStorageAdapter


@lru_cache(maxsize=1)
def _default_engine() -> Engine:
    return create_engine(get_settings().database_url, future=True, pool_pre_ping=True)


def get_storage() -> StorageAdapter:
    """FastAPI dependency: return the process-wide storage adapter.

    Tests override this to inject InMemoryStorageAdapter via
    app.dependency_overrides[get_storage] = lambda: adapter.
    """
    return PostgresStorageAdapter(_default_engine())
