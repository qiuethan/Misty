from fastapi.testclient import TestClient

from src.api.app import create_app


def test_health_ok_without_auth():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
