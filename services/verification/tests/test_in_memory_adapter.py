from datetime import datetime, timedelta, timezone

from contracts.types import VerificationCode
from src.storage.in_memory import InMemoryVerificationStore


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


def test_create_and_get():
    s = InMemoryVerificationStore()
    s.create_code(_rec())
    assert s.get_code("s").email == "a@b.com"


def test_create_replaces_per_subject():
    s = InMemoryVerificationStore()
    s.create_code(_rec(email="old@b.com"))
    s.create_code(_rec(email="new@b.com"))
    assert s.get_code("s").email == "new@b.com"


def test_latest_unconsumed_ignores_consumed():
    s = InMemoryVerificationStore()
    now = datetime.now(timezone.utc)
    s.create_code(_rec(subject="s1", email="x@y.com", consumed_at=now))
    assert s.latest_unconsumed_for_email("x@y.com") is None
    s.create_code(_rec(subject="s2", email="x@y.com"))
    assert s.latest_unconsumed_for_email("x@y.com").subject == "s2"


def test_latest_unconsumed_returns_most_recent_of_several():
    s = InMemoryVerificationStore()
    now = datetime.now(timezone.utc)
    s.create_code(_rec(subject="s_old", email="m@x.com", created_at=now - timedelta(minutes=5)))
    s.create_code(_rec(subject="s_new", email="m@x.com", created_at=now - timedelta(minutes=1)))
    assert s.latest_unconsumed_for_email("m@x.com").subject == "s_new"


def test_set_attempts_and_mark_consumed():
    s = InMemoryVerificationStore()
    s.create_code(_rec())
    s.set_attempts("s", 3)
    assert s.get_code("s").attempts == 3
    s.mark_consumed("s", datetime.now(timezone.utc))
    assert s.get_code("s").consumed_at is not None
