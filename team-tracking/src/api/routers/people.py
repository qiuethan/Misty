from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from contracts.storage import StorageAdapter
from contracts.types import Person, PersonCreate, PersonUpdate
from src.api.auth import get_actor, require_api_key
from src.api.deps import get_storage

router = APIRouter(prefix="/people", tags=["people"])


@router.post("", response_model=Person, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonCreate,
    storage: StorageAdapter = Depends(get_storage),
    actor: str = Depends(get_actor),
) -> Person:
    try:
        return storage.create_person(payload, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=list[Person])
def list_people(
    active_only: bool = False,
    storage: StorageAdapter = Depends(get_storage),
    _: str = Depends(require_api_key),
) -> list[Person]:
    return storage.list_people(active_only=active_only)


@router.get("/{person_id}", response_model=Person)
def get_person(
    person_id: UUID,
    storage: StorageAdapter = Depends(get_storage),
    _: str = Depends(require_api_key),
) -> Person:
    person = storage.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="person not found")
    return person


@router.patch("/{person_id}", response_model=Person)
def update_person(
    person_id: UUID,
    payload: PersonUpdate,
    storage: StorageAdapter = Depends(get_storage),
    actor: str = Depends(get_actor),
) -> Person:
    try:
        updated = storage.update_person(person_id, payload, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="person not found")
    return updated
