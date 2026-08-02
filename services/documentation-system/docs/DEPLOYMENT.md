# documentation-system — operational reference

Runtime operations for the documentation-system service: env-var contract,
API key management (`doc-keys` CLI), fetcher configuration, and the
team-tracking dependency.

**Infrastructure** — how the service actually runs in staging + production —
lives in the platform-wide runbook:

- **[`docs/RAILWAY-DEPLOYMENT.md`](../../../docs/RAILWAY-DEPLOYMENT.md)** — Railway + Neon setup and the branching/auto-deploy flow.
- **[`docs/DEPLOYMENT-HISTORY.md`](../../../docs/DEPLOYMENT-HISTORY.md)** — how we got there and the bugs we hit.

For local dev, the [README quickstart](../README.md) is enough — this file is
about the service in a real (staging / production) environment.

## What this service depends on

- **Postgres 16.** Managed via Neon in staging/production (see the runbook);
  a Postgres 16 container locally. Schema uses `gen_random_uuid()`, standard
  in modern Postgres core.
- **A reachable team-tracking directory** — the source of truth for owners.
  See the directory-dependency section below; the service *runs* without it
  but ownership validation degrades.
- **A reachable connectors service** — fetches content for the Google
  sources. See "The connectors dependency" below: a connectors *outage*
  degrades gracefully at request time, but a missing `CONNECTORS_API_KEY`
  blocks *boot* outside `local` (see `verify_production_secrets()` below).

## Environment variables

All configuration is env-driven (`src/config.py`, loaded from the process environment or a
`.env` file). Six variables:

| Env var | Setting | Default | Purpose |
|---------|---------|---------|---------|
| `DATABASE_URL` | `database_url` | `postgresql+psycopg://docs:dev_password@localhost:5434/docs` | Postgres connection (SQLAlchemy + psycopg driver) |
| `API_KEY` | `api_key` | `dev-api-key-change-me` | Bootstrap admin key. **Change or unset in prod.** |
| `DIRECTORY_BASE_URL` | `directory_base_url` | `http://localhost:8000` | Base URL of the team-tracking directory |
| `DIRECTORY_API_KEY` | `directory_api_key` | `dev-api-key-change-me` | API key this service uses to call the directory |
| `CONNECTORS_BASE_URL` | `connectors_base_url` | `http://localhost:8005` | Base URL of the connectors service (fetches Google source content) |
| `CONNECTORS_API_KEY` | `connectors_api_key` | `dev-api-key-change-me` | API key this service uses to call connectors. **Must be overridden outside `local`** — `verify_production_secrets()` refuses to boot on the dev default (see [`src/config.py`](../src/config.py)). |

