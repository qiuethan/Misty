from fastapi import FastAPI


def create_app() -> FastAPI:
    from src.api.routers import people  # add teams, role_kinds, memberships as tasks 10-12 land

    app = FastAPI(
        title="UTMIST team-tracking",
        version="0.1.0",
        description="Source of truth for people, teams, and memberships.",
    )
    app.include_router(people.router)
    return app


app = create_app()
