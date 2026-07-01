# Architecture

Design decisions and extending guide for `team-tracking` v1.

See [API.md](API.md) for the endpoint reference. See [archive/2026-06-30-DESIGN.md](archive/2026-06-30-DESIGN.md) for the original design spec.

## Overview

The service is three horizontal layers:

```
contracts/          Pure Python. Pydantic models + StorageAdapter Protocol.
                    No framework imports. Nothing else can break this.
        |
        v
src/api/            FastAPI routers + auth + DI wiring.
                    Imports contracts/ only. Never imports src/storage/ directly.
        |
        v
src/storage/        Concrete adapters (InMemory, Postgres).
                    Imports contracts/ for types; defines its own DB schema.
```

The key invariant: `contracts/` has zero knowledge of FastAPI, SQLAlchemy, or Postgres. The API layer has zero knowledge of which storage adapter is running. The only place that wires them together is `src/api/deps.py` via FastAPI's dependency injection.

## Layer responsibilities

### `contracts/`

Two files, no framework imports.

`contracts/types.py` defines every domain model as a Pydantic `BaseModel`. The four entity types (`Person`, `Team`, `RoleKind`, `TeamMembership`) each inherit from `DirectoryBase`, which carries the four audit fields (`created_at`, `updated_at`, `created_by`, `updated_by`). Input DTOs (`PersonCreate`, `PersonUpdate`, `TeamCreate`, etc.) are also here — they are what the API deserializes from request bodies.

`contracts/storage.py` defines `StorageAdapter` as a `typing.Protocol`. Any class that implements the methods in this protocol — with the same signatures and semantics — can be used as the backend. The API layer only types its dependency as `StorageAdapter`; it never imports a concrete class.

### `src/api/`

FastAPI application. Four files at the top level plus a `routers/` subdirectory.

`app.py` is the app factory. It creates a `FastAPI` instance and mounts the four routers. The module-level `app` variable is what uvicorn imports.

`auth.py` defines two FastAPI dependencies: `require_api_key` (validates `X-API-Key` against config, raises 401 if wrong) and `get_actor` (calls `require_api_key`, then returns `X-Actor` header or `"api"` as a fallback). Routers use `get_actor` on write endpoints and `require_api_key` on read-only endpoints.

`deps.py` wires the storage adapter. `get_storage()` is a FastAPI dependency that returns a `PostgresStorageAdapter` backed by a cached SQLAlchemy engine. Tests override this via `app.dependency_overrides[get_storage] = lambda: my_adapter`.

`routers/people.py`, `routers/teams.py`, `routers/role_kinds.py`, `routers/memberships.py` each define an `APIRouter` for one resource. They call storage methods, map storage `ValueError` to HTTP 409 or 400, and map `None` returns to HTTP 404.

### `src/storage/`

Two concrete adapters ship in v1.

`schema.py` defines the SQLAlchemy Core `Table` objects. This is the authoritative definition of what columns exist in Postgres. Alembic migrations are written by hand and must stay in sync with this file.

`InMemoryStorageAdapter` (`in_memory.py`) stores everything in plain Python dicts. It enforces the same invariants as Postgres (email uniqueness, slug uniqueness, FK checks on membership creation). It is not thread-safe and not persistent. Used exclusively in tests and local prototyping.

`PostgresStorageAdapter` (`postgres.py`) uses SQLAlchemy Core (not ORM). Every method opens a connection, runs a typed SQL expression against the tables defined in `schema.py`, and converts the result row to a Pydantic model via a `_*_row_to_model` helper. The adapter takes a SQLAlchemy `Engine` at construction time; it never creates its own engine.

### `migrations/`

Alembic manages the Postgres schema. Two migrations exist in v1:

- `001_initial_schema.py` — creates all four tables, indexes, and the `citext` extension.
- `002_seed_role_kinds.py` — inserts the four seed rows (`executive`, `director`, `lead`, `member`).

Run `uv run alembic upgrade head` to apply both. Run `uv run alembic downgrade base` to roll back.

### `tests/`

The test suite mirrors the source layout. API tests (`test_api_*.py`) use FastAPI's `TestClient` with `InMemoryStorageAdapter` injected. `test_in_memory_adapter.py` tests the adapter directly. `test_postgres_adapter.py` repeats the adapter tests against live Postgres. `test_types.py` checks Pydantic validation. `test_openapi.py` checks that the OpenAPI schema is generated and includes expected paths.

`conftest.py` provides fixtures: a seeded `InMemoryStorageAdapter` (with the four role kinds pre-inserted), a `TestClient` using it, and a seeded-person/team helper used by membership tests.

## Key design decisions

**Why only four columns on `people`?**
The base schema is intentionally minimal. `display_name`, `primary_email`, `active`, and the four audit fields are all that is needed to track a person across org changes. External identifiers (Discord ID, GitHub handle, UofT email) live in a future `person_identifiers` extension table, not as columns here. Putting them in the base would mean a schema migration every time a new integration appears. Adding them as extension rows is a data change.

