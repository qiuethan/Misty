from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DirectoryBase(BaseModel):
    """Common audit fields on every stored record."""

    model_config = ConfigDict(frozen=False, extra="forbid")

    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class Source(DirectoryBase):
    id: str  # slug PK, e.g. "web", "gdocs"
    label: str
    url_patterns: list[str]
    requires_auth: bool
    has_api: bool
    content_fetch_enabled: bool
    active: bool = True


class Doc(DirectoryBase):
    id: UUID
    url: str
    url_normalized: str
    title: str | None = None
    source_id: str
    description: str | None = None
    owning_team_id: UUID | None = None
    owning_team_label: str | None = None
    owning_person_id: UUID | None = None
    owning_person_label: str | None = None
    content_snapshot: str | None = None
    fetched_at: datetime | None = None
    active: bool = True
    tags: list[str] = []


# --- Input DTOs ---


class DocIngest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    source_id: str | None = None
    title: str | None = None
    description: str | None = None
    owning_team_id: UUID | None = None
    owning_person_id: UUID | None = None
    tags: list[str] = []


class DocUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    description: str | None = None
    owning_team_id: UUID | None = None
    owning_person_id: UUID | None = None
    active: bool | None = None


# --- Results ---


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc: Doc
    created: bool
    warnings: list[str] = []


# --- API keys (Level 2 security) ---


class ApiKey(DirectoryBase):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    active: bool = True
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    scopes: list[str] = []


class IssuedApiKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plaintext: str
    api_key: ApiKey
