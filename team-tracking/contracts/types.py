import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


def _normalize_email(v: str) -> str:
    """Canonical email normalization: strip whitespace and lowercase."""
    return v.strip().lower()


class DirectoryBase(BaseModel):
    """Common audit fields on every directory record.

    Subclasses declare their own `id` with the appropriate concrete type
    (UUID for people/teams/memberships, str slug for role_kinds).
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class Person(DirectoryBase):
    id: UUID
    display_name: str
    primary_email: str
    active: bool = True

    @field_validator("primary_email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class Team(DirectoryBase):
    id: UUID
    slug: str
    label: str
    description: str | None = None
    parent_id: UUID | None = None
    active: bool = True


class RoleKind(DirectoryBase):
    id: str  # slug PK, e.g. "executive", "director", "lead", "member"
    label: str
    description: str | None = None
    active: bool = True


class TeamMembership(DirectoryBase):
    id: UUID
    person_id: UUID
    team_id: UUID
    role_kind_id: str
    is_team_admin: bool = False
    started_at: date
    ended_at: date | None = None


# --- Input DTOs (for API create/update payloads) ---


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str
    primary_email: str

    @field_validator("primary_email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = None
    primary_email: str | None = None
    active: bool | None = None

    @field_validator("primary_email")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        return _normalize_email(v) if v is not None else None


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    label: str
    description: str | None = None
    parent_id: UUID | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9_.]+", v):
            raise ValueError("slug must match [a-z0-9_.]+")
        return v


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str | None = None
    label: str | None = None
    description: str | None = None
    parent_id: UUID | None = None
    active: bool | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[a-z0-9_.]+", v):
            raise ValueError("slug must match [a-z0-9_.]+")
        return v


class TeamMembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: UUID
    team_id: UUID
    role_kind_id: str = "member"
    is_team_admin: bool = False
    started_at: date | None = None  # defaults to today at storage layer
    ended_at: date | None = None


class TeamMembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_kind_id: str | None = None
    is_team_admin: bool | None = None
    ended_at: date | None = None
