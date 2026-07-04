"""Factory that builds a service's FastAPI auth dependencies.

The library holds no service config. `build_auth` receives the service's store
dependency + config as parameters and returns closures. All failure modes
return the same 401 — never leak which path failed.
"""

import json
import logging
import secrets
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from starlette.requests import Request

from platform_auth.hashing import parse_prefix, verify_key
from platform_auth.models import (
    ADMIN_SCOPE,
    DEV_SPOOF_SCOPE,
    ApiKeyStore,
    AuthedKey,
)

_BOOTSTRAP_KEY_NAME = "env-bootstrap"


@dataclass(frozen=True)
class AuthDeps:
    require_api_key: Callable
    require_scope: Callable
    get_actor: Callable


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing X-API-Key",
    )


def build_auth(
    get_store: Callable[..., ApiKeyStore],
    *,
    envelope: str,
    get_env_key: Callable[[], str | None],
    is_prod: Callable[[], bool] = lambda: False,
    enable_dev_spoof: bool = False,
    bootstrap_honors_x_actor: bool = False,
    audit_logger_name: str = "platform.audit",
) -> AuthDeps:
    audit = logging.getLogger(audit_logger_name)

    def _enforce_dev_scope_environment(authed: AuthedKey) -> None:
        # Literal check, not has_scope — an admin wildcard must NOT bypass this.
        if not enable_dev_spoof or DEV_SPOOF_SCOPE not in authed.scopes:
            return
        if not is_prod():
            return
        audit.warning(json.dumps({
            "event": "dev_spoof_key_rejected",
            "scope": DEV_SPOOF_SCOPE,
            "key_name": authed.name,
        }))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="dev:spoof keys forbidden in production",
        )

    def require_api_key(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        store: ApiKeyStore = Depends(get_store),
    ) -> AuthedKey:
        if not x_api_key:
            raise _unauthorized()

        prefix = parse_prefix(x_api_key, envelope)
        if prefix is not None:
            key_hash = store.get_api_key_hash(prefix)
            if key_hash is not None and verify_key(x_api_key, key_hash):
                row = store.get_api_key_by_prefix(prefix)
                if row is not None and row.active and row.revoked_at is None:
                    authed = AuthedKey(
                        name=row.name, scopes=frozenset(row.scopes), is_bootstrap=False
                    )
                    request.state.auth_key = authed
                    _enforce_dev_scope_environment(authed)
                    store.touch_api_key_last_used(row.id)
                    return authed
            # Well-formed DB key that failed: never fall through to env-key check.
            raise _unauthorized()

        env_key = get_env_key()
        if env_key and secrets.compare_digest(x_api_key.encode(), env_key.encode()):
            authed = AuthedKey(
                name=_BOOTSTRAP_KEY_NAME, scopes=frozenset({ADMIN_SCOPE}), is_bootstrap=True
            )
            request.state.auth_key = authed
            _enforce_dev_scope_environment(authed)
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

    def get_actor(
        x_actor: str | None = Header(default=None, alias="X-Actor"),
        key: AuthedKey = Depends(require_api_key),
    ) -> str:
        if bootstrap_honors_x_actor and key.is_bootstrap and x_actor:
            return x_actor
        return key.name

    return AuthDeps(
        require_api_key=require_api_key,
        require_scope=require_scope,
        get_actor=get_actor,
    )
