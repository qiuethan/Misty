"""API-key authentication for the team-tracking service.

Two-tier auth model:
1. **DB-issued keys** (primary): looked up by prefix, verified via argon2 hash,
   scoped per consumer. See src/cli.py for issuance.
2. **Env grace-period key** (legacy): the `API_KEY` env var. If set and matched,
   grants admin scope. Deprecated — use DB keys instead.

Every request handler that mutates data should depend on `require_scope("<scope>")`.
Read-only endpoints may depend on `require_scope("<domain>:read")` OR on
`require_api_key` (which returns a resolved key with no scope check).
"""

import logging
import json
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
DEV_SPOOF_SCOPE = "dev:spoof"
_PROD_ENV = "production"

_audit_logger = logging.getLogger("team_tracking.audit")


@dataclass(frozen=True)
class AuthedKey:
    """Resolved caller identity. `name` becomes the actor for created_by/updated_by.
    `scopes` gates access to scoped endpoints. `is_bootstrap` flags env-based auth
    (for the audit log to distinguish from a proper DB-issued key)."""

    name: str
    scopes: frozenset[str]
    is_bootstrap: bool = False

    def has_scope(self, scope: str) -> bool:
        return ADMIN_SCOPE in self.scopes or scope in self.scopes


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key",
    )


def _enforce_dev_scope_environment(authed: "AuthedKey") -> None:
    """403 if a dev:spoof-scoped key is presented against a production directory.

    Literal-check, not `has_scope` — an `admin` wildcard must NOT bypass this.
    """
    if DEV_SPOOF_SCOPE not in authed.scopes:
        return
    if get_settings().tt_env != _PROD_ENV:
        return
    _audit_logger.warning(
        json.dumps(
            {
                "event": "dev_spoof_key_rejected",
                "scope": DEV_SPOOF_SCOPE,
                "tt_env": _PROD_ENV,
                "key_name": authed.name,
            }
        )
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="dev:spoof keys forbidden in production",
    )


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    storage: StorageAdapter = Depends(get_storage),
) -> AuthedKey:
    """Resolve X-API-Key to an AuthedKey. Raises 401 on any failure.

    Order:
    1. If empty/missing, 401.
    2. If it parses as a DB-key format (tt_<prefix>_<secret>), look up the
       stored hash by prefix and verify. On success, touch last_used_at and
       return the resolved key.
    3. If it matches the env API_KEY (and API_KEY is non-empty), return the
       bootstrap AuthedKey with admin scope.
    4. Otherwise 401.

    All failure modes return the same 401 with the same detail — never leak
    which path failed.
    """
    if not x_api_key:
        raise _unauthorized()

    # Path 1: DB-issued key
    prefix = parse_prefix(x_api_key)
    if prefix is not None:
        key_hash = storage.get_api_key_hash(prefix)
        if key_hash is not None and verify_key(x_api_key, key_hash):
            row = storage.get_api_key_by_prefix(prefix)
            if row is not None and row.active and row.revoked_at is None:
                authed = AuthedKey(
                    name=row.name,
                    scopes=frozenset(row.scopes),
                    is_bootstrap=False,
                )
                request.state.auth_key = authed
                _enforce_dev_scope_environment(authed)
                storage.touch_api_key_last_used(row.id)
                return authed
        # DB key present but failed — fall through to 401 (never fall through
        # to env-key check for a well-formed DB key attempt; prevents an
        # attacker mixing formats).
        raise _unauthorized()

    # Path 2: env grace-period key
    env_key = get_settings().api_key
    if env_key and secrets.compare_digest(x_api_key.encode("utf-8"), env_key.encode("utf-8")):
        authed = AuthedKey(
            name=_BOOTSTRAP_KEY_NAME,
            scopes=frozenset({ADMIN_SCOPE}),
            is_bootstrap=True,
        )
        request.state.auth_key = authed
        _enforce_dev_scope_environment(authed)
        return authed

    raise _unauthorized()


def require_scope(scope: str):
    """Dependency factory: enforce that the caller has `scope` (or admin).

    Usage:
        @router.post("", ...)
        def create_person(
            payload: PersonCreate,
            key: AuthedKey = Depends(require_scope("people:write")),
            ...
        ):
    """

    def _dep(key: AuthedKey = Depends(require_api_key)) -> AuthedKey:
        if not key.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing scope: {scope}",
            )
        return key

    return _dep


def get_actor(
    x_actor: str | None = Header(default=None, alias="X-Actor"),
    key: AuthedKey = Depends(require_api_key),
) -> str:
    """Return the actor identifier for created_by/updated_by stamping.

    Level 2: actor is the KEY NAME (cryptographically attested), not the
    self-declared X-Actor header. X-Actor is still accepted for backward
    compat but ignored for DB-issued keys — a leaked key can no longer claim
    to be someone else.

    Exception: for the env bootstrap key, X-Actor is honoured to preserve
    backward compatibility with existing callers that declare their identity
    via the header. This exception is removed in L2-4 when all consumers
    migrate to DB-issued keys.
    """
    if key.is_bootstrap and x_actor:
        return x_actor
    return key.name
