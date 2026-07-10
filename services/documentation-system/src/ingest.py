"""Ingest orchestration: the URL-in → catalogued-doc flow. Pure of framework
concerns — takes injected storage/fetchers/directory and an actor string."""

from datetime import datetime, timezone

from contracts.directory import DirectoryClient, DirectoryUnavailable
from contracts.fetcher import FetchError
from contracts.storage import StorageAdapter
from contracts.types import DocIngest, IngestResult
from src.fetch.registry import FetcherRegistry
from src.url_norm import derive_source, normalize_url


class BadReference(Exception):
    """A supplied source_id / owning_*_id is invalid and the directory was
    reachable enough to confirm it. Routers map this to HTTP 400."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_grants(storage, doc_id, grants):
    for g in grants:
        storage.add_grant(doc_id, grantee_type=g.grantee_type, grantee_id=g.grantee_id, actor="ingest")


def ingest_doc(
    payload: DocIngest,
    *,
    storage: StorageAdapter,
    fetchers: FetcherRegistry,
    directory: DirectoryClient,
    actor: str,
) -> IngestResult:
    warnings: list[str] = []
    url_normalized = normalize_url(payload.url)

    # 1. Dedup — idempotent re-ingest merges any new tags.
    existing = storage.get_doc_by_normalized_url(url_normalized)
    if existing is not None and existing.active:
        for tag in payload.tags:
            storage.add_tag(existing.id, tag)
        _apply_grants(storage, existing.id, payload.grants)
        refreshed = storage.get_doc(existing.id)
        return IngestResult(
            doc=refreshed,
            created=False,
            warnings=[f"already catalogued (added by {existing.created_by})"],
        )

    # 2. Determine source — caller-supplied wins, else derive.
    if payload.source_id is not None:
        source = storage.get_source(payload.source_id)
        if source is None:
            raise BadReference(f"source_id not found: {payload.source_id}")
        source_id = source.id
    else:
        source_id = derive_source(payload.url, storage.list_sources())
        source = storage.get_source(source_id)

    # 3. Fetch, best-effort.
    title = payload.title
    snapshot = None
    fetched_at = None
    if source is not None and source.content_fetch_enabled:
        try:
            result = fetchers.fetch_for(source_id, payload.url)
            title = payload.title or result.title
            snapshot = result.content_snapshot
            fetched_at = _now()
        except FetchError as e:
            warnings.append(f"content fetch failed ({e}); title fell back to url")
    elif source is not None and source.requires_auth:
        warnings.append(f"source '{source_id}' requires auth; no snapshot fetched")
    if title is None:
        title = payload.url

    # 4. Resolve ownership labels (validate when reachable, degrade when not).
    team_label = _resolve_label(
        directory.get_team_label, payload.owning_team_id, "owning_team_id", warnings
    )
    person_label = _resolve_label(
        directory.get_person_label, payload.owning_person_id, "owning_person_id", warnings
    )

    # 5. Persist.
    doc = storage.create_doc(
        url=payload.url,
        url_normalized=url_normalized,
        source_id=source_id,
        title=title,
        description=payload.description,
        owning_team_id=payload.owning_team_id,
        owning_team_label=team_label,
        owning_person_id=payload.owning_person_id,
        owning_person_label=person_label,
        content_snapshot=snapshot,
        fetched_at=fetched_at,
        tags=payload.tags,
        actor=actor,
    )
    _apply_grants(storage, doc.id, payload.grants)
    doc = storage.get_doc(doc.id)  # re-hydrate with grants for the response
    return IngestResult(doc=doc, created=True, warnings=warnings)


def _resolve_label(lookup, entity_id, field_name: str, warnings: list[str]) -> str | None:
    """Return a display label for entity_id. Raises BadReference if the
    directory is reachable but the id is unknown; appends a warning and returns
    None if the directory is unavailable. Returns None when entity_id is None."""
    if entity_id is None:
        return None
    try:
        label = lookup(entity_id)
    except DirectoryUnavailable:
        warnings.append(f"directory unavailable; {field_name} label deferred")
        return None
    if label is None:
        raise BadReference(f"{field_name} not found: {entity_id}")
    return label
