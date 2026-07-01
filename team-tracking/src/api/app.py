from fastapi import FastAPI

from src.api.middleware import AuditLogMiddleware


def create_app() -> FastAPI:
    from src.api.routers import (
        identifiers,
        memberships,
        people,
        providers,
        role_kinds,
        teams,
    )

    app = FastAPI(
        title="UTMIST team-tracking",
        version="0.1.0",
        description="Source of truth for people, teams, and memberships.",
    )
    app.add_middleware(AuditLogMiddleware)
    app.include_router(people.router)
    app.include_router(teams.router)
    app.include_router(role_kinds.router)
    app.include_router(memberships.router)
    app.include_router(providers.router)
    app.include_router(identifiers.router)
    return app


app = create_app()