Staging + production values live in **Railway** — set per environment via the
runbook's env-var contract. Keep the defaults ONLY for local dev; anything
running against a real Neon branch must set a strong `API_KEY` and its own
scoped `DIRECTORY_API_KEY` and `CONNECTORS_API_KEY` (issued by the
provisioning script / connectors' `connectors-keys` CLI — see the runbook).

> **A staging or production deploy that has not set `CONNECTORS_API_KEY` will
> refuse to boot.** `verify_production_secrets()` checks it alongside `API_KEY`
> and `DIRECTORY_API_KEY` — this is not optional config once `docs_env` is
> `staging`/`production`.

## Postgres

- **Local:** `docker compose up -d postgres` inside `services/documentation-system/`
  spins up the dev DB (host port `5434`, chosen so it doesn't collide with
  team-tracking's `5433`). Connection string uses the `psycopg` (v3) driver:
  `postgresql+psycopg://<user>:<pass>@<host>:<port>/<db>`.
- **Staging / production:** Neon manages this. Each environment points at its
  own branch of the `documentation-system` Neon project. See the runbook.

## Migrations (Alembic)

Schema is managed by Alembic (`migrations/`). Alembic reads the same
`DATABASE_URL` the app uses — `migrations/env.py` pulls it from
`src.config.get_settings()`, one source of truth.

Four migrations ship today:

- **`001_initial_schema`** — creates `sources`, `docs`, `doc_tags`, `api_keys`
  and their indexes.
- **`002_seed_sources`** — seeds the eight built-in sources (`web`, `github`,
  `gdrive`, `gdocs`, `gsheets`, `gslides`, `notion`, `youtube`).
- **`003_doc_grants`** — adds the `doc_grants` table behind per-doc visibility,
  with the grantee-shape CHECK and both uniqueness constraints (including the
  partial index that catches duplicate `org` grants, which the plain unique
  constraint can't because `grantee_id` is NULL there).
- **`004_docs_url_unique_active`** — enforces the dedup invariant at the DB level
  with a partial unique index on `url_normalized WHERE active`.

> **`004` is a data migration, not just a schema one.** It first collapses any
> pre-existing duplicate active rows for the same `url_normalized` (keeping the
> earliest by `created_at`, id as tiebreak) and only *then* creates the index —
> creating the index first would fail on dirty data. Expect it to modify rows,
> and take a Neon branch snapshot before running it on an environment whose data
> you care about.

**On Railway,** migrations run automatically via `railway.json`'s
`preDeployCommand: "alembic upgrade head"` before every deploy — idempotent,
transactional, no manual step. **Locally,** run `uv run alembic upgrade head`
after cloning or when new migrations land.

## Running the server locally

```bash
uv sync --extra dev
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8001
```

The service listens on **8001** locally by convention (team-tracking uses
`8000`). In Railway, `PORT` is set to `8000` explicitly and the start command
in `railway.json` picks that up.

Health/observability: the audit middleware emits one JSON log line per
request to stdout. On Railway, view via `railway service logs --service
documentation-system --environment <env>` or the Railway dashboard.

## Issuing API keys (`doc-keys` CLI)

Consumers authenticate with scoped keys issued via the `doc-keys` CLI, which talks
**directly to the database** (`DATABASE_URL` must be set/reachable from wherever you run
it). See [`docs/API.md`](API.md) for how consumers present the key.

```bash
# Issue a read+write key for an ingestion bot.
# The plaintext key is printed to STDOUT exactly once — capture it now.
uv run doc-keys issue --name discord-bot --scopes docs:read docs:write

# Issue a read-only key for a dashboard.
uv run doc-keys issue --name dashboard --scopes docs:read

# List keys (metadata only — never plaintext).
uv run doc-keys list --active-only

# Revoke a compromised key by its id.
uv run doc-keys revoke <api_key_id>
```

Notes:

- Scopes are `docs:read`, `docs:write`, and `admin` (wildcard). Grant the minimum needed.
- Human-readable metadata (name, prefix, scopes, id) is printed to **stderr**; only the
  plaintext key goes to **stdout**, so `... issue ... > key.txt` captures just the key.
- `--actor` (global flag, default `cli`) is stamped on `created_by` / `updated_by`.
- Name keys after the consumer — that name is the attested actor in the audit log.

## Configuring / enabling fetchers

Fetchers produce the best-effort content snapshot at ingest and on `POST /docs/{id}/refetch`.
Which sources get fetched is determined by two things that must agree:

1. The source's `content_fetch_enabled` flag (in the `sources` table).
2. A `Fetcher` registered for that `source_id` in `default_registry()`
   (`src/fetch/registry.py`).

`web` and `github` fetch in-process. The four Google sources (`gdrive`, `gdocs`, `gsheets`,
`gslides`) fetch via the [connectors](../../connectors/) service over HTTP
(`ConnectorsFetcher`, registered in `src/fetch/registry.py`); migration `006` flipped their
`content_fetch_enabled` to `true` to match. `notion` and `youtube` remain auth-gated:
`content_fetch_enabled` is `false` and no fetcher is registered, so ingest records the doc
without a snapshot. Enabling a new source is a **code change**, not just config — implement
the `Fetcher`, register it, and flip `content_fetch_enabled` (see
[`docs/CONTRIBUTING.md`](CONTRIBUTING.md)).

Fetcher-specific env vars: `CONNECTORS_BASE_URL` / `CONNECTORS_API_KEY` (see above) configure
the Google sources' fetcher. **Deploy order matters:** deploy connectors first, then set
these two vars on documentation-system, then deploy documentation-system. Deploying
documentation-system first either boots it into a `CONNECTORS_API_KEY` still on the dev
default (refused by `verify_production_secrets()` outside `local`) or, once that's set,
points it at a connectors instance that isn't up yet — Google-source fetches would then fail
at request time (degraded, not fatal — see the connectors dependency section below) until
connectors is reachable.

## The team-tracking directory dependency

The documentation-system validates owners against the team-tracking directory over HTTP.
It is a **runtime dependency** but a **soft** one:

- **When the directory is reachable:** owner ids are validated (`GET /teams/{id}`,
  `GET /people/{id}`) and labels are cached on the doc. An unknown id is rejected with
  **HTTP 400**.
- **When the directory is down** (connection failure or 5xx): the service **degrades**.
  Ingest and update still succeed — the owner id is stored, the label is left null, and a
  warning is returned. Labels are backfilled automatically on the next read or update once
  the directory is reachable again.

Operationally this means a directory outage will **not** take the catalog down; it only
delays owner-label resolution and temporarily disables the "unknown owner id" rejection.
Ensure `DIRECTORY_BASE_URL` and `DIRECTORY_API_KEY` are correct so validation works in
steady state.

## The connectors dependency

The documentation-system fetches content for the Google sources (`gdrive`, `gdocs`,
`gsheets`, `gslides`) by calling the [connectors](../../connectors/) service over HTTP. It is
a runtime dependency with **two different failure modes** depending on when it's down:

- **At boot, outside `local`:** hard-required. `verify_production_secrets()` refuses to start
  if `CONNECTORS_API_KEY` is still the built-in dev default — see "Environment variables"
  above.
- **At request time:** soft for ingest, hard for refetch — deliberately different, since
  ingest degrading a whole batch is worse than a single explicit refetch failing loudly.
  On `POST /docs`, if connectors is unreachable or errors, `ConnectorsFetcher` raises
  `FetchError`, which `ingest_doc` catches the same way it catches a `web`/`github` fetch
  failure: the doc is still catalogued, just without a content snapshot, and a warning is
  returned — a connectors outage never fails `POST /docs`. On `POST /docs/{id}/refetch`,
  the same `FetchError` is instead surfaced to the caller as an HTTP 502 (see
  `src/api/routers/docs.py`): refetch is an explicit user-initiated action, so it fails
  loudly rather than silently leaving stale content in place.

**Deploy order:** connectors first, then set `CONNECTORS_BASE_URL` / `CONNECTORS_API_KEY` on
documentation-system, then deploy documentation-system — see "Configuring / enabling
fetchers" above for what goes wrong if the order is reversed.
