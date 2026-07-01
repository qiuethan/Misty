from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from contracts.types import Provider, RoleKind
from src.config import get_settings


def build_seed_providers() -> list[Provider]:
    """Standard providers seed for tests — matches migration 004."""
    now = datetime.now(timezone.utc)
    return [
        Provider(
            id=pid, label=plabel, description=None, active=True,
            created_at=now, updated_at=now, created_by="system", updated_by="system",
        )
        for pid, plabel in [
            ("discord", "Discord"), ("github", "GitHub"),
            ("notion", "Notion"), ("uoft_email", "UofT Email"),
        ]
    ]


def build_seed_role_kinds() -> list[RoleKind]:
    """Standard role_kinds seed set for tests — matches migration 002."""
    now = datetime.now(timezone.utc)
    return [
        RoleKind(
            id=rid, label=rlabel, description=None, active=True,
            created_at=now, updated_at=now,
            created_by="system", updated_by="system",
        )
        for rid, rlabel in [
            ("executive", "Executive"),
            ("director", "Director"),
            ("lead", "Lead"),
            ("member", "Member"),
        ]
    ]


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
            text(
                "TRUNCATE person_identifiers, team_memberships, teams, people, api_keys "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield engine
