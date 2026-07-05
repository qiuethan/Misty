"""Thin shim: builds team-tracking's auth deps from platform_auth.

Re-exports the same names routers already import.
"""

from platform_auth import ADMIN_SCOPE, AuthedKey, build_auth  # noqa: F401

from src.api.deps import get_storage
from src.config import get_settings

_deps = build_auth(
    get_storage,
    envelope="tt_",
    get_env_key=lambda: get_settings().api_key,
    is_prod=lambda: get_settings().tt_env == "production",
    enable_dev_spoof=True,
    bootstrap_honors_x_actor=True,
    audit_logger_name="team_tracking.audit",
    dev_spoof_reject_log_fields={"tt_env": "production"},
)

require_api_key = _deps.require_api_key
require_scope = _deps.require_scope
get_actor = _deps.get_actor
