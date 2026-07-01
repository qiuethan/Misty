from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from contracts.types import ApiKey, Doc, Source
from src.storage.schema import api_keys, doc_tags, docs, sources


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source_row_to_model(row) -> Source:
    return Source(
        id=row.id, label=row.label, url_patterns=list(row.url_patterns),
        requires_auth=row.requires_auth, has_api=row.has_api,
        content_fetch_enabled=row.content_fetch_enabled, active=row.active,
        created_at=row.created_at, updated_at=row.updated_at,
        created_by=row.created_by, updated_by=row.updated_by,
    )


def _api_key_row_to_model(row) -> ApiKey:
    return ApiKey(
        id=row.id, name=row.name, prefix=row.prefix, scopes=list(row.scopes),
        active=row.active, revoked_at=row.revoked_at, last_used_at=row.last_used_at,
        created_at=row.created_at, updated_at=row.updated_at,
        created_by=row.created_by, updated_by=row.updated_by,
    )


class PostgresStorageAdapter:
    """Postgres-backed StorageAdapter using SQLAlchemy Core. Returns Pydantic
    models, never raw rows. Tags are stored in doc_tags and hydrated on read."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _tags_for(self, conn, doc_id: UUID) -> list[str]:
        rows = conn.execute(
            select(doc_tags.c.tag).where(doc_tags.c.doc_id == doc_id).order_by(doc_tags.c.tag)
        ).all()
        return [r.tag for r in rows]

    def _row_to_doc(self, conn, row) -> Doc:
        return Doc(
            id=row.id, url=row.url, url_normalized=row.url_normalized, title=row.title,
            source_id=row.source_id, description=row.description,
            owning_team_id=row.owning_team_id, owning_team_label=row.owning_team_label,
            owning_person_id=row.owning_person_id, owning_person_label=row.owning_person_label,
            content_snapshot=row.content_snapshot, fetched_at=row.fetched_at, active=row.active,
            tags=self._tags_for(conn, row.id),
            created_at=row.created_at, updated_at=row.updated_at,
            created_by=row.created_by, updated_by=row.updated_by,
        )

    # --- Docs ---

    def create_doc(
        self, *, url, url_normalized, source_id, title, description,
        owning_team_id, owning_team_label, owning_person_id, owning_person_label,
        content_snapshot, fetched_at, tags, actor,
    ) -> Doc:
        with self._engine.begin() as conn:
            row = conn.execute(
                insert(docs).values(
                    url=url, url_normalized=url_normalized, source_id=source_id, title=title,
                    description=description, owning_team_id=owning_team_id,
                    owning_team_label=owning_team_label, owning_person_id=owning_person_id,
                    owning_person_label=owning_person_label, content_snapshot=content_snapshot,
                    fetched_at=fetched_at, created_by=actor, updated_by=actor,
                ).returning(docs)
            ).one()
            for tag in set(tags):
                conn.execute(insert(doc_tags).values(doc_id=row.id, tag=tag))
            return self._row_to_doc(conn, row)

    def get_doc(self, doc_id: UUID) -> Doc | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(docs).where(docs.c.id == doc_id)).one_or_none()
            return self._row_to_doc(conn, row) if row else None

    def get_doc_by_normalized_url(self, url_normalized: str) -> Doc | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(docs).where(docs.c.url_normalized == url_normalized)
            ).one_or_none()
            return self._row_to_doc(conn, row) if row else None

    def list_docs(
        self, *, owning_team_id=None, owning_person_id=None,
        source_id=None, tag=None, active_only=True,
    ) -> list[Doc]:
        stmt = select(docs)
        conditions = []
        if active_only:
            conditions.append(docs.c.active.is_(True))
        if owning_team_id is not None:
            conditions.append(docs.c.owning_team_id == owning_team_id)
        if owning_person_id is not None:
            conditions.append(docs.c.owning_person_id == owning_person_id)
        if source_id is not None:
            conditions.append(docs.c.source_id == source_id)
        if tag is not None:
            stmt = stmt.where(
                docs.c.id.in_(select(doc_tags.c.doc_id).where(doc_tags.c.tag == tag))
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
            return [self._row_to_doc(conn, r) for r in rows]

    def update_doc(self, doc_id: UUID, values: dict, *, actor: str) -> Doc | None:
        patch = dict(values)
        patch["updated_at"] = _now()
        patch["updated_by"] = actor
        with self._engine.begin() as conn:
            row = conn.execute(
                update(docs).where(docs.c.id == doc_id).values(**patch).returning(docs)
            ).one_or_none()
            return self._row_to_doc(conn, row) if row else None

    def add_tag(self, doc_id: UUID, tag: str) -> bool:
        with self._engine.begin() as conn:
            exists = conn.execute(select(docs.c.id).where(docs.c.id == doc_id)).one_or_none()
            if exists is None:
                return False
            try:
                conn.execute(insert(doc_tags).values(doc_id=doc_id, tag=tag))
            except IntegrityError:
                pass  # already present — idempotent
            return True

    def remove_tag(self, doc_id: UUID, tag: str) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(doc_tags).where(doc_tags.c.doc_id == doc_id, doc_tags.c.tag == tag)
            )
            return result.rowcount > 0

    # --- Sources ---

    def list_sources(self, *, active_only: bool = False) -> list[Source]:
        stmt = select(sources)
        if active_only:
            stmt = stmt.where(sources.c.active.is_(True))
        with self._engine.connect() as conn:
            return [_source_row_to_model(r) for r in conn.execute(stmt).all()]

    def get_source(self, source_id: str) -> Source | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(sources).where(sources.c.id == source_id)).one_or_none()
        return _source_row_to_model(row) if row else None

    # --- API keys (identical to team-tracking) ---

    def create_api_key(self, *, name, prefix, key_hash, scopes, actor) -> ApiKey:
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    insert(api_keys).values(
                        name=name, prefix=prefix, key_hash=key_hash, scopes=scopes,
                        created_by=actor, updated_by=actor,
                    ).returning(api_keys)
                ).one()
        except IntegrityError as e:
            raise ValueError(f"name or prefix already exists: {name!r} / {prefix!r}") from e
        return _api_key_row_to_model(row)

    def get_api_key_by_prefix(self, prefix: str) -> ApiKey | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(api_keys).where(api_keys.c.prefix == prefix)).one_or_none()
        return _api_key_row_to_model(row) if row else None

    def get_api_key_hash(self, prefix: str) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(api_keys.c.key_hash).where(
                    api_keys.c.prefix == prefix,
                    api_keys.c.active.is_(True),
                    api_keys.c.revoked_at.is_(None),
                )
            ).one_or_none()
        return row.key_hash if row else None

    def list_api_keys(self, *, active_only: bool = False) -> list[ApiKey]:
        stmt = select(api_keys)
        if active_only:
            stmt = stmt.where(api_keys.c.active.is_(True), api_keys.c.revoked_at.is_(None))
        with self._engine.connect() as conn:
            return [_api_key_row_to_model(r) for r in conn.execute(stmt).all()]

    def revoke_api_key(self, api_key_id: UUID, *, actor: str) -> ApiKey | None:
        now = _now()
        with self._engine.begin() as conn:
            row = conn.execute(
                update(api_keys).where(api_keys.c.id == api_key_id)
                .values(active=False, revoked_at=now, updated_at=now, updated_by=actor)
                .returning(api_keys)
            ).one_or_none()
        return _api_key_row_to_model(row) if row else None

    def touch_api_key_last_used(self, api_key_id: UUID) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    update(api_keys).where(api_keys.c.id == api_key_id).values(last_used_at=_now())
                )
        except Exception:
            pass
