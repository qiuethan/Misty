import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

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


def test_audit_extra_merges_into_line(capsys):
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware, logger_name="test.audit.extra")

    @app.get("/x")
    def x(request: Request):
        request.state.audit_extra = {"model": "claude-sonnet-4-6", "input_tokens": 5}
        return {"ok": True}

    TestClient(app).get("/x")
    entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["input_tokens"] == 5
    assert entry["status"] == 200  # core field still present


def test_audit_extra_cannot_override_reserved_keys(capsys):
    app = FastAPI()
    app.add_middleware(AuditLogMiddleware, logger_name="test.audit.reserved")

    @app.get("/y")
    def y(request: Request):
        request.state.audit_extra = {"status": 999, "path": "/spoofed"}
        return {"ok": True}

    TestClient(app).get("/y")
    entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert entry["status"] == 200      # real status wins
    assert entry["path"] == "/y"       # real path wins
