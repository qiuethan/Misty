from uuid import UUID

from platform_auth import ApiKeyRow


class NullApiKeyStore:
    """Satisfies platform_auth's ApiKeyStore for env-key-only auth.

    The shared env `API_KEY` must be a plain opaque string, NOT shaped like the
    `vf_<prefix>_<secret>` DB-key envelope — the env-key path only matches
    non-envelope keys. DB-backed keys are unsupported here, so all lookups
    below return None.
    """

    def get_api_key_hash(self, prefix: str) -> str | None:
        return None

    def get_api_key_by_prefix(self, prefix: str) -> ApiKeyRow | None:
        return None

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        return None
