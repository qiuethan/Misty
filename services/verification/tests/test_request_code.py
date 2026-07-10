from conftest import AUTH


def test_request_code_sends_and_returns_202(client, store, email):
    r = client.post(
        "/verification/request-code",
        headers=AUTH,
        json={"subject": "discord:1", "email": "A@B.com"},
    )
    assert r.status_code == 202
    assert len(email.sent) == 1
    assert email.sent[0].to == "a@b.com"  # normalized
    assert email.last_code() is not None
    stored = store.get_code("discord:1")
    assert stored is not None and stored.consumed_at is None
    assert stored.email == "a@b.com"


def test_request_code_rate_limited(client, email):
    body = {"subject": "discord:1", "email": "a@b.com"}
    assert client.post("/verification/request-code", headers=AUTH, json=body).status_code == 202
    r = client.post("/verification/request-code", headers=AUTH, json=body)
    assert r.status_code == 429
    assert r.json()["detail"] == "rate_limited"
    assert len(email.sent) == 1  # second request did not send


def test_request_code_email_failure_returns_502_and_persists_nothing(client, store):
    from src.api.deps import get_email_sender
    from src.email.base import EmailSendError

    class _Boom:
        def send(self, *, to, subject, body):
            raise EmailSendError("delivery failed")

    client.app.dependency_overrides[get_email_sender] = lambda: _Boom()
    r = client.post(
        "/verification/request-code",
        headers=AUTH,
        json={"subject": "discord:9", "email": "a@b.com"},
    )
    assert r.status_code == 502
    assert r.json()["detail"] == "email_send_failed"
    # A failed send must not leave a code behind (else the user is rate-limited).
    assert store.get_code("discord:9") is None
