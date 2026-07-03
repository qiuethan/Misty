# documentation-system — deployment

Running the service in production (or a shared staging box). Assumes you've read the
[README](../README.md). For local dev, the README quickstart is enough — this doc is about
a real, persistent deployment.

## What you need

- **Postgres 15+** (the dev compose file uses `postgres:16`). The schema uses
  `gen_random_uuid()`, available in modern Postgres core.
- **Python 3.11+** and [uv](https://github.com/astral-sh/uv).
- **A reachable team-tracking directory** — the source of truth for owners. See the
  directory-dependency section below; the service runs without it but ownership validation
  degrades.

## Environment variables

All configuration is env-driven (`src/config.py`, loaded from the process environment or a
`.env` file). Four variables:

| Env var | Setting | Default | Purpose |
|---------|---------|---------|---------|
| `DATABASE_URL` | `database_url` | `postgresql+psycopg://docs:dev_password@localhost:5434/docs` | Postgres connection (SQLAlchemy + psycopg driver) |
| `API_KEY` | `api_key` | `dev-api-key-change-me` | Bootstrap admin key. **Change or unset in prod.** |
| `DIRECTORY_BASE_URL` | `directory_base_url` | `http://localhost:8000` | Base URL of the team-tracking directory |
| `DIRECTORY_API_KEY` | `directory_api_key` | `dev-api-key-change-me` | API key this service uses to call the directory |

Production checklist:

- Set a real `DATABASE_URL` pointing at your managed/hosted Postgres.
- **Do not** keep the default `API_KEY`. Either set it to a strong random secret used only
  for bootstrap/admin, or issue per-consumer scoped keys (below) and leave `API_KEY` as a
  tightly-held admin key. Never share the bootstrap key with individual consumers.
- Point `DIRECTORY_BASE_URL` at the deployed team-tracking service and set
  `DIRECTORY_API_KEY` to a `read`-scoped key issued by that service.

## Postgres setup

The bundled `docker-compose.yml` is for local dev (Postgres on host port **5434**, so it
doesn't collide with team-tracking's default). In production, point `DATABASE_URL` at your
real database instead.

```bash
# Local / self-hosted via compose:
docker compose up -d postgres
```

The connection string uses the `psycopg` (v3) driver:
`postgresql+psycopg://<user>:<password>@<host>:<port>/<db>`.

## Migrations (Alembic)

Schema is managed by Alembic (`migrations/`). Alembic reads the same `DATABASE_URL` your
app uses — `migrations/env.py` pulls it from `src.config.get_settings()`, so there's one
source of truth for the connection string.

Apply all migrations before starting the server:

```bash
uv run alembic upgrade head
```

Two migrations ship today:

- **`001_initial_schema`** — creates `sources`, `docs`, `doc_tags`, `api_keys` and their
  indexes.
- **`002_seed_sources`** — seeds the eight built-in sources (`web`, `github`, `gdrive`,
  `gdocs`, `gsheets`, `gslides`, `notion`, `youtube`).

Run migrations as a discrete deploy step (before rolling the app), not from the app
process.

## Running the server

```bash
uv sync --extra dev              # or without --extra dev for a runtime-only install
uv run uvicorn src.api.app:app --host 0.0.0.0 --port 8001
```

Put a reverse proxy (Caddy/nginx) in front for TLS. The audit middleware honors
`X-Forwarded-For` / `X-Real-IP`, so set those on the proxy to log real client IPs. The
service listens on **8001** by convention (team-tracking uses 8000).

Health/observability: the audit middleware emits one JSON log line per request to stdout —
point your log aggregator (journald, Loki, CloudWatch, …) at the process stdout.

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

Today only `web` and `github` have both, so only those sources are fetched. The other six
sources (`gdrive`, `gdocs`, `gsheets`, `gslides`, `notion`, `youtube`) are auth-gated:
`content_fetch_enabled` is `false` and no fetcher is registered, so ingest records the doc
without a snapshot. Enabling a new source is a **code change**, not just config — implement
the `Fetcher`, register it, and flip `content_fetch_enabled` (see
[`docs/CONTRIBUTING.md`](CONTRIBUTING.md)). There are no fetcher-specific env vars in v1.

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
