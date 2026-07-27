# Developer onboarding

The single path from a fresh clone to your first merged change. It ties the
per-service docs together rather than repeating them — where a service README
already explains something, this guide links to it.

Two tracks:

- **Know this stack already?** Follow the [Quickstart](#quickstart) and skip the rest.
- **New to Python/Node/Docker, or new to this repo?** Read
  [Prerequisites](#prerequisites-new-to-this-stack) first, then work down the page.

The platform is **five backend services plus the Discord bot**. You almost never
need all of them at once — stand up only what you're touching.

| Service | Port | DB | What it is |
|---------|------|----|------------|
| [`team-tracking`](../services/team-tracking/README.md) | 8000 | Postgres :5433 | The directory — people, teams, roles, identities. Source of truth. |
| [`documentation-system`](../services/documentation-system/README.md) | 8001 | Postgres :5434 | The docs catalog. Validates owners against team-tracking; per-doc visibility + grants. |
| [`llm`](../services/llm/README.md) | 8002 | — | Stateless `POST /chat` proxy over Amazon Bedrock. No DB. |
| [`verification`](../services/verification/README.md) | 8003 | Postgres :5434 ⚠️ | Email one-time codes (request / confirm). Backs `/link` and `/add-email`. |
| [`meeting`](../services/meeting/README.md) | 8004 | — | **Stateful, ephemeral.** Live voice transcription → minutes PDF. No DB; state is in-process only. |
| [`discord-bot`](../discord-bot/README.md) | 3001 (playground) | — | Discord slash commands + a browser playground that needs no Discord token. |

> ⚠️ **Known port clash:** `documentation-system` and `verification` both bind
> host port **5434** for their dev Postgres
> (`services/*/docker-compose.yml`). They cannot run at the same time as
> written. If you need both, override one:
> `docker compose run -p 5435:5432 postgres` and point that service's
> `DATABASE_URL` at 5435.

Only `team-tracking`, `documentation-system`, and `verification` own a database
(and therefore Alembic migrations). `llm` and `meeting` are DB-free.

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

**Verification API** — same shape again, port **8003**, Postgres **5434** (see
the clash warning above):

```bash
cd services/verification
cp .env.example .env
docker compose up -d postgres
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn src.api.app:app --reload --port 8003
```

`EMAIL_BACKEND=fake` is the default — it drops mail instead of sending, so no
Resend/Gmail credentials are needed for local work.

**LLM API** — no Docker, no database:

```bash
cd services/llm
cp .env.example .env
uv sync --extra dev
uv run uvicorn src.api.app:app --reload --port 8002
```

`POST /chat` requires the `chat` scope and real AWS credentials for Bedrock;
without them the service still boots and `/health` answers.

**Meeting API** — no Docker, no database, no ffmpeg binary (PyAV bundles its
own):

```bash
cd services/meeting
cp .env.example .env
uv sync --extra dev
uv run uvicorn src.api.app:app --reload --port 8004
```

Live transcription needs AWS Transcribe credentials plus a reachable `llm`
service; the test suite fakes both, so you only need those to exercise a real
recording.

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

Install these once per machine. All five services are Python; the bot is Node.
Only the three DB-backed services need Docker (for their local Postgres).

- **git** — you have it if `git --version` works.
- **Docker** ([Docker Desktop](https://www.docker.com/products/docker-desktop/)) —
  runs the local Postgres for the three DB-backed services.
  `docker compose up -d postgres` starts it; the data lives in a named volume
  that survives reboots. Not needed at all for `llm` or `meeting`.
- **Python 3.11+** and **[`uv`](https://github.com/astral-sh/uv)** — `uv` is the
  package manager and runner for every Python service. It creates the
  virtualenv, installs deps (`uv sync`), and runs commands inside it
  (`uv run ...`). You do not `pip install` or activate a venv by hand. Install
  `uv`, and it manages Python for you. The repo is a single **uv workspace**:
  one root `pyproject.toml` (`services/*`, `packages/*`) and one root `uv.lock`
  cover all five services and the shared `packages/auth` (`platform_auth`)
  library — `uv sync` resolves the whole workspace even when run from a service
  subdirectory.
  No `ffmpeg` binary is needed anywhere, including for `meeting` — Opus decode
  runs in-process via PyAV, which bundles its own ffmpeg libraries.
- **Node 20+** — for the discord-bot. Check with `node --version`. The bot reads
  its `.env` via Node's built-in `--env-file`, so no `dotenv` package needed.

Sanity check: `git --version`, `docker --version`, `uv --version`, `node --version`
should all print a version.

---

## The 10-minute mental model

Read this before touching code; see [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full picture.

**team-tracking is the foundation — everything references it.** documentation-system
validates every doc's owner id against team-tracking. The discord-bot reads and
writes the directory over HTTP, and fans out to the other services for specific
commands. Each service owns its **own** database (or none); they never share
tables, and everything talks over HTTP (no in-process consumers).

```
  documentation-system ──validates owner ids──▶ team-tracking
   (docs catalog)         resolves labels        (directory / source of truth)
        ▲                                              ▲
        │ degrades gracefully if the directory is down  │
        │                                               │
        │  /doc                                         │  /link /whoami /team /seed
        └───────────────── discord-bot ─────────────────┘
                            │   │   │
              /link ────────┘   │   └──────── /record
              /add-email        │
                    ▼           ▼                  ▼
              verification    (none direct)     meeting ──/chat──▶ llm ──▶ Bedrock
              (email codes)                    (live transcript,        (stateless
                                                minutes, PDF)            proxy)
```

The bot is the only thing that talks to `verification` and `meeting`;
`meeting` is the only thing that talks to `llm` today. All five backends are
built the same way on purpose — learning one gives you ~80% of the others. The
core conventions (the `contracts/` Protocol boundary, swappable storage
adapters, scoped API-key auth, attested actor, Alembic migrations) are listed in
the [root README → Working conventions](../README.md#working-conventions) and
explained in [`ARCHITECTURE.md`](ARCHITECTURE.md).

Two services deviate deliberately, and it's worth knowing why before you read
their code:

- **`llm` and `meeting` have no database.** Their API keys are seeded from a
  `CONSUMER_KEYS` JSON env var and parsed at boot into an in-memory store, not
  an `api_keys` table. Rotating a key means editing the variable and
  redeploying; there is no `revoke` command.
- **`verification` has a database but no key table.** It uses a
  `NullApiKeyStore`, so only the bootstrap `API_KEY` authenticates — there are no
  per-consumer keys to mint. Its database holds only verification codes.
- **`meeting` is stateful.** It holds one in-memory session per live meeting.
  It cannot be horizontally scaled without sticky routing on `session_id`, and
  a restart drops every in-flight meeting. See
  [`MEETING-RECORDING.md`](MEETING-RECORDING.md) for why that trade was made.

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
   - **`/link` / `/add-email` end-to-end** — also start `verification` (8003) and
     set `VERIFICATION_BASE_URL` / `VERIFICATION_API_KEY` in `discord-bot/.env`.
     With `EMAIL_BACKEND=fake` no mail is sent; read the code out of the
     verification service's logs.
   - **`/record` end-to-end** — start `llm` (8002) **then** `meeting` (8004),
     since `meeting` calls `llm` for minutes. Set `MEETING_BASE_URL` /
     `MEETING_API_KEY` in `discord-bot/.env` and run the real Discord surface
     (`npm start`) — voice capture has no playground equivalent. Leave
     `MEETING_BASE_URL` blank and the bot still boots; `/record` just reports
     "not configured".

**Minting keys for the DB-free services.** `llm` and `meeting` have no
`api_keys` table, so their CLIs *print* a key and its `CONSUMER_KEYS` JSON entry
rather than storing it:

```bash
uv --project services/llm     run llm-keys     --name meeting     --scopes chat
uv --project services/meeting run meeting-keys --name discord-bot --scopes meetings
```

stdout is the plaintext key (shown **once** — give it to the consumer); stderr is
the JSON object you append to that service's `CONSUMER_KEYS` array before
restarting it.

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

   `llm`, `verification`, and `meeting` don't have their own CONTRIBUTING docs —
   their READMEs cover the same ground, and they follow the two above.

3. **Run the fast tests locally** before you push. For a DB-backed API
   (team-tracking, documentation-system, verification):

   ```bash
   cd services/<service>
   uv run pytest --ignore=tests/test_postgres_adapter.py   # fast, in-memory adapter
   ```

   `llm` and `meeting` have no Postgres adapter, so it's just `uv run pytest` —
   no Docker, no network, no AWS credentials (the Bedrock/Transcribe clients are
   faked via `app.dependency_overrides`).

   For the bot: `cd discord-bot && npm test`. If you touched the shared auth
   library, its own tests live alongside it: `cd packages/auth && uv run pytest`.

   Lint before pushing too — CI runs `ruff` on every Python service except
   documentation-system: `uv run ruff check . && uv run ruff format --check .`

4. **Open a PR into `staging`.** Every PR runs
   [`ci.yml`](../.github/workflows/ci.yml): full test suites against real
   Postgres, `ruff` lint, and Docker builds with boot smoke tests. Green CI is
   required. Three other workflows also fire on PRs —
   [`pr-zone-check`](../.github/workflows/pr-zone-check.yml) (warns, non-blocking,
   if a PR spans multiple CODEOWNERS zones),
   [`discord-pr-notify`](../.github/workflows/discord-pr-notify.yml) (posts to
   Discord when review is requested), and
   [`blocked-ready-automation`](../.github/workflows/blocked-ready-automation.yml)
   (keeps `blocked`/`ready` issue labels in sync from `Blocked by:` lines).

   > **`services/meeting` went to staging with no CI coverage at all** — no test
   > job, and `docker-build` skipped its image. Both are now wired up
   > (`meeting-test` + a meeting build/smoke step). `ruff format --check` is
   > still deferred there: several files are unformatted, so enabling it would
   > fail the job outright. Run `uv run ruff format .` in `services/meeting`
   > before adding that step back.

5. **Merging deploys.** Merging to `staging` deploys to Railway **staging**;
   merging `staging → main` deploys to **production**. PRs to `main` additionally
   run [`main-source-guard`](../.github/workflows/main-source-guard.yml), which
   enforces that they originate from `staging`. Operators: see
   [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md).

---

## Troubleshooting

- **Port already in use (5433 / 5434 / 8000–8004).** API ports are 8000
  team-tracking, 8001 documentation-system, 8002 llm, 8003 verification, 8004
  meeting. Dev Postgres is 5433 for team-tracking and 5434 for *both*
  documentation-system and verification. If a port is taken, find the process
  (`lsof -i :5434`) or stop a stray `docker compose` from another service.
- **documentation-system and verification can't run at once.** Both
  `docker-compose.yml` files bind host **5434**, so the second `docker compose
  up -d postgres` fails with a port-allocation error — or, worse, you connect to
  the *other* service's database and Alembic reports a revision it doesn't
  recognize. Remap one of them (`-p 5435:5432`) and update that service's
  `DATABASE_URL` to match.
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
- **Minted a directory key with a `doc_` prefix (team-tracking rejects it).**
  Both `services/team-tracking` and `services/documentation-system` declare a
  top-level `src` package, each with a console script at `src.cli:main`
  (`team-tracking-keys` and `doc-keys`). In the shared workspace venv these
  collide, so a bare `team-tracking-keys …` can resolve documentation-system's
  CLI and mint a `doc_`-envelope key — which team-tracking's auth rejects
  (`parse_prefix` in [`packages/auth/platform_auth/hashing.py`](../packages/auth/platform_auth/hashing.py)
  requires the `tt_` envelope). Always pin the project:
  `uv --project services/team-tracking run team-tracking-keys …` (as
  `scripts/provision-directory-key.sh` does), and verify the token's prefix is
  `tt_`, not `doc_`, before using it as `DIRECTORY_API_KEY`.
- **`/record` says "not configured".** `MEETING_BASE_URL` is unset on the bot.
  That's the intended graceful degradation, not a crash — set it (plus
  `MEETING_API_KEY`) to enable the command.
- **`meeting` or `llm` refuses to start.** Outside `MEETING_ENV`/`LLM_ENV=local`
  both call `verify_production_secrets()` at boot and exit, listing every var
  that's still unset. `llm` requires `API_KEY` (changed from the dev default)
  and `AWS_REGION`; `meeting` requires those two **plus `LLM_BASE_URL` and
  `LLM_API_KEY`**. A misconfigured deploy is meant to die at boot, not on first
  request.
- **`CONSUMER_KEYS` rejected at boot.** `llm` and `meeting` both require it to be
  a **JSON array** (`[{...}]`), not a bare object or a comma-separated string.
  Anything else fails fast at startup by design.
- **`uv: command not found` / `docker: command not found`.** Revisit
  [Prerequisites](#prerequisites-new-to-this-stack).

---

## Where to go next

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the cross-service data flow and why the
  conventions exist.
- [`MEETING-RECORDING.md`](MEETING-RECORDING.md) — how `/record` splits across the
  bot's voice surface and the `meeting` service, and why it breaks two of the
  platform's conventions on purpose.
- [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md) — deploy/operate runbook.
- [`SECURITY-REVIEW-2026-07-13.md`](SECURITY-REVIEW-2026-07-13.md) — the security
  review that drove the `people:elevate` scope, SSRF guards, and doc visibility.
- Per-service references:
  [team-tracking API](../services/team-tracking/docs/API.md),
  [documentation-system API](../services/documentation-system/docs/API.md), and
  the [`llm`](../services/llm/README.md), [`verification`](../services/verification/README.md),
  and [`meeting`](../services/meeting/README.md) READMEs (those three document
  their own API surface inline).
