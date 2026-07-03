# Developer onboarding

The single path from a fresh clone to your first merged change. It ties the
per-service docs together rather than repeating them — where a service README
already explains something, this guide links to it.

Two tracks:

- **Know this stack already?** Follow the [Quickstart](#quickstart) and skip the rest.
- **New to Python/Node/Docker, or new to this repo?** Read
  [Prerequisites](#prerequisites-new-to-this-stack) first, then work down the page.

The whole platform is three services. You rarely need all of them at once — stand
up only what you're touching.

| Service | Port | What it is |
|---------|------|------------|
| [`team-tracking`](../services/team-tracking/README.md) | 8000 | The directory — people, teams, roles, identities. Source of truth. |
| [`documentation-system`](../services/documentation-system/README.md) | 8001 | The docs catalog. Validates owners against team-tracking. |
| [`discord-bot`](../discord-bot/README.md) | 3001 (playground) | Discord slash commands + a browser playground that needs no Discord token. |

---

## Quickstart

Prerequisites: Docker, Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Node 20+, git.

**Directory API (team-tracking):**

```bash
cd services/team-tracking
cp .env.example .env
docker compose up -d postgres
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn src.api.app:app --reload --port 8000
```

Swagger at `http://localhost:8000/docs`. Dev API key: `dev-api-key-change-me`
(pass as `X-API-Key`).

**Catalog API (documentation-system)** — same shape, different ports:

```bash
cd services/documentation-system
cp .env.example .env
docker compose up -d postgres
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn src.api.app:app --reload --port 8001
```

Swagger at `http://localhost:8001/swagger` (not `/docs` — that path is a real
router here). Same dev key. Its Postgres runs on **5434** so it coexists with
team-tracking's on **5433**.

**Discord bot — playground mode** (recommended dev loop, no Discord token):

```bash
cd discord-bot
cp .env.example .env
npm install
npm run dev:web
```

Open `http://127.0.0.1:3001`, paste `100000000000000000` into "Acting as", pick
a command, run it. `Ctrl+C` tears the whole stack down. This one command boots
its own scratch team-tracking + throwaway DB, so you do **not** need port 8000
running for it.

Stuck, or new to this stack? Keep reading.

---

## Prerequisites (new to this stack?)

Install these once per machine. The two APIs are Python; the bot is Node; both
use Docker for their local Postgres.

- **git** — you have it if `git --version` works.
- **Docker** ([Docker Desktop](https://www.docker.com/products/docker-desktop/)) —
  runs each service's local Postgres. `docker compose up -d postgres` starts it;
  the data lives in a named volume that survives reboots.
- **Python 3.11+** and **[`uv`](https://github.com/astral-sh/uv)** — `uv` is the
  package manager and runner for both APIs. It creates the virtualenv, installs
  deps (`uv sync`), and runs commands inside it (`uv run ...`). You do not
  `pip install` or activate a venv by hand. Install `uv`, and it manages Python
  for you.
- **Node 20+** — for the discord-bot. Check with `node --version`. The bot reads
  its `.env` via Node's built-in `--env-file`, so no `dotenv` package needed.

Sanity check: `git --version`, `docker --version`, `uv --version`, `node --version`
should all print a version.

---

## The 10-minute mental model

Read this before touching code; see [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full picture.

**team-tracking is the foundation — everything references it.** documentation-system
validates every doc's owner id against team-tracking. The discord-bot reads and
writes the directory over HTTP. Each service owns its **own** database; they never
share tables, and everything talks over HTTP (no in-process consumers).

```
                          validates owner ids +
                          resolves labels over HTTP
  documentation-system  ───────────────────────────▶   team-tracking
   (docs catalog)                                        (directory / source of truth)
        ▲                                                        ▲
        │ degrades gracefully                                    │
        │ if the directory is down ◀─────────────────────────────┘
                                                                 │  slash commands
                                                        discord-bot
                                                        (Discord ↔ directory)
```

Both APIs are built the same way on purpose — learning one gives you ~80% of the
other. The core conventions (the `contracts/` Protocol boundary, swappable
storage adapters, scoped API-key auth, attested actor, Alembic migrations) are
listed in the [root README → Working conventions](../README.md#working-conventions)
and explained in [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Run the platform, in order

Most tasks need only one service. If you need the full chain (bot → directory,
or catalog with real owner validation), bring them up in this order:

1. **team-tracking first** (port 8000) — it's the source of truth. Follow its
   [Quick start](../services/team-tracking/README.md#quick-start).
2. **Seed one identity** so there's something to reference. With team-tracking
   running:

   ```bash
   curl -X POST http://localhost:8000/people \
     -H "X-API-Key: dev-api-key-change-me" \
     -H "Content-Type: application/json" \
     -d '{"display_name":"Your Name","primary_email":"you@example.com","access_level":"superuser"}'
   ```

3. **Then the consumer you're working on:**
   - **Catalog with real ownership validation** — start documentation-system and
     point its `DIRECTORY_*` config at `http://localhost:8000`.
   - **Discord bot, real Discord surface** — issue a scoped key against **main**
     (port 8000) and put it in `discord-bot/.env` as `DIRECTORY_API_KEY`, then
     `npm start`. Full steps, including the key scopes, are in the
     [discord-bot README → Complete startup](../discord-bot/README.md#complete-startup-from-cold).
   - **Discord bot, playground** — just `npm run dev:web`; it needs none of the
     above (it runs its own scratch team-tracking on 8001).

---

## Make your first contribution

The end-to-end loop. The per-service CONTRIBUTING docs have the code-level
walkthroughs (add an endpoint, add a storage method, write a migration) — this
is the workflow around them.

1. **Branch off `staging`.** Never commit straight to `main`; a CI guard rejects
   PRs to `main` that don't come from `staging` (see below).

   ```bash
   git switch staging && git pull
   git switch -c your-feature
   ```

2. **Copy the nearest example.** The codebase is intentionally repetitive so
   patterns are easy to imitate. When adding something, find the closest existing
   case and mirror its shape. Read the CONTRIBUTING doc for the service you're
   touching first:
   - [team-tracking CONTRIBUTING](../services/team-tracking/docs/CONTRIBUTING.md)
   - [documentation-system CONTRIBUTING](../services/documentation-system/docs/CONTRIBUTING.md)

3. **Run the fast tests locally** before you push. For either API:

   ```bash
   cd services/<service>
   uv run pytest --ignore=tests/test_postgres_adapter.py   # fast, in-memory adapter
   ```

   For the bot: `cd discord-bot && npm test`.

4. **Open a PR into `staging`.** Every PR runs
   [`ci.yml`](../.github/workflows/ci.yml): full test suites against real
   Postgres, `ruff` lint, and Docker builds with boot smoke tests. Green CI is
   required.

5. **Merging deploys.** Merging to `staging` deploys to Railway **staging**;
   merging `staging → main` deploys to **production**. PRs to `main` additionally
   run [`main-source-guard`](../.github/workflows/main-source-guard.yml), which
   enforces that they originate from `staging`. Operators: see
   [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md).

---

## Troubleshooting

- **Port already in use (5433 / 5434 / 8000 / 8001).** team-tracking's dev
  Postgres is 5433, documentation-system's is 5434 — deliberately different so
  they coexist. If a port is taken, find the process (`lsof -i :5433`) or stop a
  stray `docker compose` from another service.
- **`relation does not exist` / empty tables.** You skipped
  `uv run alembic upgrade head`. Run it from the service directory after Postgres
  is up.
- **Bot says "directory is temporarily unavailable."** Your `DIRECTORY_API_KEY`
  is invalid against main — often a key that was issued against a scratch DB that
  got wiped. Verify it:

  ```bash
  curl http://localhost:8000/api-keys/self -H "X-API-Key: <key-from-.env>"
  ```

  A `401` means reissue it against **main** (port 8000) and update `.env`.
- **`/docs` 404s on the catalog.** Its Swagger UI is at `/swagger`; `/docs` is a
  real docs-resource router on that service.
- **`uv: command not found` / `docker: command not found`.** Revisit
  [Prerequisites](#prerequisites-new-to-this-stack).

---

## Where to go next

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the cross-service data flow and why the
  conventions exist.
- [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md) — deploy/operate runbook.
- Per-service API references:
  [team-tracking](../services/team-tracking/docs/API.md),
  [documentation-system](../services/documentation-system/docs/API.md).
