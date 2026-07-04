import pytest
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from platform_auth.factory import build_auth
from platform_auth.hashing import generate_key


@dataclass
class _Row:
    id: UUID
    name: str
    scopes: list[str]
    active: bool = True
    revoked_at: datetime | None = None


class _Store:
    def __init__(self):
        self.rows: dict[str, tuple[_Row, str]] = {}   # prefix -> (row, hash)
        self.touched: list[UUID] = []

    def add(self, name, scopes, envelope="tt_"):
        plaintext, prefix, key_hash = generate_key(envelope)
        self.rows[prefix] = (_Row(id=uuid4(), name=name, scopes=scopes), key_hash)
        return plaintext

    def get_api_key_hash(self, prefix):
        r = self.rows.get(prefix)
        return r[1] if r else None

    def get_api_key_by_prefix(self, prefix):
        r = self.rows.get(prefix)
        return r[0] if r else None

    def touch_api_key_last_used(self, api_key_id):
        self.touched.append(api_key_id)


def _app(store, **kw):
    deps = build_auth(lambda: store, envelope="tt_", get_env_key=lambda: "", **kw)
    app = FastAPI()

    @app.get("/read")
    def read(_=Depends(deps.require_scope("people:read"))):
        return {"ok": True}

    @app.get("/whoami")
    def whoami(actor: str = Depends(deps.get_actor)):
        return {"actor": actor}

    return app


def test_valid_key_passes_scope_and_touches_last_used():
    store = _Store()
    key = store.add("bot", ["people:read"])
    client = TestClient(_app(store))
    r = client.get("/read", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert len(store.touched) == 1


def test_missing_scope_403_and_missing_key_401():
    store = _Store()
    key = store.add("bot", ["teams:read"])
    client = TestClient(_app(store))
    assert client.get("/read", headers={"X-API-Key": key}).status_code == 403
    assert client.get("/read").status_code == 401


def test_env_bootstrap_key_grants_admin():
    store = _Store()
    deps = build_auth(lambda: store, envelope="tt_", get_env_key=lambda: "env-secret")
    app = FastAPI()

    @app.get("/read")
    def read(_=Depends(deps.require_scope("people:read"))):
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/read", headers={"X-API-Key": "env-secret"}).status_code == 200


def test_actor_is_key_name():
    store = _Store()
    key = store.add("discord-bot", ["people:read"])
    client = TestClient(_app(store))
    assert client.get("/whoami", headers={"X-API-Key": key}).json() == {"actor": "discord-bot"}


def test_dev_spoof_rejected_in_prod():
    store = _Store()
    key = store.add("spoofer", ["dev:spoof", "people:read"])
    client = TestClient(_app(store, is_prod=lambda: True, enable_dev_spoof=True))
    assert client.get("/read", headers={"X-API-Key": key}).status_code == 403
