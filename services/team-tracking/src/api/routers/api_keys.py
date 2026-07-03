"""Router for API-key introspection.

Currently exposes exactly one endpoint: GET /api-keys/self.
Callers use this to learn what scopes their own key has — used by the
discord-bot to decide whether it's allowed to enable spoof mode.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.auth import AuthedKey, require_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class SelfKey(BaseModel):
    """Response body for GET /api-keys/self."""

    name: str
    scopes: list[str]


@router.get("/self", response_model=SelfKey)
def get_self_key(key: AuthedKey = Depends(require_api_key)) -> SelfKey:
    """Return the calling key's own name and scopes.

    No scope beyond a valid API key is required.
    """
    return SelfKey(name=key.name, scopes=sorted(key.scopes))
