from datetime import datetime, timedelta, timezone

from conftest import AUTH
from contracts.types import VerificationCode
from src.codes import hash_code

SECRET = "test-hmac-secret"


def _code(subject, code):
    now = datetime.now(timezone.utc)
    return VerificationCode(
        subject=subject,
        email="a@b.com",
        code_hash=hash_code(code, SECRET),
        expires_at=now + timedelta(minutes=10),
        attempts=0,
        consumed_at=None,
        created_at=now,
    )


def test_codes_scoped_per_subject(client, store):
    store.create_code(_code("discord:1", "111111"))
    store.create_code(_code("discord:2", "222222"))
    # subject 2's code must not confirm subject 1
    wrong = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "222222"}
    )
    assert wrong.status_code == 400
    right = client.post(
        "/verification/confirm-code", headers=AUTH, json={"subject": "discord:1", "code": "111111"}
    )
    assert right.status_code == 200
