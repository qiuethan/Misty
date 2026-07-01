from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import StorageAdapter
from contracts.types import RoleKind
from src.api.auth import AuthedKey, require_scope
from src.api.deps import get_storage

router = APIRouter(prefix="/role_kinds", tags=["role_kinds"])


@router.get("", response_model=list[RoleKind])
def list_role_kinds(
    active_only: bool = False,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("role_kinds:read")),
) -> list[RoleKind]:
    return storage.list_role_kinds(active_only=active_only)


@router.get("/{role_kind_id}", response_model=RoleKind)
def get_role_kind(
    role_kind_id: str,
    storage: StorageAdapter = Depends(get_storage),
    _: AuthedKey = Depends(require_scope("role_kinds:read")),
) -> RoleKind:
    rk = storage.get_role_kind(role_kind_id)
    if rk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_kind not found")
    return rk
