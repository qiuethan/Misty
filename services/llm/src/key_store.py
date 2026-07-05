"""In-memory API-key store seeded from config — the DB-free equivalent of
team-tracking's Postgres key table. Satisfies platform_auth's ApiKeyStore
protocol structurally, so it is swappable for a persistent store later (#44)."""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ConsumerKeyRow:
    id: UUID
    name: str
    scopes: list[str]
    active: bool = True
    revoked_at: datetime | None = None


class InMemoryKeyStore:
    def __init__(self) -> None:
        self._hash_by_prefix: dict[str, str] = {}
        self._row_by_prefix: dict[str, ConsumerKeyRow] = {}

    def add(self, *, prefix: str, key_hash: str, name: str, scopes: list[str]) -> None:
        self._hash_by_prefix[prefix] = key_hash
        self._row_by_prefix[prefix] = ConsumerKeyRow(id=uuid4(), name=name, scopes=list(scopes))

    # --- platform_auth.ApiKeyStore protocol ---
    def get_api_key_hash(self, prefix: str) -> str | None:
        return self._hash_by_prefix.get(prefix)

    def get_api_key_by_prefix(self, prefix: str) -> ConsumerKeyRow | None:
        return self._row_by_prefix.get(prefix)

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        return None  # stateless — nothing to record


def key_store_from_config(consumer_keys_json: str) -> InMemoryKeyStore:
    store = InMemoryKeyStore()
    raw = (consumer_keys_json or "").strip()
    if not raw:
        return store
    for entry in json.loads(raw):
        store.add(
            prefix=entry["prefix"],
            key_hash=entry["key_hash"],
            name=entry["name"],
            scopes=entry.get("scopes", []),
        )
    return store
