# How We Deployed

The story of how the UTMIST ops platform got from "code on a laptop" to running on Railway with staging + production environments. Written the day it happened so future volunteers know why things are the way they are.

For the operational **runbook** (how to redeploy, add a service, provision keys, verify), see [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md). This document is the story and the design decisions.

---

## What we built

- **Two live environments:** `staging` (safe test playground) and `production` (real UTMIST members).
- **Hosting:** Railway. Each service is a container built from its own `Dockerfile` on git push.
- **Databases:** Neon Postgres, one project per service, one branch per environment.
- **Discord:** two separate Discord applications — a staging bot invited only to a private test guild, a production bot registered globally.
- **CI/CD:** GitHub Actions gates PRs; Railway auto-deploys on merge to the environment's branch.

---

## The decisions we made (and why)

### Railway over VPS

We looked hard at self-hosting on a VPS with `docker-compose` + Caddy. Cheaper, simpler stack. But UTMIST has **volunteer turnover** — the person who set up a box will graduate, and the next cohort inherits a mystery server. Railway makes the "who owns the box" problem go away: there's no OS to patch, no SSH key to hand off, deploys are a `git push`, and the next volunteer inherits a dashboard, not a Linux system.

Cost: ~$5–20/mo (Hobby plan). Worth it for the turnover-proofing.

### Neon over self-hosted Postgres

Same reasoning + Neon's **branching** feature. Creating `staging` as a copy-on-write branch of prod gave us a realistic staging DB in seconds, storage-efficient (only stores diffs), and reset-able whenever we want. The alternative — seeding a separate staging DB — is manual, drifts from prod, and someone has to keep it in sync forever.

**Postgres 16** (matches CI + local dev exactly). `postgresql://` connection strings are edited to `postgresql+psycopg://` so SQLAlchemy picks the right driver.

### One Neon *project* per service, one *branch* per environment

Every service owns its DB. The bot talks to team-tracking's API, not its DB. team-tracking's DB never contains a doc catalog entry, and docs-system's DB never contains a person record. Separation by design — matches the "each service is a source of truth for one domain" principle.

| | team-tracking project | documentation-system project |
|---|---|---|
| production env | `main` branch | `main` branch |
| staging env | `staging` branch | `staging` branch |

Four connection strings total (2 projects × 2 branches).

### Three Railway services, shared across environments

We started by accidentally creating **six** services (three `-staging`-suffixed ones plus three production). Cleaned up to three services, each with per-environment variables — Railway's idiomatic pattern. Same service ID in both envs; only the variable *values* differ. Adding a variable later is one dashboard change, not two.

### Branching model: feature → staging → main

```
feature branch  ──PR──▶  staging  ──PR──▶  main
                          │                  │
                          ▼                  ▼
                    Railway staging   Railway production
                    (auto-deploy)     (auto-deploy)
```

