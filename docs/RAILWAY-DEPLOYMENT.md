# Railway Deployment (staging + production)

Deploys team-tracking, documentation-system, and discord-bot to Railway, backed
by Neon Postgres (a branch per environment). Repo-side config lives in each
service's `Dockerfile` + `railway.json`; the steps below are the account-side
setup you run in the Railway + Neon dashboards / CLIs.

## Prerequisites
- A Railway account + the `railway` CLI (`railway login`).
- A Neon account.
- `uv` locally (for the key-provisioning script).

## Branching + auto-deploy model
Each Railway environment is wired to a git branch. Merging a PR flips a deploy.

```
feature branch  ──PR──▶  staging  ──PR──▶  main
                          │                  │
                          ▼                  ▼
                    Railway staging   Railway production
                    (auto-deploy)     (auto-deploy)
```

- **`staging`** is the integration branch. Feature PRs target it (it's the repo
  default). Every merge auto-deploys to the `staging` Railway environment
  (staging Neon branch + staging Discord app).
- **`main`** is the release branch. **PRs to `main` may only come from
  `staging`** — enforced by the `main-source-guard` workflow
  ([`.github/workflows/main-source-guard.yml`](../.github/workflows/main-source-guard.yml)),
  which fails any PR to `main` whose head is not `staging`. Every merge to
  `main` auto-deploys to the `production` Railway environment.
- Both branches are protected; all four CI checks are required.

## 1. Neon: databases + branches
Create **two Neon projects** — `team-tracking` and `documentation-system` (each
service owns its DB). In each project you get a `main` branch (= production);
create a second branch named `staging` (copy-on-write from main). Copy the four
connection strings (2 projects × 2 branches). Use the `postgresql+psycopg://…`
form (append `?sslmode=require` if not present).

## 2. Railway: project, environments, services
1. Create a Railway project; it starts with a `production` environment — add a
   `staging` environment too.
2. Add three services from this repo:
   - `services/team-tracking` and `services/documentation-system` — Python
     services. Their Dockerfiles now build from the **repo root** as context (so
     `packages/` is reachable) and install their workspace member with
     `uv sync --frozen --no-dev --package <team-tracking|documentation-system>`
     into a venv at `/app/.venv`. So each of these two services' Railway **root
     directory is `/`**, with `railway.json` → `dockerfilePath` pointing at
     `services/team-tracking/Dockerfile` / `services/documentation-system/Dockerfile`
     respectively.
   - `discord-bot` — Node, unaffected by the workspace change; its root
     directory stays `discord-bot`.
   Railway picks up each service's `railway.json` (Dockerfile build, start
   command, health check, and — for the APIs — the `alembic upgrade head`
   pre-deploy step).
3. Keep the two APIs **private** (no public domain). The bot needs no domain.

## 3. Environment variables
Set these per environment (staging vs production) per service:

| Var | team-tracking | documentation-system | discord-bot |
|---|---|---|---|
| `DATABASE_URL` | tt Neon branch | docs Neon branch | — |
| `API_KEY` | a strong random secret | a strong random secret | — |
| `TT_ENV` | `staging` / `production` | — | — |
| `PORT` | `8000` | `8000` | — |
| `DIRECTORY_BASE_URL` | — | `http://${{team-tracking.RAILWAY_PRIVATE_DOMAIN}}:${{team-tracking.PORT}}` | same |
| `DIRECTORY_API_KEY` | — | *(set by the provisioning script — step 4)* | *(set by the script)* |
| `DISCORD_TOKEN` | — | — | staging app / prod app token |
| `DISCORD_CLIENT_ID` | — | — | per app |
| `DISCORD_GUILD_ID` | — | — | test guild (staging) / blank (prod) |
| `ENABLE_DISCORD` | — | — | `true` |
| `ENABLE_WEB` | — | — | `false` |

> **Why `PORT=8000` explicitly?** `${{team-tracking.PORT}}` in the consumers'
> `DIRECTORY_BASE_URL` only resolves when `PORT` is an explicit Railway variable.
> Railway's dynamically-injected `PORT` isn't visible to cross-service template
> refs. Without this, `DIRECTORY_BASE_URL` resolves to `http://…railway.internal:`
> (empty port) and every bot → team-tracking call fails with "directory
> temporarily unavailable." One of the three real bugs shipped through the
> branching flow — see [`DEPLOYMENT-HISTORY.md`](DEPLOYMENT-HISTORY.md).

Generate the `API_KEY` values locally so nothing sensitive appears in a shell
transcript:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
Four of them — one per API service per environment. Paste into Railway's
variable dashboard, never into a file.

**Deploy team-tracking first** in each environment. Its `preDeployCommand`
runs `alembic upgrade head` against the environment's Neon branch, which the
provisioning script (next) depends on.

