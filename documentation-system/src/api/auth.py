import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from starlette.requests import Request

from contracts.storage import StorageAdapter
from src.api.deps import get_storage
from src.api.hashing import parse_prefix, verify_key
from src.config import get_settings

ADMIN_SCOPE = "admin"
_BOOTSTRAP_KEY_NAME = "env-bootstrap"


@dataclass(frozen=True)
class AuthedKey:
    name: str
    scopes: frozenset[str]
    is_bootstrap: bool = False

    def has_scope(self, scope: str) -> bool:
        return ADMIN_SCOPE in self.scopes or scope in self.scopes


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key"
    )


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    storage: StorageAdapter = Depends(get_storage),
) -> AuthedKey:
    if not x_api_key:
        raise _unauthorized()
    prefix = parse_prefix(x_api_key)
    if prefix is not None:
        key_hash = storage.get_api_key_hash(prefix)
        if key_hash is not None and verify_key(x_api_key, key_hash):
            row = storage.get_api_key_by_prefix(prefix)
            if row is not None and row.active and row.revoked_at is None:
                storage.touch_api_key_last_used(row.id)
                authed = AuthedKey(name=row.name, scopes=frozenset(row.scopes), is_bootstrap=False)
                request.state.auth_key = authed
                return authed
        raise _unauthorized()
    env_key = get_settings().api_key
    if env_key and secrets.compare_digest(x_api_key.encode(), env_key.encode()):
        authed = AuthedKey(
            name=_BOOTSTRAP_KEY_NAME, scopes=frozenset({ADMIN_SCOPE}), is_bootstrap=True
        )
        request.state.auth_key = authed
        return authed
    raise _unauthorized()


def require_scope(scope: str):
    def _dep(key: AuthedKey = Depends(require_api_key)) -> AuthedKey:
        if not key.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"missing scope: {scope}"
            )
        return key
    return _dep


def get_actor(key: AuthedKey = Depends(require_api_key)) -> str:
    """Actor for created_by/updated_by is the attested key name. There is no
    X-Actor header — a caller cannot claim to be someone else."""
    return key.name
