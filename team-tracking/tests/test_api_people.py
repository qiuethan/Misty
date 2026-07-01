import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.storage.in_memory import InMemoryStorageAdapter

AUTH = {"X-API-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    # clear the lru_cache on get_settings so the new env value takes effect
    from src.config import get_settings

    get_settings.cache_clear()

    adapter = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def test_create_person_returns_201(client):
    resp = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["display_name"] == "Alex"
    assert body["primary_email"] == "alex@utmist.ca"
    assert "id" in body


def test_create_person_requires_api_key(client):
    resp = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
    )
    assert resp.status_code == 401


def test_get_person(client):
    created = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    ).json()
    resp = client.get(f"/people/{created['id']}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alex"


def test_get_person_not_found(client):
    resp = client.get("/people/00000000-0000-0000-0000-000000000000", headers=AUTH)
    assert resp.status_code == 404


def test_list_people(client):
    client.post(
        "/people",
        json={"display_name": "A", "primary_email": "a@utmist.ca"},
        headers=AUTH,
    )
    client.post(
        "/people",
        json={"display_name": "B", "primary_email": "b@utmist.ca"},
        headers=AUTH,
    )
    resp = client.get("/people", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_person(client):
    created = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    ).json()
    resp = client.patch(
        f"/people/{created['id']}",
        json={"display_name": "Alexandra"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alexandra"


def test_duplicate_email_returns_409(client):
    client.post(
        "/people",
        json={"display_name": "A", "primary_email": "a@utmist.ca"},
        headers=AUTH,
    )
    resp = client.post(
        "/people",
        json={"display_name": "B", "primary_email": "A@utmist.ca"},
        headers=AUTH,
    )
    assert resp.status_code == 409


def test_x_actor_header_used_for_created_by(client):
    created = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers={**AUTH, "X-Actor": "discord-bot"},
    ).json()
    assert created["created_by"] == "discord-bot"


def test_people_write_denied_without_scope(client):
    """A DB-issued key with only people:read scope gets 403 on POST /people."""
    from src.api.hashing import generate_key

    adapter = client.app.dependency_overrides[get_storage]()
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="reader",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["people:read"],
        actor="admin",
    )
    resp = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 403
    assert "people:write" in resp.json()["detail"]


def test_get_person_by_email(client):
    client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    )
    resp = client.get("/people/by-email/alex@utmist.ca", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Alex"


def test_get_person_by_email_not_found(client):
    resp = client.get("/people/by-email/nobody@utmist.ca", headers=AUTH)
    assert resp.status_code == 404


def test_get_person_by_email_is_case_insensitive(client):
    client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    )
    resp = client.get("/people/by-email/Alex@UTMIST.ca", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["primary_email"] == "alex@utmist.ca"


def test_get_person_by_email_requires_api_key(client):
    resp = client.get("/people/by-email/alex@utmist.ca")
    assert resp.status_code == 401
