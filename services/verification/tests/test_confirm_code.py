from datetime import datetime, timedelta, timezone

from conftest import AUTH
from contracts.types import VerificationCode
from src.codes import hash_code

SECRET = "test-hmac-secret"


def _code(
    subject="discord:1", email="a@b.com", code="123456", *, ttl_min=10, attempts=0, consumed=False
):
    now = datetime.now(timezone.utc)
    return VerificationCode(
        subject=subject,
        email=email,
        code_hash=hash_code(code, SECRET),
        expires_at=now + timedelta(minutes=ttl_min),
        attempts=attempts,
        consumed_at=(now if consumed else None),
        created_at=now,
    )


def test_confirm_success(client, store):
    store.create_code(_code())
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert r.status_code == 200
    assert r.json() == {"verified": True, "subject": "discord:1", "email": "a@b.com"}


def test_confirm_wrong_code_increments(client, store):
    store.create_code(_code())
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "000000"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_code"
    assert store.get_code("discord:1").attempts == 1


def test_confirm_expired(client, store):
    store.create_code(_code(ttl_min=-1))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert r.status_code == 410
    assert r.json()["detail"] == "expired"


def test_confirm_single_use_then_idempotent_replay(client, store):
    store.create_code(_code())
    first = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert first.status_code == 200
    # Replay within TTL returns success again even with a bogus code.
    again = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "999999"}
    )
    assert again.status_code == 200
    assert again.json()["verified"] is True


def test_confirm_lockout_after_five(client, store):
    store.create_code(_code(attempts=4))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "000000"}
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"


def test_confirm_no_pending(client):
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "nope", "code": "123456"}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "no_pending_code"
