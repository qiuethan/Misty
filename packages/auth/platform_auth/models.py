"""Auth value types and the ports the library needs from a host service."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

ADMIN_SCOPE = "admin"
DEV_SPOOF_SCOPE = "dev:spoof"


@dataclass(frozen=True)
class AuthedKey:
    """Resolved caller identity. `name` is the actor for created_by/updated_by;
    `scopes` gates scoped endpoints; `is_bootstrap` flags env-based auth."""

    name: str
    scopes: frozenset[str]
    is_bootstrap: bool = False

    def has_scope(self, scope: str) -> bool:
        return ADMIN_SCOPE in self.scopes or scope in self.scopes


@runtime_checkable
class ApiKeyRow(Protocol):
    """The subset of a stored API-key row the auth path reads."""

    id: UUID
    name: str
    scopes: list[str]
    active: bool
    revoked_at: datetime | None


class ApiKeyStore(Protocol):
    """The subset of a service's storage adapter the auth path calls.

    A service's existing StorageAdapter satisfies this structurally — no
    changes required on the storage side.
    """

    def get_api_key_hash(self, prefix: str) -> str | None: ...
    def get_api_key_by_prefix(self, prefix: str) -> ApiKeyRow | None: ...
    def touch_api_key_last_used(self, api_key_id: UUID) -> None: ...
