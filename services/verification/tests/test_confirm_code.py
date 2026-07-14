from datetime import datetime, timedelta, timezone

from conftest import AUTH
from contracts.types import VerificationCode
from src.codes import hash_code
from src.policy import MAX_ATTEMPTS

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
    # Replay within TTL with the CORRECT code returns idempotent success.
    again = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert again.status_code == 200
    assert again.json() == {"verified": True, "subject": "discord:1", "email": "a@b.com"}


def test_confirm_replay_wrong_code_refused_and_no_email_leak(client, store):
    # A subject that has already been verified (consumed) and is still within TTL.
    store.create_code(_code(consumed=True))
    r = client.post(
        "/verification/confirm-code",
        headers=AUTH,
        json={"subject": "discord:1", "code": "999999"},  # wrong code
    )
    # Must refuse like the normal wrong-code path and must NOT echo the email.
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_code"
    assert "email" not in r.text
    assert "a@b.com" not in r.text


def test_confirm_replay_correct_code_after_consumed(client, store):
    # Consumed + unexpired + correct code still returns idempotent success (+ email).
    store.create_code(_code(consumed=True))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert r.status_code == 200
    assert r.json() == {"verified": True, "subject": "discord:1", "email": "a@b.com"}


def test_confirm_replay_wrong_code_eventually_locks_out(client, store):
    # Consumed + unexpired: repeated wrong-code replays must trip the same
    # attempt limiting as the normal path (no unlimited brute force, and no
    # early lockout before the cap).
    start_attempts = 0
    store.create_code(_code(consumed=True, attempts=start_attempts))
    # Wrong-code replays return 400 invalid_code until the increment that reaches
    # the cap, which returns 429 too_many_attempts.
    expected_400s = MAX_ATTEMPTS - start_attempts - 1
    for i in range(expected_400s):
        r = client.post(
            "/verification/confirm-code",
            headers=AUTH,
            json={"subject": "discord:1", "code": "999999"},
        )
        assert r.status_code == 400, f"guess {i} should be 400, got {r.status_code}"
        assert r.json()["detail"] == "invalid_code"
    # The next wrong guess crosses the cap and locks out.
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "999999"}
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"
    assert "a@b.com" not in r.text
    # And it stays locked out.
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "999999"}
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"


def test_confirm_replay_correct_code_before_lockout(client, store):
    # A correct-code replay still returns idempotent success while under the cap,
    # and must NOT increment the stored attempt count.
    store.create_code(_code(consumed=True, attempts=4))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert r.status_code == 200
    assert r.json() == {"verified": True, "subject": "discord:1", "email": "a@b.com"}
    assert store.get_code("discord:1").attempts == 4  # unchanged by a correct replay


def test_confirm_replay_expired_consumed_unchanged(client, store):
    # Consumed but expired: 404 no_pending_code regardless of submitted code.
    store.create_code(_code(consumed=True, ttl_min=-1))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "no_pending_code"


def test_confirm_lockout_after_five(client, store):
    store.create_code(_code(attempts=4))
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "000000"}
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"


def test_confirm_locked_out_rejects_even_correct_code(client, store):
    store.create_code(_code(attempts=5))  # already at MAX_ATTEMPTS
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "123456"}
    )  # the CORRECT code
    assert r.status_code == 429
    assert r.json()["detail"] == "too_many_attempts"
    stored = store.get_code("discord:1")
    assert stored.consumed_at is None  # correct code was NOT consumed
    assert stored.attempts == 5  # not incremented past the cap


def test_confirm_no_pending(client):
    r = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "nope", "code": "123456"}
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "no_pending_code"
