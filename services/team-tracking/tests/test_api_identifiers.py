import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_providers, build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.storage.in_memory import InMemoryStorageAdapter

AUTH = {"X-API-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from src.config import get_settings

    get_settings.cache_clear()
    adapter = InMemoryStorageAdapter(
        seed_role_kinds=build_seed_role_kinds(),
        seed_providers=build_seed_providers(),
    )
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def _make_person(client, email="alex@utmist.ca"):
    return client.post(
        "/people", json={"display_name": "Alex", "primary_email": email}, headers=AUTH
    ).json()


def test_link_and_list_identifier(client):
    p = _make_person(client)
    resp = client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "123", "handle": "alex"},
        headers={**AUTH, "X-Actor": "discord-bot"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "discord"
    assert body["external_id"] == "123"
    assert body["created_by"] == "discord-bot"

    listed = client.get(f"/people/{p['id']}/identifiers", headers=AUTH)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_reverse_lookup_returns_person(client):
    p = _make_person(client)
    client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "999"},
        headers=AUTH,
    )
    resp = client.get("/people/by-identifier/discord/999", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["id"] == p["id"]


def test_reverse_lookup_404_when_unlinked(client):
    resp = client.get("/people/by-identifier/discord/nobody", headers=AUTH)
    assert resp.status_code == 404


def test_link_unknown_person_404(client):
    resp = client.post(
        "/people/00000000-0000-0000-0000-000000000000/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers=AUTH,
    )
    assert resp.status_code == 404


def test_link_unknown_provider_400(client):
    p = _make_person(client)
    resp = client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "myspace", "external_id": "1"},
        headers=AUTH,
    )
    assert resp.status_code == 400


def test_duplicate_provider_for_person_409(client):
    p = _make_person(client)
    body = {"provider": "discord", "external_id": "1"}
    client.post(f"/people/{p['id']}/identifiers", json=body, headers=AUTH)
    resp = client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "2"},
        headers=AUTH,
    )
    assert resp.status_code == 409


def test_external_id_owned_by_another_person_409(client):
    p1 = _make_person(client, "a@utmist.ca")
    p2 = _make_person(client, "b@utmist.ca")
    client.post(
        f"/people/{p1['id']}/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers=AUTH,
    )
    resp = client.post(
        f"/people/{p2['id']}/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers=AUTH,
    )
    assert resp.status_code == 409


def test_patch_handle(client):
    p = _make_person(client)
    client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "1", "handle": "old"},
        headers=AUTH,
    )
    resp = client.patch(
        f"/people/{p['id']}/identifiers/discord", json={"handle": "new"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["handle"] == "new"


def test_patch_unknown_link_404(client):
    p = _make_person(client)
    resp = client.patch(f"/people/{p['id']}/identifiers/github", json={"handle": "x"}, headers=AUTH)
    assert resp.status_code == 404


def test_delete_identifier(client):
    p = _make_person(client)
    client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers=AUTH,
    )
    resp = client.delete(f"/people/{p['id']}/identifiers/discord", headers=AUTH)
    assert resp.status_code == 204
    assert client.delete(f"/people/{p['id']}/identifiers/discord", headers=AUTH).status_code == 404


def test_patch_unknown_person_404(client):
    resp = client.patch(
        "/people/00000000-0000-0000-0000-000000000000/identifiers/discord",
        json={"handle": "x"},
        headers=AUTH,
    )
    assert resp.status_code == 404


def test_delete_unknown_person_404(client):
    resp = client.delete(
        "/people/00000000-0000-0000-0000-000000000000/identifiers/discord",
        headers=AUTH,
    )
    assert resp.status_code == 404


def test_patch_external_id_collision_409(client):
    p1 = _make_person(client, "a@utmist.ca")
    p2 = _make_person(client, "b@utmist.ca")
    client.post(
        f"/people/{p1['id']}/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers=AUTH,
    )
    client.post(
        f"/people/{p2['id']}/identifiers",
        json={"provider": "discord", "external_id": "2"},
        headers=AUTH,
    )
    resp = client.patch(
        f"/people/{p2['id']}/identifiers/discord", json={"external_id": "1"}, headers=AUTH
    )
    assert resp.status_code == 409


def test_identifier_write_denied_without_scope(client):
    from src.api.hashing import generate_key

    p = _make_person(client)
    adapter = client.app.dependency_overrides[get_storage]()
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="reader",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["identifiers:read"],
        actor="admin",
    )
    resp = client.post(
        f"/people/{p['id']}/identifiers",
        json={"provider": "discord", "external_id": "1"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 403
    assert "identifiers:write" in resp.json()["detail"]


def test_add_email_endpoint_creates_and_is_idempotent(client):
    pid = _make_person(client)["id"]
    r1 = client.post(f"/people/{pid}/emails", headers=AUTH, json={"email": "New@X.com"})
    assert r1.status_code == 201 and r1.json()["provider"] == "email"
    assert r1.json()["external_id"] == "new@x.com"
    r2 = client.post(f"/people/{pid}/emails", headers=AUTH, json={"email": "new@x.com"})
    assert r2.status_code == 201 and r2.json()["id"] == r1.json()["id"]
    ids = client.get(f"/people/{pid}/identifiers", headers=AUTH).json()
    assert sum(i["provider"] == "email" for i in ids) == 1


def test_add_email_own_primary_creates_and_is_idempotent(client):
    p = _make_person(client, "me@x.com")
    pid = p["id"]
    r1 = client.post(f"/people/{pid}/emails", headers=AUTH, json={"email": p["primary_email"]})
    assert r1.status_code == 201 and r1.json()["provider"] == "email"
    assert r1.json()["external_id"] == p["primary_email"]
    r2 = client.post(f"/people/{pid}/emails", headers=AUTH, json={"email": p["primary_email"]})
    assert r2.status_code == 201 and r2.json()["id"] == r1.json()["id"]


def test_add_email_rejects_another_persons(client):
    a = _make_person(client, "a@x.com")["id"]
    b = _make_person(client, "b@x.com")["id"]
    client.post(f"/people/{a}/emails", headers=AUTH, json={"email": "s@x.com"})
    r = client.post(f"/people/{b}/emails", headers=AUTH, json={"email": "s@x.com"})
    assert r.status_code == 409 and r.json()["detail"] == "email_registered_to_another"


def test_generic_identifier_endpoints_reject_email(client):
    pid = _make_person(client)["id"]
    r = client.post(
        f"/people/{pid}/identifiers",
        headers=AUTH,
        json={"provider": "email", "external_id": "e@x.com"},
    )
    assert r.status_code == 409 and r.json()["detail"] == "email_not_addressable_by_provider"


def test_reverse_lookup_by_email_identifier(client):
    pid = _make_person(client, "p2@x.com")["id"]
    client.post(f"/people/{pid}/emails", headers=AUTH, json={"email": "look@x.com"})
    r = client.get("/people/by-identifier/email/look@x.com", headers=AUTH)
    assert r.status_code == 200 and r.json()["id"] == pid