- **`staging` is the default branch** — new PRs auto-target it. Small friction win worth a small mental-model weirdness.
- **`main` is protected** and requires 5 checks (the 4 CI jobs + `enforce-source-is-staging`, a workflow that rejects any PR to main whose head isn't `staging`). Nothing reaches production without first proving itself on staging.
- **Merges to `staging`** auto-deploy to the Railway staging environment (staging Neon branch + staging Discord app).
- **Merges to `main`** auto-deploy to the Railway production environment.

### Per-consumer scoped API keys, minted by a script

The bot and docs-system authenticate to team-tracking with scoped `tt_…` keys. We do *not* share the admin bootstrap `API_KEY` across services — each consumer gets its own key with only the scopes it needs, so a leaked bot key can't be used by docs-system and vice versa, and each is independently revocable.

Keys are minted by [`scripts/provision-directory-key.sh <env>`](../scripts/provision-directory-key.sh), which runs `team-tracking-keys issue` against that environment's Neon branch and writes each key onto its Railway consumer service with `railway variables --set`. One command per environment, run when the environment is first stood up (or when a key needs rotating).

Scope lists:
- **discord-bot:** `people:read people:write identifiers:read identifiers:write teams:read teams:write memberships:read memberships:write role_kinds:read`
- **documentation-system:** `people:read teams:read` (all it needs — just to validate a doc's owner)

### CI-gated everything

`.github/workflows/ci.yml` runs on every PR to `staging` or `main`:
- `python-test` — real Postgres 16 service, applies migrations, runs the full pytest suite
- `python-lint` — ruff check + format
- `node-test` — the discord-bot's `node --test` suite
- `docker-build` — builds *and boot-smoke-tests* all three service images (`python -c "import src.api.app"` for the APIs, `node --check src/index.js` for the bot)

Plus the `main-source-guard` workflow on PRs to `main`. All required — nothing red merges.

---

## The three bugs we hit (and the fix each shipped)

All three shook out during the first live deploy attempt. Each got fixed via the branching flow (staging → main).

### 1. `${PORT}` wasn't being shell-expanded

**Symptom:** every deploy of the two APIs failed immediately with:
```
Error: Invalid value for '--port': '${PORT}' is not a valid integer.
```

**Root cause:** the `railway.json` start command was `uvicorn ... --host :: --port ${PORT}` — a plain string. Railway executed it without going through a shell, so `${PORT}` was passed literally to uvicorn (which naturally rejected it).

**Fix (commits `62bf023`, PR #11 → #12):** wrap in `sh -c`:
```json
"startCommand": "sh -c 'uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}'"
```
The shell expands `$PORT` (which Railway injects at container start) before uvicorn sees it.

### 2. `--host ::` was IPv6-only on Debian's default kernel

**Symptom:** APIs built fine, uvicorn logs showed `Uvicorn running on http://[::]:8080` and even successful `alembic upgrade head` runs — but Railway's healthcheck against `/health` failed 11 times over 5 minutes with "service unavailable," and every deploy was marked FAILED.

**Root cause:** I had specified `--host ::` on the theory that Railway's private network is IPv6. In Debian's default `python:3.11-slim` kernel config, binding to `::` binds **IPv6-only** — Railway's healthchecker was reaching in on IPv4 (`127.0.0.1:PORT`) and finding no listener.

**Fix (commits `f0bfe7a`, PR #13 → #14):** bind to the boring, universal `--host 0.0.0.0`. Railway's private networking routes to the container's port regardless of bind family, so internal service-to-service calls still work.

### 3. `${{team-tracking.PORT}}` template ref resolved to empty string

**Symptom:** everything deployed green, but running `/link` in the staging test guild returned "The directory is temporarily unavailable." The bot's HTTP call to team-tracking was failing.

**Root cause:** the bot's `DIRECTORY_BASE_URL` was set to `http://${{team-tracking.RAILWAY_PRIVATE_DOMAIN}}:${{team-tracking.PORT}}`. Railway resolves those cross-service templates from the **variable store**. But `PORT` is a **dynamic** value Railway injects into the container at runtime — it's not in the variable store. So the template resolved to `http://team-tracking.railway.internal:` — the port was literally empty. Bot's HTTP client tried to open a connection to `team-tracking.railway.internal` with no port, fell into its `DirectoryUnavailable` error path, returned the "temporarily unavailable" message.

**Fix (Railway dashboard / CLI, no code change):** explicitly set `PORT=8000` as a Railway variable on team-tracking in both environments. Now it lives in the variable store, cross-service refs resolve to `:8000`, and Railway still uses that value at container start (so uvicorn also binds to 8000 — a nice consistency win).

**Lesson:** if you use a cross-service template ref, the referenced variable must be an **explicit** Railway variable, not a Railway-injected runtime value.

---

## Current live state

- **Both environments fully up.** All 3 services (team-tracking, documentation-system, discord-bot) SUCCESS in both `staging` and `production`.
- **APIs are private-only** on Railway (no public domain). External callers can't reach them — only the bot and docs-system, over Railway's internal network, can.
- **Discord commands registered.** Staging bot: 3 stable global + 2 beta (test guild only). Production bot: 3 stable global (real UTMIST server), beta correctly skipped (no `DISCORD_GUILD_ID` set).
- **Team-tracking pre-deploy migration** runs `alembic upgrade head` against the environment's Neon branch on every deploy. Idempotent.

---

## How to redeploy

Just push to the appropriate branch:

- **Deploy to staging** — merge a PR into `staging`.
- **Deploy to production** — merge a `staging → main` PR.

Railway watches for the push and rebuilds affected services. Nothing more to do.

**Manual redeploy** (rare — e.g. after a Railway hiccup) via CLI:
```bash
railway service redeploy --service <name> --environment <staging|production> --yes
```

## How to roll back

Roll back by *reverting the commit* on the branch that deployed the bad change:

```bash
# On staging:
git checkout staging && git revert <bad-commit>
git push  # → Railway auto-redeploys staging

# On production (needs staging → main):
# 1. Revert on staging first, PR to staging, merge
# 2. Then staging → main PR to promote the revert
```

**Database migrations** — if the bad commit included a schema migration, you'll also need to downgrade with `alembic downgrade -1` against that environment's Neon branch. Every migration ships with a working `downgrade()` (that's a review requirement); use `railway run --service team-tracking --environment <env> -- alembic downgrade -1` to run it.

Neon also lets you **reset a branch** to an earlier point-in-time snapshot from the Neon dashboard — a lifeline if a migration + a data corruption happen together.

---

## Who has access to what

- **Railway project** (`Bot-Deploy`) — anyone on the `UTMIST-Internal-Tooling` Railway workspace. Add teammates in the Railway dashboard.
- **Neon projects** (`team-tracking`, `documentation-system`) — same story on the Neon side. Share via project settings.
- **GitHub repo** — GitHub team-based, standard PR flow. `main` and `staging` protected; nothing merges without CI green.
- **Discord bots** — the token lives *only* in Railway (per-environment). The Discord developer portal shows the app; only whoever created the app is a "team member" unless invited.

**Security note:** the person who deployed this (Ethan) is the only one currently seeded as a `superuser` in the production directory. Onboarding more admins is a controlled process — see the runbook's "seeding admins" section.

---

## What we deliberately didn't build

- **A local `docker-compose.yml` for the whole platform.** The specs called for one, but the existing native flows (`npm run dev:web` for the bot playground, per-service quick-starts for the APIs) already cover the local story better than a compose file would. See the design doc in `docs/superpowers/specs/` for the reasoning.
- **A separate CD system beyond Railway's auto-deploy.** Railway watches the branches; no extra pipeline needed.
- **Custom domains for the APIs.** They're private-only for now. If an external tool ever needs to reach team-tracking or docs-system, flipping on a public Railway domain is a one-click change; both APIs already have API-key auth if so.
- **Observability beyond Railway's built-in logs + metrics.** Sufficient for the current scale; revisit when we outgrow it.

## What's next if you want it

Not blocking, all optional:

- **SHA-pin CI actions** (currently on major-version tags) for supply-chain hardening.
- **Add `concurrency:` blocks to CI** so superseded PR pushes auto-cancel — saves minutes.
- **Fast-follow on the runbook's minor documentation nits.**
- **Custom domain** for team-tracking or docs-system if a dashboard/frontend ever wants to hit them from outside Railway.

## Referenced docs

- **Runbook (how to run + redeploy):** [`RAILWAY-DEPLOYMENT.md`](RAILWAY-DEPLOYMENT.md)
- **Cross-service architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Service specifics:**
  [`services/team-tracking/`](../services/team-tracking/README.md),
  [`services/documentation-system/`](../services/documentation-system/README.md),
  [`discord-bot/`](../discord-bot/README.md)
- **CI:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) + [`.github/workflows/main-source-guard.yml`](../.github/workflows/main-source-guard.yml)
- **Design specs + plans** (gitignored): `docs/superpowers/specs/` and `docs/superpowers/plans/`
