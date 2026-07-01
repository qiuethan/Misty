"""Structured audit-log middleware.

Every request produces exactly one JSON log line to stdout. Downstream log
aggregation (Loki, CloudWatch, Datadog, journald, etc.) picks it up.

Log line shape:
    {
        "ts": "2026-07-01T12:34:56.789Z",  # UTC ISO-8601
        "request_id": "b8c...uuid",
        "method": "POST",
        "path": "/people",
        "status": 201,
        "duration_ms": 42,
        "key_name": "discord-bot",  # or "env-bootstrap" or None
        "remote": "203.0.113.7",
        "is_bootstrap": false        # true if env grace-period key was used
    }

The middleware installs a per-request `request.state.auth_key: AuthedKey | None`
that auth resolves; the audit log reads it after the handler runs. If auth
failed (401/403), key_name is null.
"""

import json
import logging
import sys
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("team_tracking.audit")


class _SysStdoutStream:
    """A stream that resolves sys.stdout at write time.

    This ensures pytest's capsys fixture can capture output even though the
    handler is created once — logging.StreamHandler captures the stream object
    at creation, but we always delegate to the *current* sys.stdout.
    """

    def write(self, msg: str) -> int:
        return sys.stdout.write(msg)

    def flush(self) -> None:
        sys.stdout.flush()


def _configure_audit_logger() -> None:
    """One-time setup: attach a stdout handler that emits raw JSON lines.

    Idempotent — safe to call multiple times (create_app may be called by tests).
    """
    if logger.handlers:
        return
    handler = logging.StreamHandler(_SysStdoutStream())  # type: ignore[arg-type]
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emits one JSON log line per request after the handler completes.

    Never fails the request — if logging itself raises, we swallow it and
    still return the response.
    """

    async def dispatch(self, request: Request, call_next):
        _configure_audit_logger()
        request_id = str(uuid4())
        request.state.request_id = request_id
        start = time.monotonic()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            try:
                auth_key = getattr(request.state, "auth_key", None)
                # Prefer the X-Forwarded-For / X-Real-IP header (set by reverse proxy)
                # over the direct client, so we log the real caller when behind Caddy/nginx.
                remote = (
                    request.headers.get("X-Real-IP")
                    or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or None)
                    or (request.client.host if request.client else None)
                )
                entry = {
                    "ts": _now_iso(),
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code if response is not None else 500,
                    "duration_ms": duration_ms,
                    "key_name": auth_key.name if auth_key else None,
                    "is_bootstrap": auth_key.is_bootstrap if auth_key else False,
                    "remote": remote,
                }
                logger.info(json.dumps(entry, separators=(",", ":")))
            except Exception:
                # Never let the audit log fail the request. Log-and-swallow.
                pass


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
