from uuid import UUID

from platform_auth import ApiKeyRow


class NullApiKeyStore:
    """Satisfies platform_auth's ApiKeyStore for env-key-only auth.

    The verification service issues no DB-backed keys — the single shared vf_
    key is validated via the env-key path — so all DB-key lookups return nothing.
    """

    def get_api_key_hash(self, prefix: str) -> str | None:
        return None

    def get_api_key_by_prefix(self, prefix: str) -> ApiKeyRow | None:
        return None

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        return None