**Why `role_kinds` uses a slug as primary key?**
Downstream permission rules read `role_kind_id = 'lead'` or `role_kind_id IN ('executive', 'director')` directly. A numeric surrogate key would require a join to get to the human-readable slug, and the slug is the meaningful value. Renaming a slug is a data migration (UPDATE + application deploy), which is intentionally rare and handled explicitly. The four seed values (`executive`, `director`, `lead`, `member`) are stable vocabulary.

**Why `is_team_admin` is separate from `role_kind_id`?**
Admin authority (can edit the team and its memberships) is orthogonal to seniority. The Partnerships lead might not be the team admin; a member might be. Conflating the two into a single field would require either a special `admin` role kind (which mixes seniority and authority) or a list of role kinds that imply admin (which embeds policy in schema). The boolean flag keeps them independent.

**Why historical rows instead of deletes?**
`team_memberships` rows are never deleted. When someone leaves a team, `ended_at` is set to a date. This means:
- The full membership history survives, which matters for turnover continuity.
- Point-in-time queries ("who was on Partnerships on 2024-12-15?") work without any audit log — the data is in the main table.
- The `end_membership` endpoint exists as a semantic helper over `PATCH /memberships/{id}` because closing a membership is a distinct intent from editing it.

There is intentionally no unique constraint on `(person_id, team_id)` for active rows, because overlapping rows are valid during role transitions (a person can hold member through November and lead from December — two rows with overlapping or adjacent date ranges).

**Why `StorageAdapter` as a Protocol?**
The API layer is testable without a database. `InMemoryStorageAdapter` runs in-process; the entire test suite (except `test_postgres_adapter.py`) completes in under five seconds. The Protocol boundary also documents the contract explicitly: if you want to add a new storage backend (SQLite, a mock, a read-replica wrapper), you implement these methods with these semantics — nothing else needs to change.

**Why `citext` for `primary_email`?**
`citext` is a Postgres extension that makes a text column case-insensitive for equality and uniqueness checks. `Alice@UTMIST.ca` and `alice@utmist.ca` are the same address. The API normalizes to lowercase on write (in the Pydantic validator), and `citext` enforces it at the DB level as a belt-and-suspenders guard. `InMemoryStorageAdapter` normalizes manually before comparison.

**Why API key + `X-Actor` for auth?**
V1 auth is minimal by design. `X-API-Key` is a shared secret checked against config, not a keyed table. `X-Actor` lets callers self-identify (e.g., `"discord-bot"`, `"sync-job"`, `"bootstrap-script"`), which ends up in `created_by`/`updated_by` audit fields. When multiple callers exist and per-caller revocation is needed, the obvious upgrade path is an `api_keys` table that the auth dependency looks up.

**Why `contracts/` has no framework imports?**
If `contracts/` imported FastAPI or SQLAlchemy, swapping either would require touching the contract layer. As written, `contracts/` can be extracted to a separate package and shared with connector services or CLI tools without pulling in any web framework dependency.

## Data model quick reference

### `people`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` default |
| `display_name` | text NOT NULL | Free-form; handles all name conventions |
| `primary_email` | citext NOT NULL UNIQUE | Case-insensitive; normalized to lowercase on write |
| `active` | boolean NOT NULL | Default `true`; soft-retirement only |
| `created_at` / `updated_at` | timestamptz NOT NULL | Auto-populated |
| `created_by` / `updated_by` | text NOT NULL | Actor identifier string |

### `teams`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` default |
| `slug` | text NOT NULL UNIQUE | Pattern `[a-z0-9_.]+`; enforced at app layer |
| `label` | text NOT NULL | Human-readable display name |
| `description` | text NULL | One-line summary |
| `parent_id` | UUID NULL FK → teams.id | Self-reference for hierarchy; null = top-level |
| `active` | boolean NOT NULL | Default `true` |
| `created_at` / `updated_at` | timestamptz NOT NULL | |
| `created_by` / `updated_by` | text NOT NULL | |

### `role_kinds`

| Column | Type | Notes |
|--------|------|-------|
| `id` | text PK | Slug; e.g. `executive`, `director`, `lead`, `member` |
| `label` | text NOT NULL | Display label |
| `description` | text NULL | |
| `active` | boolean NOT NULL | Default `true` |
| `created_at` / `updated_at` | timestamptz NOT NULL | |
| `created_by` / `updated_by` | text NOT NULL | |

Seed rows: `executive`, `director`, `lead`, `member` (inserted by migration `002`).

### `team_memberships`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | `gen_random_uuid()` default |
| `person_id` | UUID NOT NULL FK → people.id | |
| `team_id` | UUID NOT NULL FK → teams.id | |
| `role_kind_id` | text NOT NULL FK → role_kinds.id | Default `'member'` |
| `is_team_admin` | boolean NOT NULL | Default `false`; orthogonal to role |
| `started_at` | date NOT NULL | Default `CURRENT_DATE` |
| `ended_at` | date NULL | Null = currently active |
| `created_at` / `updated_at` | timestamptz NOT NULL | |
| `created_by` / `updated_by` | text NOT NULL | |