## 4. Provision the directory keys
Once team-tracking is up + migrated in an environment, mint + wire the scoped
consumer keys:

```bash
railway login          # once
TT_DATABASE_URL="<team-tracking Neon branch DATABASE_URL for this env>" \
  ./scripts/provision-directory-key.sh staging      # then: production
```

This issues scoped `team-tracking-keys` for discord-bot + documentation-system
and sets each service's `DIRECTORY_API_KEY`. Re-running issues a fresh key and
repoints the consumer; the previous key stays active until you revoke it
manually (`team-tracking-keys revoke <id>`).

## 5. Register Discord slash commands
The bot has to tell Discord which slash commands it supports. Re-run whenever the
command set changes (new commands, beta→stable promotions, option tweaks). It's
idempotent — safe to re-run.

Use the wrapper so you register **both** environments in one go and can't
accidentally skip staging (a partial run leaves stale duplicate guild commands —
see #38). It always does staging first:

```bash
cd discord-bot
npm run register:all          # staging, then production
```

To target a single environment: `npm run register:staging` or
`npm run register:production`. There's also a guarded shell wrapper that prompts
before touching production: `./scripts/register.sh all` (or `staging` /
`production`).

> **Not** `npm run register` — that hardcodes `--env-file=.env` and only hits
> your **local test bot**. The `register:*` scripts (and `register.sh`) are the
> Railway-targeted ones; Railway injects each environment's secrets.

Under the hood each script runs
`railway run --service discord-bot --environment <env> -- node src/registerCommands.js`.

The script partitions commands into **stable** (registered globally — visible
in every server the bot is in) and **beta** (registered only to
`DISCORD_GUILD_ID` if set). Because we set `DISCORD_GUILD_ID` on staging and
leave it blank in production, staging gets `beta` commands in the test guild
only, and production correctly skips them.

Global registrations can take up to ~1 hour to propagate through Discord's
cache. Guild-scoped (staging) commands appear instantly.

## 6. Seed the first admin
Nobody is a directory admin on a fresh production DB. Seed yourself as a
`superuser` so you can grant others. Two ways:

**Option A — Neon SQL editor** (fastest for a one-off):
```sql
INSERT INTO people (display_name, primary_email, access_level, created_by, updated_by)
VALUES ('Your Name', 'you@example.com', 'superuser', 'manual-seed', 'manual-seed')
ON CONFLICT (primary_email) DO UPDATE
  SET access_level = 'superuser',
      updated_by   = 'manual-seed',
      updated_at   = now()
RETURNING id, display_name, primary_email, access_level;
```
Idempotent (upserts on `primary_email`). Run in the **team-tracking → main
branch** for production, or `staging` branch for staging.

**Option B — the seed CLI** (more auditable / scriptable):
```bash
TT_DB="<team-tracking Neon branch URL for this env>"
DATABASE_URL="$TT_DB" \
  uv --project services/team-tracking run team-tracking-seed seed-person \
    --name "Your Name" --email you@example.com --level superuser
```

After that, use `/link` in Discord (staging test guild or the real server) to
attach your Discord account to the seeded person record. New admins get added
by an existing admin running `/seed` from Discord.

## 7. Verify
- **APIs:** `railway run --service team-tracking --environment <env> -- bash -c 'curl -s localhost:$PORT/health'` → `{"status":"ok"}`; pre-deploy logs show `alembic upgrade head` ran.
- **Bot:** Railway logs show `Bot ready as …` — staging bot appears in the test guild; prod bot registers globally.
- **End-to-end:** run a bot command (e.g. `/whoami`) in the staging guild → reaches staging team-tracking → staging Neon branch. If it returns "directory is temporarily unavailable," the two most common causes are (1) `DIRECTORY_BASE_URL` template not resolving (see the `PORT=8000` note above), or (2) `DIRECTORY_API_KEY` missing on the consumer (re-run the provisioning script).

## Notes
- The two API Dockerfiles build with the repo root as context and
  `uv sync --frozen --no-dev --package <name>` to install just that workspace
  member (plus the shared `platform_auth` leaf from `packages/auth`) — that's
  why their Railway root directory is `/` while `discord-bot`'s stays
  `discord-bot`.
- APIs bind **`--host 0.0.0.0`**. Railway's IPv6 private network routes to the
  container's port regardless of the bind family, and `0.0.0.0` is what
  Railway's healthcheck reaches (an IPv6-only bind like `::` fails healthcheck
  on Debian's default kernel config). If service-to-service calls
  (bot → team-tracking) fail, check the `DIRECTORY_BASE_URL` reference next.
- Staging uses the **separate staging Discord application** + private test guild,
  so staging commands never touch the real UTMIST server.
- The `sh -c` wrapper on the API `startCommand` is deliberate — see the second
  bug in [`DEPLOYMENT-HISTORY.md`](DEPLOYMENT-HISTORY.md).
