from fastapi.testclient import TestClient

from src.api.app import create_app


def test_openapi_lists_endpoints():
    client = TestClient(create_app())
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/verification/request-code" in paths
    assert "/verification/confirm-code" in paths
    assert "/health" in paths
