from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from contracts.types import VerificationCode
from src.config import get_settings
from src.storage.postgres import PostgresVerificationStore


@pytest.fixture(scope="module")
def engine():
    return create_engine(get_settings().database_url, future=True)


@pytest.fixture
def store(engine):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE verification_codes RESTART IDENTITY"))
    return PostgresVerificationStore(engine)


def _rec(subject="s", email="a@b.com", **kw):
    now = datetime.now(timezone.utc)
    base = dict(
        subject=subject,
        email=email,
        code_hash="h",
        expires_at=now + timedelta(minutes=10),
        attempts=0,
        consumed_at=None,
        created_at=now,
    )
    base.update(kw)
    return VerificationCode(**base)


def test_roundtrip(store):
    store.create_code(_rec())
    got = store.get_code("s")
    assert got.email == "a@b.com" and got.attempts == 0


def test_create_replaces_per_subject(store):
    store.create_code(_rec(email="old@b.com"))
    store.create_code(_rec(email="new@b.com"))
    assert store.get_code("s").email == "new@b.com"


def test_latest_unconsumed_for_email(store):
    now = datetime.now(timezone.utc)
    store.create_code(_rec(subject="s1", email="x@y.com", consumed_at=now))
    assert store.latest_unconsumed_for_email("x@y.com") is None
    store.create_code(_rec(subject="s2", email="x@y.com"))
    assert store.latest_unconsumed_for_email("x@y.com").subject == "s2"


def test_set_attempts_and_consume(store):
    store.create_code(_rec())
    store.set_attempts("s", 2)
    assert store.get_code("s").attempts == 2
    store.mark_consumed("s", datetime.now(timezone.utc))
    assert store.get_code("s").consumed_at is not None
