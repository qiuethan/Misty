# UTMIST Ops Platform

The internal operations infrastructure for UTMIST — a canonical, machine-queryable record of *who runs the org*, *what the org owns*, and *how people reach it*. Deployed and running in production.

UTMIST is a student org with rotating leadership and mixed technical fluency. Every year new leads inherit their predecessor's undocumented spreadsheets and lost Google Docs. This platform is our answer to that: **institutional knowledge that survives graduation.** Everything is exposed as HTTP APIs plus a Discord frontend, self-hostable if you ever want, deployed to Railway today because it's turnover-proof.

**Status:** Live on Railway (staging + production) with Neon Postgres backing each service. Merges to `staging` auto-deploy to staging; merges to `main` auto-deploy to production.

---

## What you can do with it

### As a UTMIST member (in Discord)

**Stable (registered globally — visible in every UTMIST server the bot is in):**

- **`/link`** — attach your Discord account to your directory record so the bot knows who you are. Public (you don't need to be linked yet).
- **`/whoami`** — see your linked identity, teams you're on, and access level. Requires you to be linked.
- **`/team`** — look up, create, rename, add/remove members, and view rosters (subcommands: `create`, `list`, `rename`, `add`, `remove`, `roster`). Reads are public; writes are admin-only.
- **`/my-teams`** — list your active memberships. Requires you to be linked.

**Beta (currently visible only in the test guild; promote by flipping `beta: false` in each command module + re-registering):**

- **`/doc`** — catalog and browse links (subcommands: `add`, `list`, `show`, `remove`), backed by documentation-system. Reads are public; writes are admin-only. Team-owner field has slug autocomplete.

### As an admin (in Discord)

- **`/seed`** — create or promote a person in the directory (member / admin / superuser). Requires admin+. Stable (visible globally). You can only grant a level at or below your own.
- **`/team create`**, **`/team add`**, **`/team remove`**, **`/team rename`** — the write subcommands are admin-gated. Stable (visible globally).

### As a developer / integration builder

Every domain has a first-class HTTP API — build your own dashboard, sync job, or automation on top:

- **[team-tracking](services/team-tracking/README.md)** — 23 endpoints across `people`, `teams`, `role_kinds`, `team_memberships`, `providers`, `person_identifiers`, `api_keys`. Full point-in-time roster queries. Scoped API keys, per-request audit log. **Actively consumed** by the Discord bot in production.
- **[documentation-system](services/documentation-system/README.md)** — endpoints over `docs` and `sources`; ingest a URL and it's normalized, dedup'd, fetched (title + snapshot for supported sources), and owner-validated against team-tracking. Ownership degrades gracefully if the directory is unreachable. **Consumed** by the Discord bot's `/doc` command group (`add`, `list`, `show`, `remove`), currently in beta.

Both APIs speak OpenAPI. Point Swagger UI or codegen at them.

### As an operator

- **Deploy is `git push`.** Merge to `staging` → Railway rebuilds and deploys staging automatically. Promote via a `staging → main` PR for production. No separate CD system.
- **Roll back is `git revert`** + push. If a migration went with it, `railway run … alembic downgrade -1` reverses the schema.
- **Manage API keys** via the `team-tracking-keys` / `doc-keys` CLIs — scoped, revocable, per-consumer, argon2-hashed at rest.

---

## The services

| Service | What it holds | Status |
|---------|---------------|--------|
| [`services/team-tracking/`](services/team-tracking/README.md) | People, teams, roles, memberships, external identity mapping (Discord/GitHub/Notion/UofT email → person) | **Deployed** (staging + prod). Directory is empty on prod until seeded. |
| [`services/documentation-system/`](services/documentation-system/README.md) | Catalog of URLs (docs/sheets/repos/videos) with owners, tags, and best-effort content snapshots | **Deployed** (staging + prod). Consumed by the bot's `/doc` command group (`add`/`list`/`show`/`remove`), currently in beta (test guild only). |
| [`discord-bot/`](discord-bot/README.md) | Discord slash-command frontend + a browser-based "web playground" for iterating on commands without a Discord token | **Deployed** (staging + prod). 5 stable commands (`/link`, `/whoami`, `/seed`, `/team`, `/my-teams`) registered globally; 1 beta (`/doc`) in test guild only. |
| Search / retrieval | Full-text + semantic search over the catalog's snapshots | Deferred (not built) |

**How they relate.** team-tracking is the foundation — everything else references it. documentation-system validates every doc's owner against team-tracking. The discord-bot's commands read/write the directory over HTTP. Each service owns its own database; they never share tables.

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

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the cross-service data flow.

---

## Repo layout

```
UTMIST-Prototypes/
├── README.md                          You are here
├── docs/
│   ├── DEVELOPMENT.md                Developer onboarding — clone to first PR
│   ├── ARCHITECTURE.md                Cross-service architecture — how the pieces fit
│   ├── RAILWAY-DEPLOYMENT.md          Deploy runbook (Railway + Neon setup, key provisioning)
│   └── DEPLOYMENT-HISTORY.md          Design decisions + lessons learned
│
├── services/                          HTTP source-of-truth services (each in its own folder)
│   ├── team-tracking/                 Directory service
│   │   ├── README.md                  Overview + quick start
│   │   ├── src/                       FastAPI + SQLAlchemy Core
│   │   ├── contracts/                 Pydantic types + Protocols (framework-free boundary)
│   │   ├── migrations/                Alembic
│   │   ├── tests/                     pytest (in-memory + real-Postgres adapters)
│   │   ├── Dockerfile, railway.json   Production image + Railway config
│   │   └── docs/                      API.md, ARCHITECTURE.md, DEPLOYMENT.md, CONTRIBUTING.md
│   │
│   └── documentation-system/          Catalog service (same shape as team-tracking)
│
├── discord-bot/                       Discord frontend + web playground
│   ├── src/                           Node.js + discord.js
│   ├── scripts/dev-web.js             Local playground orchestrator (ephemeral scratch DB)
│   ├── Dockerfile, railway.json       Production image + Railway config
│   └── test/                          node --test
│
├── scripts/
│   └── provision-directory-key.sh     Mint + wire scoped API keys per environment
│
└── .github/workflows/
    ├── ci.yml                         Tests + lint + Docker builds on every PR
    └── main-source-guard.yml          Enforces "PRs to main come from staging"
```

Each service is self-contained: its own dependencies, its own database, its own tests, its own docs. Add a new source-of-truth service by dropping it in `services/` following the same shape.

---

## Running the platform locally

New here? Start with the **[developer onboarding guide](docs/DEVELOPMENT.md)** — it walks a fresh clone through prerequisites, running the platform in order, and your first contribution.

Nothing to bootstrap at the root — stand up only what you need:

- **Directory API** — [`services/team-tracking/README.md` → Quick start](services/team-tracking/README.md#quick-start). Port **8000**.
- **Catalog API** — [`services/documentation-system/README.md` → Quick start](services/documentation-system/README.md#quick-start). Port **8001**; its Postgres on **5434** (chosen to coexist with team-tracking's dev Postgres on 5433).
- **Discord bot** — [`discord-bot/README.md`](discord-bot/README.md). Two modes:
  - `npm start` — real Discord surface (needs a bot token).
  - `npm run dev:web` — browser-based playground on `http://localhost:3001`, no Discord token needed. Orchestrates its own scratch team-tracking + ephemeral DB, so it's fully self-contained for hacking on commands.

For catalog-with-real-ownership-validation, run team-tracking first and point the catalog's `DIRECTORY_*` config at it.

---

## Working conventions

Both APIs are built the same way on purpose — learning one gives you 80% of the other:

- **`contracts/` Protocol boundary.** Each service has a `contracts/` package of Pydantic domain types plus `Protocol` interfaces. Application code depends on the Protocols, never on a concrete implementation.
- **Swappable storage adapters.** `InMemoryStorageAdapter` for fast tests, `PostgresStorageAdapter` for real runs — both satisfy the same Protocol. Tests use in-memory; a small integration test suite gates the Postgres adapter too.
- **Scoped API-key auth.** Every request carries `X-API-Key`. Keys are argon2-hashed in the DB with a set of per-resource scopes (`people:read`, `teams:write`, etc.).
- **Attested actor.** The `created_by`/`updated_by` on every audit field is the authenticated key's own name — a caller can't claim to be someone else.
- **Per-request audit log.** Middleware emits one JSON line per request with the resolved actor, endpoint, status, and duration.
- **Alembic migrations.** Schema changes are versioned; migrations run as Railway's `preDeployCommand` on every deploy.
- **API-only, nothing runs inside.** No in-process consumers; everything talks to these services over HTTP.
- **CI-gated changes.** Every PR to `staging` or `main` runs [`ci.yml`](.github/workflows/ci.yml) — full test suites against real Postgres, ruff, and Docker builds with boot smoke tests. PRs to `main` also run [`main-source-guard`](.github/workflows/main-source-guard.yml).
- **Branching = deploy.** `staging` merges deploy to Railway staging; `main` merges deploy to production.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for why these choices exist and how they compose.

---

## Where to go next

Depending on what you're here to do:

**Deploying / operating**
- [`docs/RAILWAY-DEPLOYMENT.md`](docs/RAILWAY-DEPLOYMENT.md) — the runbook (deploy, redeploy, provision keys, register commands, verify).
- [`docs/DEPLOYMENT-HISTORY.md`](docs/DEPLOYMENT-HISTORY.md) — why the platform is deployed the way it is, and the non-obvious lessons.

**Building against the APIs**
- [`services/team-tracking/docs/API.md`](services/team-tracking/docs/API.md) — all 23 endpoints with request/response shapes.
- [`services/documentation-system/docs/API.md`](services/documentation-system/docs/API.md) — ingest, retrieve, and update the catalog.

**Contributing code**
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — onboarding: clone → running locally → first PR.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the cross-service picture.
- Then whichever service you're touching: [`services/team-tracking/`](services/team-tracking/README.md), [`services/documentation-system/`](services/documentation-system/README.md), or [`discord-bot/`](discord-bot/README.md).
- Each service has a `docs/CONTRIBUTING.md` with task walkthroughs.

**New to the platform?** Start here, read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), then dive into whichever service you're most likely to touch.
