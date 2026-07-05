from fastapi import FastAPI

from platform_auth import AuditLogMiddleware

from src.config import verify_production_secrets


def create_app() -> FastAPI:
    verify_production_secrets()

    app = FastAPI(
        title="UTMIST verification",
        version="0.1.0",
        description="Proves control of an email for a given subject via one-time codes.",
    )
    app.add_middleware(AuditLogMiddleware, logger_name="verification.audit")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Routers are included in Task 5 (endpoints).
    return app


app = create_app()
