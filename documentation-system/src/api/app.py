from fastapi import FastAPI

from src.api.middleware import AuditLogMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="UTMIST documentation-system",
        version="0.1.0",
        description="Catalog of URLs: ingest, browse, and own documents.",
    )
    app.add_middleware(AuditLogMiddleware)
    # routers are mounted by their own tasks (docs, sources)
    return app


app = create_app()
