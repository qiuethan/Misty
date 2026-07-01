from datetime import datetime, timezone
from uuid import UUID, uuid4

from contracts.types import ApiKey, Doc, Source


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryStorageAdapter:
    """In-process adapter for tests. Not thread-safe, not persistent. Enforces
    the same invariants as Postgres (dedup by url_normalized, tag uniqueness)."""

    def __init__(self, seed_sources: list[Source] | None = None) -> None:
        self._docs: dict[UUID, Doc] = {}
        self._tags: dict[UUID, set[str]] = {}
        self._sources: dict[str, Source] = {s.id: s for s in (seed_sources or [])}
        self._api_keys: dict[UUID, ApiKey] = {}
        self._api_key_hashes: dict[UUID, str] = {}

    def _hydrate(self, doc: Doc) -> Doc:
        data = doc.model_dump()
        data["tags"] = sorted(self._tags.get(doc.id, set()))
        return Doc(**data)

    # --- Docs ---

    def create_doc(
        self, *, url, url_normalized, source_id, title, description,
        owning_team_id, owning_team_label, owning_person_id, owning_person_label,
        content_snapshot, fetched_at, tags, actor,
    ) -> Doc:
        now = _now()
        doc = Doc(
            id=uuid4(), url=url, url_normalized=url_normalized, source_id=source_id,
            title=title, description=description,
            owning_team_id=owning_team_id, owning_team_label=owning_team_label,
            owning_person_id=owning_person_id, owning_person_label=owning_person_label,
            content_snapshot=content_snapshot, fetched_at=fetched_at, active=True,
            tags=[], created_at=now, updated_at=now, created_by=actor, updated_by=actor,
        )
        self._docs[doc.id] = doc
        self._tags[doc.id] = set(tags)
        return self._hydrate(doc)

    def get_doc(self, doc_id: UUID) -> Doc | None:
        doc = self._docs.get(doc_id)
        return self._hydrate(doc) if doc else None

    def get_doc_by_normalized_url(self, url_normalized: str) -> Doc | None:
        for doc in self._docs.values():
            if doc.url_normalized == url_normalized:
                return self._hydrate(doc)
        return None

    def list_docs(
        self, *, owning_team_id=None, owning_person_id=None,
        source_id=None, tag=None, active_only=True,
    ) -> list[Doc]:
        out = []
        for doc in self._docs.values():
            if active_only and not doc.active:
                continue
            if owning_team_id is not None and doc.owning_team_id != owning_team_id:
                continue
            if owning_person_id is not None and doc.owning_person_id != owning_person_id:
                continue
            if source_id is not None and doc.source_id != source_id:
                continue
            if tag is not None and tag not in self._tags.get(doc.id, set()):
                continue
            out.append(self._hydrate(doc))
        return out

    def update_doc(self, doc_id: UUID, values: dict, *, actor: str) -> Doc | None:
        existing = self._docs.get(doc_id)
        if existing is None:
            return None
        data = existing.model_dump()
        data.update(values)
        data["updated_at"] = _now()
        data["updated_by"] = actor
        data["tags"] = []
        updated = Doc(**data)
        self._docs[doc_id] = updated
        return self._hydrate(updated)

    def add_tag(self, doc_id: UUID, tag: str) -> bool:
        if doc_id not in self._docs:
            return False
        self._tags.setdefault(doc_id, set()).add(tag)
        return True

    def remove_tag(self, doc_id: UUID, tag: str) -> bool:
        tags = self._tags.get(doc_id)
        if not tags or tag not in tags:
            return False
        tags.discard(tag)
        return True

    # --- Sources ---

    def list_sources(self, *, active_only: bool = False) -> list[Source]:
        out = list(self._sources.values())
        if active_only:
            out = [s for s in out if s.active]
        return out

    def get_source(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    # --- API keys (mirror team-tracking) ---

    def create_api_key(self, *, name, prefix, key_hash, scopes, actor) -> ApiKey:
        if any(k.name == name for k in self._api_keys.values()):
            raise ValueError(f"name already exists: {name}")
        if any(k.prefix == prefix for k in self._api_keys.values()):
            raise ValueError(f"prefix already exists: {prefix}")
        now = _now()
        key = ApiKey(
            id=uuid4(), name=name, prefix=prefix, scopes=scopes, active=True,
            revoked_at=None, last_used_at=None,
            created_at=now, updated_at=now, created_by=actor, updated_by=actor,
        )
        self._api_keys[key.id] = key
        self._api_key_hashes[key.id] = key_hash
        return key

    def get_api_key_by_prefix(self, prefix: str) -> ApiKey | None:
        for k in self._api_keys.values():
            if k.prefix == prefix:
                return k
        return None

    def get_api_key_hash(self, prefix: str) -> str | None:
        for k in self._api_keys.values():
            if k.prefix == prefix and k.active and k.revoked_at is None:
                return self._api_key_hashes.get(k.id)
        return None

    def list_api_keys(self, *, active_only: bool = False) -> list[ApiKey]:
        keys = list(self._api_keys.values())
        if active_only:
            keys = [k for k in keys if k.active and k.revoked_at is None]
        return keys

    def revoke_api_key(self, api_key_id: UUID, *, actor: str) -> ApiKey | None:
        existing = self._api_keys.get(api_key_id)
        if existing is None:
            return None
        now = _now()
        data = existing.model_dump()
        data.update(active=False, revoked_at=now, updated_at=now, updated_by=actor)
        revoked = ApiKey(**data)
        self._api_keys[api_key_id] = revoked
        return revoked

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        existing = self._api_keys.get(api_key_id)
        if existing is None:
            return
        data = existing.model_dump()
        data["last_used_at"] = _now()
        self._api_keys[api_key_id] = ApiKey(**data)