Indexes: `(team_id, ended_at)`, `(person_id, ended_at)`, `(started_at, ended_at)`.

No unique constraint on `(person_id, team_id)` — overlapping rows are valid during role transitions.

## Convention: named exec seats

UTMIST has named positions like "President," "VP Partnerships," "Treasurer." The base schema models these through `team_memberships` rather than a separate `positions` table.

Two patterns:

**Team-scoped exec seats** (VP Partnerships, Events Lead): create a `team_memberships` row on the relevant team with `role_kind_id = 'executive'` (or `'lead'`). Whether the person is also `is_team_admin = true` is a separate decision. The title "VP Partnerships" is derived from the composite `(role_kind=executive, team=partnerships)` — the schema does not store the string.

**Org-wide exec seats** (President, Treasurer): create a top-level team with a slug like `leadership` and put these people there with `role_kind_id = 'executive'`. The team is data, not schema.

This approach means adding a new named position is a data operation (create a team and/or add a membership row), not a schema migration.

## Extending the system

### Add a new HTTP endpoint

1. Decide which resource it belongs to. If it fits an existing router (`people`, `teams`, `role_kinds`, `memberships`), add it there.
2. Add the method signature to `contracts/storage.py` (the `StorageAdapter` Protocol).
3. Implement the method in both `InMemoryStorageAdapter` (`src/storage/in_memory.py`) and `PostgresStorageAdapter` (`src/storage/postgres.py`).
4. Add the route handler to the relevant file in `src/api/routers/`.
5. Add tests in the matching `tests/test_api_*.py` and `tests/test_in_memory_adapter.py`.

The order matters: define the contract first, then implement, then expose.

### Add a new storage adapter

Create a new file in `src/storage/` (e.g., `src/storage/sqlite.py`). Implement every method defined in `contracts/storage.py`. The class does not need to inherit from anything — Python structural typing means it satisfies the Protocol automatically.

To use it: change `src/api/deps.py` to return your adapter from `get_storage()`, or pass it via `app.dependency_overrides[get_storage]` in a specific test or environment.

### Add a new base column

Example: adding `preferred_name: str | None` to `people`.

1. Add the field to `Person` in `contracts/types.py`. Make it optional with a default of `None` so existing records deserialize correctly.
2. Add it to `PersonCreate` and/or `PersonUpdate` as appropriate.
3. Add the column to the `people` table in `src/storage/schema.py`.
4. Add a new Alembic migration in `migrations/versions/` that runs `op.add_column(...)`.
5. Update `_person_row_to_model` in `src/storage/postgres.py` to read the new field.
6. Update `create_person` and `update_person` in both storage adapters to handle the new field.

### Add an extension table

Extension tables add richer data without touching base tables. Example: `person_identifiers` to store Discord IDs, GitHub handles, and UofT emails.

Suggested file layout:
```
contracts/
    person_identifiers.py   # PersonIdentifier model + Create/Update DTOs
                            # + extend StorageAdapter Protocol with new methods

src/storage/
    schema.py               # Add person_identifiers Table definition
    in_memory.py            # Add identifier storage and methods
    postgres.py             # Add SQL implementations

src/api/routers/
    person_identifiers.py   # New router, mounted in app.py

migrations/versions/
    003_person_identifiers.py  # New Alembic migration

tests/
    test_api_person_identifiers.py
```

The base tables (`people`, `teams`, `role_kinds`, `team_memberships`) do not change. The extension table has a FK → `people.id` and is maintained by its own methods on `StorageAdapter`.

### Add a connector

A connector is a service (or async worker) that synchronizes data between this API and an external system (Discord, Google Workspace, GitHub). The connector hangs off the HTTP API — it reads and writes through `GET`/`POST`/`PATCH` requests, not directly to the database.

Example: a Discord role sync connector would:
1. Call `GET /memberships?team_id=<id>&active_only=true` to get the current roster.
2. Compare against Discord's current role assignments.
3. Call `POST /memberships` or `POST /memberships/{id}/end` to record changes.

The connector does not import from `src/` or `contracts/`. It is a separate process that speaks the published HTTP API. This is the boundary that keeps the directory's data model independent of integration details.

## Non-goals reference

The following are explicitly out of scope for v1. See [archive/2026-06-30-DESIGN.md](archive/2026-06-30-DESIGN.md) for the full rationale.

- No Discord / Google / GitHub / Notion sync jobs (connectors layer, built separately).
- No permission enforcement engine (downstream systems derive access from membership data).
- No auth or login for officers editing directory data (handled by whatever admin surface is chosen).
- No org-wide admin concept (deferred to connectors/perms layer).
- No content storage (the directory is identity and structure only).
- No pagination (list endpoints return all matching rows; add if roster grows past ~500).
