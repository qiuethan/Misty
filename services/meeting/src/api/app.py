from fastapi import FastAPI

from src.api.middleware import AuditLogMiddleware
from src.config import verify_production_secrets


def create_app() -> FastAPI:
    verify_production_secrets()

    from src.api.deps import get_key_store

    get_key_store()  # fail fast on a malformed CONSUMER_KEYS at boot, not first request

    app = FastAPI(
        title="UTMIST meeting",
        version="0.1.0",
        description="Meeting recording + transcription service.",
    )
    app.add_middleware(AuditLogMiddleware, logger_name="meeting.audit")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
