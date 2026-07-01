# team-tracking

Source-of-truth HTTP API for UTMIST's team directory: people, teams, roles, and memberships.

## What this service does

UTMIST runs a rotating volunteer org — people join teams, move between roles, and eventually hand off to successors. Without a canonical record of who is on what team right now (and who was on it six months ago), downstream systems have to guess. The team-tracking service is that canonical record.

The service exposes a simple REST API over four tables: `people`, `teams`, `role_kinds`, and `team_memberships`. It answers questions like "who is currently on the Partnerships team," "who were the leads during fall semester," and "is Alex an admin of the Events team right now." Downstream systems — a Discord bot, a docs catalog, a sponsor CRM — call this API rather than each maintaining their own roster.

Membership rows are never deleted. When someone leaves a team, their row gains an `ended_at` date. This means the full history of who held what role survives across leadership transitions, and point-in-time queries ("roster as of 2024-12-15") work without any special logic.

## Quick start

Prerequisites: Docker, Python 3.11+, [uv](https://github.com/astral-sh/uv).

```bash
# 1. Copy environment config and start Postgres
cp .env.example .env
docker compose up -d postgres

# 2. Install dependencies (including dev tools)
uv sync --extra dev

# 3. Apply database migrations
uv run alembic upgrade head

# 4. Start the API server
uv run uvicorn src.api.app:app --reload --port 8000
```

The API is now running at `http://localhost:8000`. OpenAPI docs are at `http://localhost:8000/docs`.

The default dev API key is `dev-api-key-change-me` (set in `.env`). Pass it as `X-API-Key` on every request:

```bash
curl -sS http://localhost:8000/role_kinds \
  -H "X-API-Key: dev-api-key-change-me" | python3 -m json.tool
```

## Folder tour

```
team-tracking/
├── contracts/              Domain models (Pydantic) + StorageAdapter Protocol
│   ├── types.py            Person, Team, RoleKind, TeamMembership + Create/Update DTOs
│   └── storage.py          StorageAdapter Protocol — the boundary the API depends on
│
├── src/
│   ├── api/                FastAPI application
│   │   ├── app.py          App factory; mounts all routers
│   │   ├── auth.py         require_api_key + get_actor dependencies
│   │   ├── deps.py         get_storage() FastAPI dependency (injects Postgres adapter)
│   │   └── routers/        One file per resource: people, teams, role_kinds, memberships
│   │
│   ├── storage/            Concrete StorageAdapter implementations
│   │   ├── schema.py       SQLAlchemy Core table definitions (source of DB schema truth)
│   │   ├── in_memory.py    InMemoryStorageAdapter — used in tests
│   │   └── postgres.py     PostgresStorageAdapter — used in production
│   │
│   └── config.py           Settings (DATABASE_URL, API_KEY) loaded from environment
│
├── migrations/             Alembic migrations
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py   Creates all four tables + indexes
│       └── 002_seed_role_kinds.py  Seeds executive/director/lead/member
│
├── tests/                  Test suite (63 tests)
│   ├── conftest.py         Fixtures: in-memory adapter, test client, seeded role_kinds
│   ├── test_api_people.py
│   ├── test_api_teams.py
│   ├── test_api_role_kinds.py
│   ├── test_api_memberships.py
│   ├── test_in_memory_adapter.py
│   ├── test_postgres_adapter.py    Integration tests (requires running Postgres)
│   ├── test_openapi.py
│   └── test_types.py
│
├── docs/
│   ├── API.md              Full endpoint reference
│   ├── ARCHITECTURE.md     Design decisions and extending guide
│   ├── DEPLOYMENT.md       Production deployment + hardening guide
│   └── archive/
│       ├── 2026-06-30-DESIGN.md    Original design spec
│       └── 2026-06-30-PLAN.md      Original implementation plan
│
└── deploy/
    ├── Caddyfile           Production reverse proxy (TLS + rate limit + headers)
    └── nginx.conf.example  Alternative to Caddy
```

**Dependency direction:** `contracts/` has no imports from `src/`. The API layer (`src/api/`) imports only from `contracts/` and `src/config`. The storage layer (`src/storage/`) imports from `contracts/` for types and defines its own schema. Nothing imports from `src/storage/` except `src/api/deps.py` (the wiring point).

## API at a glance

All endpoints require `X-API-Key`. Write endpoints also accept `X-Actor` (identifies the caller in audit fields; defaults to `"api"`).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/people` | Create a person |
| GET | `/people` | List people (`?active_only=true`) |
| GET | `/people/{id}` | Get one person |
| PATCH | `/people/{id}` | Update a person |
| POST | `/teams` | Create a team |
| GET | `/teams` | List teams (`?active_only=true`) |
| GET | `/teams/{id}` | Get team by UUID |
| GET | `/teams/by-slug/{slug}` | Get team by slug |
| PATCH | `/teams/{id}` | Update a team |
| GET | `/role_kinds` | List role kinds |
| GET | `/role_kinds/{id}` | Get one role kind |
| POST | `/memberships` | Create a membership |
| GET | `/memberships` | List memberships (filterable) |
| GET | `/memberships/{id}` | Get one membership |
| PATCH | `/memberships/{id}` | Update a membership |
| POST | `/memberships/{id}/end` | End a membership (set ended_at) |

See [docs/API.md](docs/API.md) for full request/response shapes, query parameters, error codes, and curl examples.

## Testing

The test suite has two modes:

**Fast (in-memory, no Docker required):**
```bash
uv run pytest --ignore=tests/test_postgres_adapter.py -v
```

This runs ~60 tests using `InMemoryStorageAdapter` injected via FastAPI's `dependency_overrides`. Tests cover all endpoints, error paths, and filter combinations. Runs in under 5 seconds.

**Full (includes Postgres integration):**
```bash
docker compose up -d postgres
uv run pytest -v
```

`tests/test_postgres_adapter.py` runs the same behavioral assertions against a live Postgres instance. Requires `DATABASE_URL` in `.env` pointing at the running container.

## Where to find things

- [docs/API.md](docs/API.md) — endpoint reference with curl examples and query recipes
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layered design, key decisions, and how-to guides for extending the system
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — production deployment, TLS, rate limiting, secret handling
- [docs/archive/2026-06-30-DESIGN.md](docs/archive/2026-06-30-DESIGN.md) — original design spec
- [docs/archive/2026-06-30-PLAN.md](docs/archive/2026-06-30-PLAN.md) — original implementation plan

Machine-readable OpenAPI schema: `GET /openapi.json`. Interactive Swagger UI: `GET /docs`.

## Status

v1 shipped on 2026-06-30. Four base tables, 16 endpoints, two storage adapters, 63 passing tests.

**Not in v1 (per design non-goals):**

- Connectors layer — no Discord, Google Workspace, GitHub, or Notion sync. Connectors are designed to hang off the HTTP API when built.
- Extension tables — `person_identifiers` (Discord ID, GitHub handle, UofT email) and `team_metadata` are reserved but not implemented. Adding them does not require touching base tables.
- Permission enforcement — the API exposes primitives (memberships, admin flag) from which downstream systems derive access rules. No policy engine lives here.
- Admin UI — officer edits go through whatever admin surface is chosen (NocoDB, Directus, direct SQL, or a custom app).
- Pagination — list endpoints return all matching rows. Adequate for UTMIST's roster size; add limit/offset when needed.
