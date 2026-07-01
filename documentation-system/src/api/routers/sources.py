from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import StorageAdapter
from contracts.types import Source
from src.api.auth import AuthedKey, require_scope
from src.api.deps import get_storage

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[Source])
def list_sources(
    active_only: bool = False,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("docs:read")),
) -> list[Source]:
    return storage.list_sources(active_only=active_only)


@router.get("/{source_id}", response_model=Source)
def get_source(
    source_id: str,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("docs:read")),
) -> Source:
    source = storage.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return source
