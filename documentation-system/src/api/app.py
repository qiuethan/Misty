from fastapi import FastAPI

from src.api.middleware import AuditLogMiddleware


def create_app() -> FastAPI:
    app = FastAPI(
        title="UTMIST documentation-system",
        version="0.1.0",
        description="Catalog of URLs: ingest, browse, and own documents.",
        docs_url="/swagger",
    )
    app.add_middleware(AuditLogMiddleware)
    from src.api.routers import docs

    app.include_router(docs.router)
    # sources router is mounted by its own task
    return app


app = create_app()
