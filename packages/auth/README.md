# platform-auth

Shared API-key auth (keys, scopes, audit) for UTMIST platform services. A pure leaf package: depends only on `fastapi`/`starlette`/`argon2` plus stdlib, never on any service's code. Each service wires it in via `build_auth(...)`, passing its own storage (or in-memory) key store and config.

## Exports (`platform_auth/__init__.py`)

| Name | From | What it is |
|------|------|------------|
| `build_auth` | `factory.py` | Builds a service's `require_api_key` / `require_scope` / `get_actor` / `get_on_behalf_actor` FastAPI dependencies from its key store + config. |
| `AuthDeps` | `factory.py` | Dataclass bundling the four dependencies `build_auth` returns. |
| `AuditLogMiddleware` | `audit.py` | One structured JSON audit line per request to stdout, keyed off `request.state.auth_key`. |
| `generate_key` | `hashing.py` | Generates a new `<envelope><prefix>_<secret>` API key; returns `(plaintext, prefix, key_hash)`. |
| `verify_key` | `hashing.py` | Constant-time verify of a candidate plaintext against an argon2 hash. |
| `parse_prefix` | `hashing.py` | Extracts the prefix segment from a candidate key for a given envelope, or `None`. |
| `PREFIX_LENGTH` | `hashing.py` | Length in chars of the public prefix segment. |
| `ApiKeyRow` | `models.py` | Protocol for the subset of a stored key row the auth path reads. |
| `ApiKeyStore` | `models.py` | Protocol a service's key store must satisfy (`get_api_key_hash`, `get_api_key_by_prefix`, `touch_api_key_last_used`). A DB-backed `StorageAdapter` satisfies this structurally; so does `InMemoryKeyStore` below. |
| `AuthedKey` | `models.py` | Resolved caller identity: `name` (the audit actor), `scopes`, `is_bootstrap`. |
| `ADMIN_SCOPE` | `models.py` | The wildcard scope (`"admin"`) that satisfies any `require_scope` check. |
| `DEV_SPOOF_SCOPE` | `models.py` | The `"dev:spoof"` scope, rejected outside dev/local by `_enforce_dev_scope_environment`. |
| `ConsumerKeyRow` | `memory_store.py` | Frozen dataclass row shape backing `InMemoryKeyStore` — `id`, `name`, `scopes`, `active`, `revoked_at`. |
| `InMemoryKeyStore` | `memory_store.py` | DB-free `ApiKeyStore` implementation. Used by services with no `api_keys` table (`llm`, `meeting`, `connectors`) — keys are seeded from config at boot rather than persisted. |
| `key_store_from_config` | `memory_store.py` | Parses a `CONSUMER_KEYS` JSON array (`[{"name","prefix","key_hash","scopes"}]`) into a populated `InMemoryKeyStore`. Raises `RuntimeError` on a malformed value so a bad env var fails a service's boot, not its first request. |

## Two key-store shapes

- **DB-backed** (`team-tracking`, `documentation-system`, `verification`): the service's own `StorageAdapter` already satisfies `ApiKeyStore` structurally — no adapter class from this package needed.
- **DB-free** (`llm`, `meeting`, `connectors`): `key_store_from_config(settings.consumer_keys)` builds an `InMemoryKeyStore` at boot from the `CONSUMER_KEYS` env var. There is no revoke call — revocation is dropping the entry from `CONSUMER_KEYS` and redeploying.

## Testing

```bash
cd packages/auth
uv run pytest
```
