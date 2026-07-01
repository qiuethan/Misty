from fastapi import FastAPI


def create_app() -> FastAPI:
    from src.api.routers import memberships, people, role_kinds, teams

    app = FastAPI(
        title="UTMIST team-tracking",
        version="0.1.0",
        description="Source of truth for people, teams, and memberships.",
    )
    app.include_router(people.router)
    app.include_router(teams.router)
    app.include_router(role_kinds.router)
    app.include_router(memberships.router)
    return app


app = create_app()
