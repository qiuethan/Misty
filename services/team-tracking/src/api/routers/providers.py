from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import StorageAdapter
from contracts.types import Provider
from src.api.auth import AuthedKey, require_scope
from src.api.deps import get_storage

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=list[Provider])
def list_providers(
    active_only: bool = False,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("providers:read")),
) -> list[Provider]:
    return storage.list_providers(active_only=active_only)


@router.get("/{provider_id}", response_model=Provider)
def get_provider(
    provider_id: str,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("providers:read")),
) -> Provider:
    provider = storage.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="provider not found")
    return provider
