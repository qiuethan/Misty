def test_missing_key_401(client):
    r = client.post("/verification/request-code", json={"subject": "s", "email": "a@b.com"})
    assert r.status_code == 401


def test_wrong_key_401(client):
    r = client.post(
        "/verification/request-code",
        headers={"X-API-Key": "nope"},
        json={"subject": "s", "email": "a@b.com"},
    )
    assert r.status_code == 401
