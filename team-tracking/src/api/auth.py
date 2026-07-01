from fastapi import Depends, Header, HTTPException, status

from src.config import get_settings


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Verify the API key. Raises 401 if invalid. Returns 'api'."""
    if x_api_key is None or x_api_key != get_settings().api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
    return "api"


def get_actor(
    _: str = Depends(require_api_key),
    x_actor: str | None = Header(default=None, alias="X-Actor"),
) -> str:
    """Composite dependency: enforce API key AND return the actor identifier.

    Prefer explicit X-Actor header (e.g. 'discord-bot', 'sync-job'); fall
    back to 'api'. The returned string is used for created_by/updated_by on
    writes. Import this in routers instead of redefining per-file.
    """
    return x_actor or "api"
