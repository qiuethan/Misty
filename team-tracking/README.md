# team-tracking

UTMIST's team-tracking system. The directory layer: people, teams, roles, memberships. Foundational — downstream systems (docs catalog, Discord bot, sponsor CRM, event tools) reference this as the source of truth for org identity.

See `DESIGN.md` for the schema and layered architecture.

## Design principle: interface-first

The database, admin UI, API framework, and hosting are all deferred decisions. This code is structured so those choices can change without rewriting consumers.

Every boundary that could change is expressed as an **interface** (contract) with concrete implementations behind it:

```
consumers
    │
    ▼
DirectoryAPI     ← stable contract; consumers only depend on this
    │
    ▼
StorageAdapter   ← stable contract; DirectoryAPI only depends on this
    │
    ▼
Postgres | SQLite | ... ← swappable concrete implementations
```

**Rules of thumb:**

- Consumers never import from `src/storage/*` directly. They only see the interfaces in `contracts/`.
- Swapping Postgres for another store means adding a new class in `src/storage/` that implements `StorageAdapter`. No other file should change.
- Same pattern for auth, event publishing, admin surface — any boundary that touches an external system.

## Folder layout

```
team-tracking/
├── README.md          — this file
├── DESIGN.md          — schema + architecture spec
├── contracts/         — stable interface definitions (the things nothing else can break)
├── src/               — concrete implementations (freely swappable)
│   └── storage/       — storage adapters (Postgres first; others later)
└── migrations/        — SQL DDL for the initial Postgres schema
```

## Status

v1 implementation complete: Python + FastAPI + SQLAlchemy Core. Four base tables (people, teams, role_kinds, team_memberships) exposed via an HTTP API guarded by an API key. Two `StorageAdapter` implementations shipped — `InMemoryStorageAdapter` for tests, `PostgresStorageAdapter` for production. OpenAPI is auto-generated at `/openapi.json` and `/docs`.

**Deferred (per DESIGN.md non-goals):** connectors layer (Discord/Google/GitHub sync), extension tables (e.g. `person_identifiers`), permission-enforcement engine, admin UI, pagination.

## Local development

Prereqs: Docker (for Postgres), Python 3.11+, [uv](https://github.com/astral-sh/uv).

```bash
# One-time setup
cp .env.example .env
docker compose up -d postgres
uv sync --extra dev
uv run alembic upgrade head

# Run the API server
uv run uvicorn src.api.app:app --reload --port 8000

# Run tests (fast — in-memory only)
uv run pytest --ignore=tests/test_postgres_adapter.py -v

# Run tests including Postgres integration (requires docker compose up)
uv run pytest -v

# Open OpenAPI docs
open http://localhost:8000/docs
```

## Sample curl usage

```bash
# Create a person
curl -sS -X POST http://localhost:8000/people \
  -H "X-API-Key: dev-api-key-change-me" \
  -H "X-Actor: bootstrap-script" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "Alex Chen", "primary_email": "alex@utmist.ca"}'

# Create a team
curl -sS -X POST http://localhost:8000/teams \
  -H "X-API-Key: dev-api-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"slug": "partnerships", "label": "Partnerships"}'

# List role kinds
curl -sS http://localhost:8000/role_kinds -H "X-API-Key: dev-api-key-change-me"
```
