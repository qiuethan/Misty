from fastapi import FastAPI

from src.config import verify_production_secrets


def create_app() -> FastAPI:
    verify_production_secrets()

    app = FastAPI(
        title="UTMIST connectors",
        version="0.1.0",
        description="Shared internal source-connector API (document URL to text).",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
