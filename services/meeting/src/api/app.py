import logging
from fastapi import FastAPI

from src.api.middleware import AuditLogMiddleware
from src.api.routers.meetings import router as meetings_router
from src.config import verify_production_secrets


_SINGLE_INSTANCE_NOTE = (
    "meeting holds every live session in process memory: a session's WebSocket, "
    "/transcript polls and /stop MUST all reach the same process. Run exactly one "
    "instance -- one replica, one uvicorn worker. Replica count and region are "
    "dashboard settings; railway.json pins only overlapSeconds=0, so a redeploy "
    "never briefly runs two. NOTE that this does not make a redeploy safe: the "
    "outgoing process keeps its sessions in memory while it drains, but routing "
    "has already moved on, so any meeting in progress loses its /stop and its "
    "minutes. Redeploy between meetings until sessions live outside the process."
)


def create_app() -> FastAPI:
    verify_production_secrets()

    from src.api.deps import get_key_store

    get_key_store()  # fail fast on a malformed CONSUMER_KEYS at boot, not first request

    logging.getLogger(__name__).info(_SINGLE_INSTANCE_NOTE)
    app = FastAPI(
        title="UTMIST meeting",
        version="0.1.0",
        description="Meeting recording + transcription service.",
    )
    app.add_middleware(AuditLogMiddleware, logger_name="meeting.audit")
    app.include_router(meetings_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
