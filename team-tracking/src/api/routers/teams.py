from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import StorageAdapter
from contracts.types import Team, TeamCreate, TeamUpdate
from src.api.auth import get_actor, require_api_key
from src.api.deps import get_storage

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=Team, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    storage: StorageAdapter = Depends(get_storage),
    actor: str = Depends(get_actor),
) -> Team:
    try:
        return storage.create_team(payload, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=list[Team])
def list_teams(
    active_only: bool = False,
    storage: StorageAdapter = Depends(get_storage),
    _: str = Depends(require_api_key),
) -> list[Team]:
    return storage.list_teams(active_only=active_only)


@router.get("/by-slug/{slug}", response_model=Team)
def get_team_by_slug(
    slug: str,
    storage: StorageAdapter = Depends(get_storage),
    _: str = Depends(require_api_key),
) -> Team:
    team = storage.get_team_by_slug(slug)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    return team


@router.get("/{team_id}", response_model=Team)
def get_team(
    team_id: UUID,
    storage: StorageAdapter = Depends(get_storage),
    _: str = Depends(require_api_key),
) -> Team:
    team = storage.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    return team


@router.patch("/{team_id}", response_model=Team)
def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    storage: StorageAdapter = Depends(get_storage),
    actor: str = Depends(get_actor),
) -> Team:
    try:
        updated = storage.update_team(team_id, payload, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    return updated
