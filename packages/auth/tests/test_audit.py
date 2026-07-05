import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_auth import AuditLogMiddleware


def test_emits_one_json_line_per_request(capsys):
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware, logger_name="test.audit")

    @app.get("/ping")
    def ping():
        return {"ok": True}

    TestClient(app).get("/ping")
    out = capsys.readouterr().out.strip().splitlines()
    entry = json.loads(out[-1])
    assert entry["method"] == "GET"
    assert entry["path"] == "/ping"
    assert entry["status"] == 200
    assert entry["key_name"] is None
