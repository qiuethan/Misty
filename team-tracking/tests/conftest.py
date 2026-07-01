from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config import get_settings


@pytest.fixture(scope="session")
def engine() -> Engine:
    return create_engine(get_settings().database_url, future=True)


@pytest.fixture
def clean_db(engine: Engine) -> Iterator[Engine]:
    """Truncate mutable tables before each Postgres adapter test.

    Keeps role_kinds intact (seeded via migration).
    """
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE team_memberships, teams, people RESTART IDENTITY CASCADE")
        )
    yield engine
