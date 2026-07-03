# UTMIST Ops Platform

Internal operations infrastructure for UTMIST — the canonical record of *who runs
the org* and *what the org owns*, exposed as small HTTP services that everything
else can build on.

UTMIST is a student org with rotating leadership and mixed technical fluency. This
platform exists so that knowledge — who's on which team, where the important docs
live — survives leadership transitions instead of walking out the door when someone
graduates. The pieces are designed to be self-hostable, boring to run, and easy for
the next cohort to pick up.

## What's here

The platform is decomposed into small services, each a **source of truth** for one
domain and each reachable only over HTTP:

| Service | Domain | Status |
|---------|--------|--------|
| [`services/team-tracking/`](services/team-tracking/README.md) | People, teams, roles, memberships + external identity mapping | Shipped (v1) |
| [`services/documentation-system/`](services/documentation-system/README.md) | Catalog of URLs (docs/sheets/repos/videos) with owners, tags, snapshots | Shipped (v1) |
| [`discord-bot/`](discord-bot/README.md) | Discord slash-command frontend for the directory (`/link`, `/whoami`, `/seed`, `/team`, `/my-teams`) — plus a Discord-shaped web playground for iteration without a Discord token | Shipped (v1) |
| Search / retrieval plugin | Full-text + semantic search over the catalog | Deferred (not built) |

## How the two services relate

The directory (`team-tracking`) is the foundational service. The documentation
catalog (`documentation-system`) is a **consumer** of it: when you catalog a doc and
say "the Partnerships team owns this," the catalog validates that team id against the
directory over HTTP and resolves a human-readable label for it.

```
                          validates owner ids +
                          resolves labels over HTTP
  documentation-system  ───────────────────────────▶   team-tracking
   (docs catalog)                                        (directory / source of truth)
        ▲                                                        │
        │ degrades gracefully                                    │
        │ if the directory is down ◀─────────────────────────────┘
```

Two properties matter here:

- **The directory is a hard dependency for *meaning*, not for *availability*.** You
  can't tag a doc with a meaningful org owner unless there's an org model to point
  at — that's why the directory is built first (see
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)).
- **The catalog uses `degrade-on-directory-down`.** If the directory is unreachable,
  ingest doesn't block: the owner id is stored, the label is left null with a
  warning, and a later read or update backfills it once the directory is reachable
  again. An outage in the directory never takes the catalog down with it.

The full cross-service data flow — ingest → owner validation → label resolution or
degrade → backfill — is documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Build roadmap

The services are built in dependency order — each layer needs the one beneath it:

1. **Directory** (`team-tracking`) — *done.* The org model everything else references.
2. **Documentation catalog** (`documentation-system`) — *done.* References the
   directory for ownership.
3. **Search / retrieval** — *deferred, not built.* Full-text + semantic search over
   the catalog's stored content snapshots. The snapshots are already captured for
   this; the search surface itself is out of scope until it's actually needed.

## Repo layout

```
UTMIST-Prototypes/
├── README.md                   You are here — platform overview
├── .github/workflows/ci.yml    CI — tests, lint, Docker builds on every PR to main
├── docs/
│   └── ARCHITECTURE.md          Cross-service architecture (how the pieces fit)
│
├── services/                   HTTP source-of-truth services — one folder each
│   ├── team-tracking/           Directory service — source of truth for the org
│   │   ├── README.md            Service overview + quick start
│   │   └── docs/                API.md, ARCHITECTURE.md, DEPLOYMENT.md, CONTRIBUTING.md
│   │
│   └── documentation-system/    Documentation catalog service
│       ├── README.md            Service overview + quick start
│       └── docs/                API.md, ARCHITECTURE.md, DEPLOYMENT.md, CONTRIBUTING.md
│
└── discord-bot/                Discord frontend + web playground for the directory
    ├── README.md               Service overview + complete startup guide
    └── src/                    Node.js — thin over team-tracking, no local DB
```

Each service is self-contained: its own dependencies, its own Postgres, its own
tests, its own docs. You can run, deploy, and reason about each one on its own — and
new source-of-truth services drop into `services/` following the same shape.

## Getting started

There's no top-level bootstrap — each service has its own quick start, and you only
need to stand up the ones you're working on. Follow the service READMEs rather than
re-deriving the steps here:

- **Directory:** [`services/team-tracking/README.md` → Quick start](services/team-tracking/README.md#quick-start).
  Runs on port **8000**.
- **Catalog:** [`services/documentation-system/README.md` → Quick start](services/documentation-system/README.md#quick-start).
  Runs on port **8001**; its Postgres is on **5434**. Ports are chosen so both
  services can run side by side locally.
- **Discord bot:** [`discord-bot/README.md` → Complete startup](discord-bot/README.md#complete-startup-from-cold).
  Two modes — a real Discord surface (`npm start`, needs a bot token) and a
  browser-based web playground (`npm run dev:web`, no token needed). The
  playground orchestrator manages its own ephemeral team-tracking on port
  **8001** — the same port `documentation-system` uses, so don't run both at
  once locally without changing one of the ports.

If you want the catalog to actually validate ownership against a live directory, run
`team-tracking` first and point the catalog's `DIRECTORY_*` config at it (see the
catalog's `DEPLOYMENT.md`). Without a reachable directory the catalog still runs — it
just degrades ownership labels, by design.

## Shared conventions

Both services are built the same way on purpose, so someone who learns one already
mostly knows the other:

- **`contracts/` Protocol boundary** — each service has a `contracts/` package of
  Pydantic domain types plus `Protocol` interfaces. Application code depends on the
  Protocols, never on a concrete implementation.
- **Swappable storage adapters** — an `InMemoryStorageAdapter` for fast tests and a
  `PostgresStorageAdapter` for production, both satisfying the same Protocol.
- **Scoped API-key auth** — every request carries an `X-API-Key`. Keys are
  Argon2-hashed in the database and carry a set of per-resource scopes.
- **Attested actor** — the actor stamped on audit fields is the authenticated key's
  own identity. A caller can't claim to be someone else.
- **Per-request audit log** — middleware logs every request with its resolved actor.
- **Alembic migrations** — schema changes are versioned migrations, applied with
  `alembic upgrade head`.
- **API-only, nothing runs inside** — there are no in-process consumers; everything
  talks to these services over HTTP against their OpenAPI contract.
- **CI-gated changes** — every pull request to `main` runs
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml): the service test suites
  (against a real Postgres), `ruff` lint, and Docker image builds. Branch protection
  keeps anything red from merging.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for why these conventions exist
and how they play out across service boundaries.

## Where to go next

- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — the cross-service picture:
  API-only source-of-truth principle, the ownership-validation + degrade data flow,
  and the shared conventions.
- **Directory service** — [`services/team-tracking/README.md`](services/team-tracking/README.md) and
  its [`docs/`](services/team-tracking/docs/) (`API.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`,
  `CONTRIBUTING.md`).
- **Catalog service** — [`services/documentation-system/README.md`](services/documentation-system/README.md)
  and its [`docs/`](services/documentation-system/docs/) (`API.md`, `ARCHITECTURE.md`,
  `DEPLOYMENT.md`, `CONTRIBUTING.md`).
- **Discord bot** — [`discord-bot/README.md`](discord-bot/README.md). Covers the
  bot's neutral command shape (a single handler serves both Discord and web
  surfaces), the `dev:spoof` scope safety model, and the orchestrated web
  playground with its ephemeral scratch DB.

New contributor? Start with this README for orientation, read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) to see how the pieces fit, then dive
into whichever service's README and `docs/CONTRIBUTING.md` you'll be working in.
